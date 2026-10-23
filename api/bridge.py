"""api/bridge — pywebview js_api 桥：JSON 进 → engine → JSON 出

UI 层只跟这个类打交道；所有方法返回可 JSON 序列化的 dict。
异常统一包成 {"error": "..."}，绝不让 UI 拿到裸异常。
"""
from __future__ import annotations
import datetime
import json
import os
import sys
import traceback
import re
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.rules import Rules, display_order_key
from engine import rawschema, ladder as ladder_mod, differ, render_backup, valuer
from engine.models import Snapshot, Ladder, ValuationTable, ValuationItem
from engine.snapshot import resolve
from engine import acquire, stage_one, __version__
from engine.autohome_categories import clean_group, display_groups
from engine.storage import atomic_write_text, unique_filename


def _today():
    return datetime.date.today().isoformat()


class Bridge:
    def __init__(self, workdir: str):
        self.workdir = workdir          # 使用者数据目录（快照/阶梯/赋值表/结果）
        self.rules = Rules()
        self.acquirer = acquire.Acquirer()
        # Playwright's sync API is thread-affine. pywebview may invoke JS API
        # methods on different worker threads, so serialize all browser work
        # through one stable owner thread.
        self._acquire_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='carkit-browser')
        self._closed = False
        self.stage_raw = None
        self._comparison_records = {}
        self._plan_sessions = {}
        os.makedirs(workdir, exist_ok=True)
        for sub in ("raw", "阶梯", "快照", "赋值", "结果", "方案"):
            os.makedirs(os.path.join(workdir, sub), exist_ok=True)

    def shutdown(self):
        """Close the Playwright owner thread when the native window exits."""
        if self._closed:
            return
        self._closed = True
        try:
            self._acquire_executor.submit(self.acquirer.close).result(timeout=10)
        except Exception:
            pass
        self._acquire_executor.shutdown(wait=True, cancel_futures=True)

    # ---------- 通用 ----------

    def ping(self):
        return {"ok": True, "version": __version__, "rules": self.rules.version,
                "workdir": self.workdir}

    def open_file_dialog(self, file_types=None):
        """原生文件选择对话框，返回绝对路径或 None"""
        try:
            import webview
            w = webview.windows[0]
            ft = tuple(file_types) if file_types else None
            res = w.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                       file_types=ft)
            return res[0] if res else None
        except Exception as e:
            return {"error": str(e)}

    def save_file_dialog(self, default_name="", file_types=None):
        try:
            import webview
            w = webview.windows[0]
            ft = tuple(file_types) if file_types else None
            res = w.create_file_dialog(webview.SAVE_DIALOG, save_filename=default_name,
                                       file_types=ft)
            return res if isinstance(res, str) else (res[0] if res else None)
        except Exception as e:
            return {"error": str(e)}

    def workdir_path(self, *parts):
        return os.path.join(self.workdir, *parts)

    def _new_output_path(self, sub, stem, suffix):
        return os.path.join(self.workdir, sub, unique_filename(stem, suffix))

    def checklist(self):
        return self.rules.checklist

    def remove_imported_snapshot(self, filename):
        """Move an imported snapshot to a recoverable local recycle folder."""
        try:
            root = (Path(self.workdir) / '快照').resolve()
            if not filename or Path(filename).name != filename or not filename.endswith('.json'):
                raise ValueError('请选择有效的本品配置文件')
            source = (root / filename).resolve()
            if source.parent != root or not source.is_file():
                raise ValueError('本品配置文件不存在或路径无效')
            recycle = (Path(self.workdir) / '回收站' / '本品配置').resolve()
            if not recycle.is_relative_to(Path(self.workdir).resolve()):
                raise ValueError('回收站路径无效')
            recycle.mkdir(parents=True, exist_ok=True)
            target = recycle / (source.stem + '-' + uuid.uuid4().hex[:8] + '.json')
            source.rename(target)
            return {'ok': True, 'path': str(target)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def list_files(self, sub: str):
        d = os.path.join(self.workdir, sub)
        if not os.path.isdir(d):
            return []
        return sorted(os.listdir(d))

    def remove_vehicle_history(self, filename):
        try:
            workspace = Path(self.workdir).resolve()
            root = (workspace / 'raw').resolve()
            if not root.is_relative_to(workspace):
                raise ValueError('历史目录路径无效')
            if not filename or Path(filename).name != filename or not filename.lower().endswith('.json'):
                raise ValueError('无效历史文件')
            source = (root / filename).resolve()
            if source.parent != root or not source.is_file():
                raise ValueError('历史文件不存在或路径无效')
            recycle = (workspace / '回收站' / '车型历史').resolve()
            if not recycle.is_relative_to(workspace):
                raise ValueError('回收站路径无效')
            recycle.mkdir(parents=True, exist_ok=True)
            target = recycle / (source.stem + '-' + uuid.uuid4().hex[:8] + '.json')
            source.rename(target)
            self.stage_raw = None
            return {'ok': True, 'path': str(target)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def vehicle_history(self):
        records = []
        for filename in self.list_files('raw'):
            if not filename.lower().endswith('.json'):
                continue
            try:
                raw = rawschema.detect_and_load(os.path.join(self.workdir, 'raw', filename))
                years = sorted(set(re.findall(r'(20\d{2})款', ' '.join(t.full for t in raw.trims))))
                date = raw.scraped_at[:19].replace('T', ' ') if raw.scraped_at else '日期未记录'
                label = f"{raw.model or '未命名车型'} · {' / '.join(years)+'款' if years else '年款未记录'} · {len(raw.trims)}个版型 · {date}"
                records.append({'file': filename, 'label': label, 'count': len(raw.trims)})
            except Exception:
                records.append({'file': filename, 'label': filename+'（数据无法读取）', 'count': 0})
        return records

    def open_history(self, filename):
        try:
            if filename != os.path.basename(filename):
                raise ValueError('无效历史记录')
            raw = rawschema.detect_and_load(os.path.join(self.workdir, 'raw', filename))
            stage_one.validate_raw(raw)
            self.stage_raw = raw
            return {'ok': True, 'model': raw.model, 'series_id': raw.series_id,
                    'trims': [{'name': t.short, 'full': t.full, 'price_guide': t.price_guide} for t in raw.trims],
                    'rows': len(raw.rows)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def prepare_competitor(self, filename):
        try:
            if filename != os.path.basename(filename):
                raise ValueError('无效历史记录')
            raw_path = os.path.join(self.workdir, 'raw', filename)
            raw = rawschema.detect_and_load(raw_path)
            stage_one.validate_raw(raw)
            # Cache separately per capture; keep user corrections on revisits.
            import hashlib
            # Include the normalization version in the cache key.  Older
            # caches were built before embedded markers such as ``主●/副●``
            # were recognized, which could make airbags appear as zero.
            key = hashlib.sha256(Path(raw_path).read_bytes() + b"|cell-marker-v2").hexdigest()[:16]
            output = os.path.join(self.workdir, '阶梯', 'compare-'+key+'.json')
            if os.path.exists(output):
                lad = Ladder.load(output)
                lad.evidence = {'raw': raw.to_dict()}
                ladder_mod.upgrade_ladder(lad, self.rules)
                # Upgrade only untouched source-backed values, in the same cache.
                # Marketing terms never override a user's different correction.
                from engine.seat_adjust import from_raw, legacy_summary
                from engine.mapper import legacy_mapped_item, map_raw_to_ladder, n_high_voltage, n_seat_memory, n_sunroof, n_seat_func
                mapped = map_raw_to_ladder(raw, self.rules)
                source_indices = {trim.short: i for i, trim in enumerate(raw.trims)}
                configs = {item['no']: item for item in self.rules.items}
                items_by_no = {}
                for item in lad.items:
                    items_by_no.setdefault(item.no, item)
                roof, seat = items_by_no.get(18), items_by_no.get(35)
                has_seat_adjust = raw.row('主座椅调节方式', '副座椅调节方式') is not None
                airbag_values = ladder_mod._airbag_display(mapped[5]['values'], mapped[5]['airbag_comps'])
                seat_subs = {sub['sub']: sub['values'] for sub in mapped[36]['subs']}
                alias_updates = []
                for no, aliases, normalize in (
                    (3, ('高压平台（V）', '高压平台(V)'), n_high_voltage),
                    (45, ('电动座椅记忆功能',), n_seat_memory),
                ):
                    item = items_by_no.get(no)
                    if item and item.row_absent and raw.row(*aliases):
                        alias_updates.append((item, normalize))
                for i, trim in enumerate(lad.trims):
                    source_i = source_indices.get(trim['name'])
                    if source_i is None:
                        continue
                    if roof and i < len(roof.values) and roof.values[i] == n_sunroof(raw, source_i, configs[18], include_terms=False):
                        roof.values[i] = n_sunroof(raw, source_i, configs[18])
                    if seat and i < len(seat.values):
                        old_values = [from_raw(raw, source_i, include_terms=False),
                                      from_raw(raw, source_i, include_terms=False, legacy_display=True),
                                      from_raw(raw, source_i, legacy_display=True)]
                        if has_seat_adjust:
                            old_values.append(legacy_summary(raw, source_i))
                        if seat.values[i] in old_values:
                            seat.values[i] = from_raw(raw, source_i)
                    for item, normalize in alias_updates:
                        if i < len(item.values) and item.values[i] == '✕':
                            item.values[i] = normalize(raw, source_i, configs[item.no])
                    for no in (5, 6, 7, 9, 21, 22, 25, 29, 30, 31, 33, 34, 35, 36, 39):
                        item = items_by_no.get(no)
                        if not item or i >= len(item.values):
                            continue
                        versions = [legacy_mapped_item(raw, source_i, no)]
                        if no == 5:
                            versions.append(legacy_mapped_item(raw, source_i, no, legacy_side=False))
                        if no == 36:
                            value, _, subs = n_seat_func(raw, source_i, configs[no], assume_front=False)
                            versions.append({'value': value, 'subs': subs})
                            current_subs = {row['sub']: row['values'][i] for row in item.subs if i < len(row['values'])}
                            if not any(item.values[i] == old['value'] and current_subs == old['subs'] for old in versions):
                                continue  # An explicit seat correction keeps its whole trim authoritative.
                            for row in item.subs:
                                row['values'][i] = seat_subs[row['sub']][source_i]
                        elif not any(item.values[i] == old['value'] for old in versions):
                            continue
                        item.values[i] = (airbag_values[source_i]
                                          if no == 5 else mapped[no]['values'][source_i])
                        item.row_absent = mapped[no]['row_absent']
                for item in (roof, seat, items_by_no.get(3), items_by_no.get(5), items_by_no.get(30), items_by_no.get(45)):
                    if item and raw.row(*configs[item.no]['source_rows']):
                        item.row_absent = False
                # Existing captures keep hand edits; append only newly defined items.
                missing = {it['no'] for it in self.rules.items} - {it.no for it in lad.items}
                if missing:
                    fresh = ladder_mod.build_ladder(raw, self.rules, model=raw.model,
                                                    series_id=raw.series_id, date=_today())
                    indices = [source_indices.get(trim['name']) for trim in lad.trims]
                    for item in fresh.items:
                        if item.no not in missing:
                            continue
                        item.values = [item.values[i] if i is not None else '[待定]原始版型未匹配' for i in indices]
                        for sub in item.subs:
                            sub['values'] = [sub['values'][i] if i is not None else '[待定]原始版型未匹配' for i in indices]
                        lad.items.append(item)
                    lad.items.sort(key=lambda it: display_order_key(it.no))
                # Refresh applicability without discarding manual configuration edits.
                from engine.powertrain import energy_types, not_applicable
                energies = energy_types(raw)
                for i, trim in enumerate(lad.trims):
                    source_i = source_indices.get(trim['name'])
                    if source_i is None or source_i >= len(energies):
                        continue
                    trim['energy_type'] = energies[source_i]
                    for item in lad.items:
                        if i < len(item.values) and not_applicable(energies[source_i], item.no):
                            item.values[i] = '不适用'
                lad.evidence = {'raw': raw.to_dict()}
                lad.save(output)
            else:
                lad = ladder_mod.build_ladder(raw, self.rules, model=raw.model,
                                              series_id=raw.series_id, date=_today())
                lad.save(output)
            return {'ok': True, 'path': output, 'ladder': lad.to_dict()}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ---------- ① 抓取 ----------

    def scrape_status(self):
        """目标机浏览器可用性检测"""
        try:
            from engine import scrape
            return scrape.detect_browser()
        except Exception as e:
            return {"available": False, "error": str(e)}

    def scrape_open(self, series_id: str, channel: str = "msedge"):
        """第1步：打开配置页（真实浏览器），等使用者勾年款+隐藏相同参数"""
        try:
            from engine import scrape
            return scrape.scrape_open(series_id, channel)
        except Exception as e:
            return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=3)}

    def stage_search(self, query: str, year: str = ""):
        """Search by model name, or accept an Autohome series URL/id."""
        return self._acquire(self.acquirer.search, query, year)

    def stage_choose_series(self, sid: str):
        return self._acquire(self.acquirer.fetch, sid)

    def stage_apply_filters(self, selected=None):
        return self._acquire(self.acquirer.apply_filters, selected or {})

    def stage_continue(self):
        return self._acquire(self.acquirer.resume)

    def _acquire(self, action, *args):
        """Keep browser calls on their owner thread and handle captures uniformly."""
        try:
            result = self._acquire_executor.submit(action, *args).result()
            if result.get('raw'):
                return self._stage_store(result['raw'])
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _stage_store(self, raw_dict):
        raw = rawschema.RawTable.from_dict(raw_dict)
        stage_one.validate_raw(raw)
        if not raw.scraped_at:
            raw.scraped_at = datetime.datetime.now().isoformat(timespec='seconds')
        raw_path = self._new_output_path('raw', f'raw-{raw.series_id or raw.model}', '.json')
        raw.save(raw_path)
        self.stage_raw = raw
        return {"ok": True, "model": raw.model, "series_id": raw.series_id,
                "trims": [{"idx": t.idx, "name": t.short, "full": t.full,
                           "price_guide": t.price_guide} for t in raw.trims],
                "rows": len(raw.rows), "complete": True, "raw_path": raw_path}

    def stage_get_raw(self):
        if not self.stage_raw:
            return {"ok": False, "error": "请先抓取车型。"}
        return {"ok": True, "raw": self.stage_raw.to_dict()}

    def _stage_excluded_rows(self):
        defaults = self._validate_stage_exclusions(list(stage_one.DEFAULT_EXCLUDED_ROWS))
        workdir = getattr(self, 'workdir', None)
        path = os.path.join(workdir, '阶梯展示排除清单.json') if workdir else ''
        if not path or not os.path.exists(path):
            return defaults
        with open(path, encoding='utf-8') as source:
            data = json.load(source)
        rows = self._validate_stage_exclusions(data.get('excluded_rows') if isinstance(data, dict) else data)
        if isinstance(data, dict) and data.get('schema') in ('carkit.stage-display/v4', 'carkit.stage-display/v5'):
            included = set(self._validate_stage_exclusions(data.get('included_rows', []))) if data['schema'] == 'carkit.stage-display/v5' else set()
            return list(dict.fromkeys([name for name in defaults if name not in included] + rows))
        # Old files mixed defaults with custom exclusions. Store only the extra
        # exclusions; missing defaults in old files are not manual overrides.
        result = self.save_stage_display_rules(list(dict.fromkeys([*defaults, *rows])))
        if not result['ok']:
            raise ValueError(result['error'])
        return result['excluded_rows']

    @staticmethod
    def _validate_stage_exclusions(rows):
        if not isinstance(rows, list) or any(not isinstance(name, str) for name in rows):
            raise ValueError('不展示的配置须为配置行名列表')
        return list(dict.fromkeys(name.strip() for name in rows if name.strip()))

    def stage_display_rules(self):
        try:
            rows = self.stage_raw.rows if self.stage_raw else []
            excluded = self._stage_excluded_rows()
            defaults = self._validate_stage_exclusions(list(stage_one.DEFAULT_EXCLUDED_ROWS))
            standard, optional, packages = set(), {}, set()
            trim_count = len(self.stage_raw.trims) if self.stage_raw else 0
            for row in rows:
                if clean_group(row.group) == '选装包':
                    packages.add(row.name)
                for index, cell in enumerate(row.cells[:trim_count]):
                    items = [cell, *cell.subs]
                    if stage_one.parts(cell) or any('●' in item.text for item in items):
                        standard.add(row.name)
                    # Position-specific markers can live inside a standard cell.
                    if any(item.dot == '○' or '○' in item.text for item in items):
                        optional.setdefault(row.name, set()).add(index)
            option_status = {name: 'mixed' if name in standard else 'optional' for name in optional}
            option_status.update({name: 'package' for name in packages - standard - optional.keys()})
            return {'ok': True, 'excluded_rows': excluded,
                    'default_excluded_rows': defaults,
                    'rows': list(dict.fromkeys(row.name for row in rows)),
                    'groups': display_groups(rows, [*defaults, *excluded], self.workdir_path('raw')),
                    'option_status': option_status,
                    'option_availability': {name: 'none' if status == 'package' else
                                            'all' if len(optional[name]) == trim_count else 'partial'
                                            for name, status in option_status.items()}}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def save_stage_display_rules(self, excluded_rows):
        try:
            rows = self._validate_stage_exclusions(excluded_rows)
            defaults = self._validate_stage_exclusions(list(stage_one.DEFAULT_EXCLUDED_ROWS))
            selected = set(rows)
            default_names = set(defaults)
            extra = [name for name in rows if name not in default_names]
            included = [name for name in defaults if name not in selected]
            path = os.path.join(self.workdir, '阶梯展示排除清单.json')
            # Keep manual restores separate so future code defaults still apply.
            data = {'schema': 'carkit.stage-display/v5', 'excluded_rows': extra, 'included_rows': included}
            atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2)+'\n')
            return {'ok': True, 'excluded_rows': [name for name in defaults if name in selected] + extra}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def stage_filters(self):
        if not self.stage_raw:
            return {'ok': True, 'filters': []}
        raw = self.stage_raw
        fields = [('年款', None), ('能源类型', '能源类型'), ('排量', '排量(L)'),
                  ('变速箱', '变速箱'), ('驱动类型', '驱动方式'), ('四驱形式', '四驱形式')]
        filters = []
        for label, name in fields:
            if name is None:
                values = [match[1] if (match := re.search(r'(20\d{2})款', t.full)) else '' for t in raw.trims]
            else:
                row = raw.row(name)
                values = [' / '.join(stage_one.parts(c)) for c in row.cells] if row else []
            options = list(dict.fromkeys(v for v in values if v and v not in {'-', '无'}))
            if options:
                filters.append({'label': label, 'values': values, 'options': options})
        return {'ok': True, 'filters': filters}

    def stage_preview(self, plan):
        try:
            if not self.stage_raw:
                return {"ok": False, "error": "请先选择历史车型或抓取车型。"}
            raw = self.stage_raw
            stage_one.validate_plan(raw, plan)
            excluded = self._stage_excluded_rows()
            fs = stage_one.features(raw, excluded)
            columns = []
            for entry in plan:
                i, b = entry['target'], entry['base']
                columns.append({
                    'name': raw.trims[i].short,
                    'price': raw.trims[i].price_guide,
                    'base': raw.trims[b].short if b is not None else None,
                    'items': stage_one._compact_items(stage_one._change_items(fs, i, b), b),
                    'options': stage_one._option_lines(raw, i, excluded),
                })
            return {'ok': True, 'model': raw.model, 'columns': columns}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def export_excel(self, kind, payload):
        try:
            from engine.excel_export import export_report
            data = self.stage_preview(payload) if kind == 'ladder' else payload
            if kind not in ('ladder', 'diff'):
                raise ValueError('不支持的导出类型')
            if data.get('ok') is False:
                return data
            if kind == 'diff' and not data.get('groups'):
                raise ValueError('请先运行对比')
            if kind == 'ladder':
                # stage_preview carries the parsed vehicle model; keep it in the
                # suggested filename so exported files remain identifiable.
                model = data.get('model') or getattr(self.stage_raw, 'model', None) or '车型'
                safe_model = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(model)).strip(' ._') or '车型'
                name = f'配置阶梯-{safe_model}.xlsx'
            else:
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', f"竞争力对比-{data.get('self_model') or '本品'}vs{data.get('comp_model') or '竞品'}") + '.xlsx'
            path = self.save_file_dialog(name, ['Excel (*.xlsx)'])
            if isinstance(path, dict):
                return {'ok': False, 'error': path.get('error', '无法选择保存位置')}
            if not path:
                return {'ok': True, 'cancelled': True}
            if not path.lower().endswith('.xlsx'):
                path += '.xlsx'
            export_report(path, kind, data)
            return {'ok': True, 'path': path}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def stage_export(self, plan, filename='', choose_path=False):
        try:
            if not self.stage_raw:
                return {"ok": False, "error": "请先抓取车型。"}
            stage_one.validate_plan(self.stage_raw, plan)
            md = stage_one.render(self.stage_raw, plan, self._stage_excluded_rows())
            safe = re.sub(r'[^\w\-一-龥]+', '_', filename or self.stage_raw.model or '车型配置阶梯').strip('_')
            path = self._new_output_path('阶梯', safe, '.md')
            if choose_path:
                selected = self.save_file_dialog(os.path.basename(path), ['Markdown (*.md)'])
                if isinstance(selected, dict):
                    return {'ok': False, 'error': selected.get('error', '无法选择保存位置')}
                if not selected:
                    return {'ok': True, 'cancelled': True}
                path = selected if selected.lower().endswith('.md') else selected + '.md'
            atomic_write_text(path, md)
            return {"ok": True, "path": path, "md": md}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def scrape_capture(self, model: str = ""):
        """第2步：确认抓取 → canonical RawTable 落盘"""
        try:
            from engine import scrape
            raw = scrape.scrape_capture(model)
            sid = raw.series_id or "import"
            out = self._new_output_path('raw', f'raw-{sid}', '.json')
            raw.save(out)
            return {"ok": True, "path": out, "model": raw.model,
                    "trims": [t.short for t in raw.trims], "rows": len(raw.rows)}
        except Exception as e:
            return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=3)}

    def import_raw(self, path: str):
        """导入已保存的 HTML / raw JSON"""
        try:
            if path.lower().endswith((".html", ".htm")):
                from engine import scrape
                raw = scrape.parse_saved_html(path)
            else:
                raw = rawschema.detect_and_load(path)
            out = self._new_output_path('raw', f"raw-{raw.model or 'import'}", '.json')
            raw.save(out)
            return {"ok": True, "path": out, "model": raw.model,
                    "trims": [t.short for t in raw.trims], "rows": len(raw.rows),
                    "lossy": raw.lossy}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- ② 竞品阶梯 ----------

    def build_ladder(self, raw_path: str, model: str = "", series_id: str = ""):
        try:
            raw = rawschema.detect_and_load(raw_path, series_id=series_id)
            lad = ladder_mod.build_ladder(raw, self.rules, model=model or raw.model,
                                          series_id=series_id or raw.series_id, date=_today())
            out = self._new_output_path('阶梯', f'竞品阶梯-{lad.model}', '.json')
            lad.save(out)
            md = ladder_mod.render_md(lad)
            md_out = str(Path(out).with_suffix('.md'))
            atomic_write_text(md_out, md)
            return {"ok": True, "path": out, "md_path": md_out, "ladder": lad.to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=3)}

    def load_ladder(self, path: str):
        try:
            lad = Ladder.load(path)
            if not any(os.path.abspath(path) in (s['paths']['left'], s['paths']['right'])
                       for s in self._plan_sessions.values()):
                ladder_mod.upgrade_ladder(lad, self.rules)
            return {"ok": True, "ladder": lad.to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_ladder_edit(self, path: str, ladder_dict: dict):
        """GUI 表格手工微调后回存"""
        try:
            Ladder.from_dict(ladder_dict).save(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def seat_adjust_details(self, value):
        """Use the same per-seat interpretation in the editor and valuation."""
        try:
            from engine.seat_adjust import parse
            return {'ok': True, **parse(value)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    # ---------- ③ 快照 ----------

    def ppt_pages(self, path):
        try:
            from engine.ppt_import import list_pages
            return {'ok': True, 'pages': list_pages(path)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def ppt_parse(self, path, page):
        try:
            from engine.ppt_import import parse_page
            return {'ok': True, 'draft': parse_page(path, page)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def ppt_preview(self, draft):
        try:
            from engine.ppt_import import make_snapshot
            snap = make_snapshot(draft)
            return {'ok': True, 'snapshot': snap.to_dict()}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def save_ppt_snapshot(self, snap_dict, confirmed=False):
        try:
            if confirmed is not True:
                raise ValueError('请先核对解析结果并勾选确认')
            snap = Snapshot.from_dict(snap_dict)
            from engine.snapshot import prepare_snapshot
            prepare_snapshot(snap)
            from engine.screen_config import validate_snapshot_screens
            validate_snapshot_screens(snap)
            if not snap.trims or not snap.model.strip():
                raise ValueError('请填写车型和版型')
            names = [t['name'] for t in snap.trims]
            if len(set(names)) != len(names) or any(not n.strip() for n in names):
                raise ValueError('版型名称不能为空或重复')
            snap.status = '已确认（未明确项保留待定）'
            safe = re.sub(r'[^\w\-一-龥]+', '_', snap.model).strip('_')
            path = os.path.join(self.workdir, '快照', safe+'-PPT导入-'+_today()+'-'+uuid.uuid4().hex[:8]+'.json')
            snap.save(path)
            return {'ok': True, 'path': path, 'snapshot': snap.to_dict()}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def new_snapshot(self, model: str, trims: list):
        snap = Snapshot(model=model, version="v1", date=_today(), status="编辑中",
                        trims=trims,
                        cells=[{"no": it["no"], "values": {t["name"]: "✕" for t in trims},
                                "basis": ""} for it in self.rules.items])
        from engine.snapshot import prepare_snapshot
        prepare_snapshot(snap)
        out = self._new_output_path('快照', f'{model}-配置阶梯快照', '.json')
        snap.save(out)
        return {"ok": True, "path": out, "snapshot": snap.to_dict()}

    def load_snapshot(self, path: str):
        try:
            snap = resolve(Snapshot.load(path))
            return {"ok": True, "snapshot": snap.to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_snapshot(self, path: str, snap_dict: dict):
        try:
            from engine.screen_config import validate_snapshot_screens
            from engine.snapshot import prepare_snapshot
            validate_snapshot_screens(prepare_snapshot(Snapshot.from_dict(snap_dict))).save(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- ④ 赋值表 ----------

    def _current_valuation_path(self):
        return os.path.join(self.workdir, "赋值", "当前赋值规则.json")

    def current_valuation(self):
        try:
            path = self._current_valuation_path()
            customized = os.path.exists(path)
            data = json.loads(Path(path).read_text(encoding="utf-8")) if customized else {}
            return {"ok": True, "valuation": valuer.normalize_valuation(data, self.rules),
                    "path": path, "customized": customized,
                    "editor_schema": valuer.editor_schema()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_current_valuation(self, val_dict: dict):
        try:
            data = valuer.normalize_valuation(val_dict, self.rules)
            data["source"] = "用户在程序内修改的当前赋值规则"
            path = self._current_valuation_path()
            atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=1))
            return {"ok": True, "valuation": data, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def reset_current_valuation(self):
        try:
            path = self._current_valuation_path()
            if os.path.exists(path):
                os.remove(path)
            return {"ok": True, "valuation": valuer.default_valuation(self.rules),
                    "path": path, "editor_schema": valuer.editor_schema()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def make_valuation_template(self):
        out = os.path.join(self.workdir, "赋值", f"赋值表模板-{_today()}.xlsx")
        path = self._current_valuation_path()
        saved = json.loads(Path(path).read_text(encoding="utf-8")) if os.path.exists(path) else {}
        current = valuer.normalize_valuation(saved, self.rules)
        valuer.make_template_xlsx(out, self.rules, {it["no"]: it for it in current["items"]})
        return {"ok": True, "path": out}

    def load_valuation(self, path: str):
        try:
            if path.lower().endswith(".xlsx"):
                d = valuer.load_xlsx(path)
            else:
                d = json.loads(Path(path).read_text(encoding="utf-8"))
            return {"ok": True, "valuation": valuer.normalize_valuation(d, self.rules),
                    "editor_schema": valuer.editor_schema()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_valuation(self, path: str, val_dict: dict):
        try:
            val_dict = valuer.normalize_valuation(val_dict, self.rules)
            atomic_write_text(path, json.dumps(val_dict, ensure_ascii=False, indent=1))
            return {"ok": True, "valuation": val_dict}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- ⑤ 对比 ----------

    def run_diff(self, snapshot_path: str, ladder_path: str, pairs: list,
                 valuation_path: str = "", left_is_competitor: bool = False, plan_session: str = ""):
        """pairs: [{"self_trim":..,"comp_trim":..}] —— 必须由使用者指定（铁律）"""
        try:
            rules = self.rules
            if plan_session:
                session = self._plan_sessions.get(plan_session)
                if not session:
                    raise ValueError('方案工作副本已失效，请重新打开方案')
                if (os.path.abspath(snapshot_path), os.path.abspath(ladder_path), os.path.abspath(valuation_path), left_is_competitor) != (
                    session['paths']['left'], session['paths']['right'], session['paths']['valuation'], session['left_kind'] == 'ladder'):
                    raise ValueError('方案输入已变更，请重新打开方案')
                directory = session['directory']
                if any(os.path.islink(path) or os.path.dirname(os.path.realpath(path)) != directory
                       for path in session['paths'].values()):
                    raise ValueError('方案工作副本路径无效，请重新打开方案')
                rules = Rules.from_snapshot(session['rules'])
            if not pairs:
                return {"ok": False, "error": "请先指定版型配对（程序不自动配对）"}
            pairs = [dict(pair) for pair in pairs]
            for i, pair in enumerate(pairs):
                for key, label in (('self_floor_price', '左侧底价'), ('comp_floor_price', '右侧底价')):
                    pair[key] = valuer.normalize_floor_price(pair.get(key), f'第{i+1}组{label}')
            if left_is_competitor:
                from types import SimpleNamespace
                self_lad = Ladder.load(snapshot_path)
                if not plan_session:
                    ladder_mod.upgrade_ladder(self_lad, rules)
                snap = SimpleNamespace(model=self_lad.model, pending=[])
                left_input = self_lad.to_dict()
            else:
                snap = resolve(Snapshot.load(snapshot_path))
                if snap.status == '待确认':
                    raise ValueError('PPT解析草稿尚未确认，请先到本品配置核对并保存')
                self_lad = snap.to_ladder(rules.checklist["items"])
                left_input = snap.to_dict()
            comp_lad = Ladder.load(ladder_path)
            if not plan_session:
                ladder_mod.upgrade_ladder(comp_lad, rules)
            missing_items = {it['no'] for it in rules.items} - {it.no for it in comp_lad.items}
            if missing_items:
                raise ValueError('右侧竞品阶梯缺少新配置项，请重新抓取或从历史车型重新生成后再对比。')
            self_trims = [t["name"] for t in self_lad.trims]
            comp_trims = [t["name"] for t in comp_lad.trims]
            for p in pairs:
                if p["self_trim"] not in self_trims:
                    return {"ok": False, "error": f"自产品版型不存在: {p['self_trim']}"}
                if p["comp_trim"] not in comp_trims and p["comp_trim"] + "版" not in comp_trims:
                    return {"ok": False, "error": f"竞品版型不存在: {p['comp_trim']}"}
                if p['comp_trim'] not in comp_trims:
                    p['comp_trim'] += '版'
            if valuation_path:
                saved = valuer.load_xlsx(valuation_path) if valuation_path.lower().endswith(".xlsx") \
                    else json.loads(Path(valuation_path).read_text(encoding="utf-8"))
            else:
                path = self._current_valuation_path()
                saved = json.loads(Path(path).read_text(encoding="utf-8")) if os.path.exists(path) else {}
            vd = valuer.normalize_valuation(saved, rules)
            valuation = ValuationTable(version=vd["version"], source=vd["source"],
                                       items=[ValuationItem(**it) for it in vd["items"]])
            cells = differ.diff(self_lad, comp_lad, pairs, rules, valuation=valuation)
            name_by_no = {it["no"]: (it.get("md_name") or it["name"])
                          for it in rules.checklist["items"]}
            for c in cells:
                c["name"] = name_by_no.get(c["no"], str(c["no"]))
            excluded = {it.no for it in valuation.items if it.rule == 'excluded'}
            cells = [c for c in cells if c['no'] not in excluded]
            self_prices = {t["name"]: t.get("price_guide") for t in self_lad.trims}
            comp_prices = {t["name"]: t.get("price_guide") for t in comp_lad.trims}
            groups = differ.assemble_backup(cells, pairs, snap.model, comp_lad.model,
                                            self_prices, comp_prices, valuation,
                                            self_options=self_lad.options, comp_options=comp_lad.options)
            render_backup.format_configurations(cells, groups)
            notes = [f"[暂定/待定]：{p.get('reason')}（{p.get('handling')}）" for p in snap.pending]
            md = render_backup.render_md(snap.model, comp_lad.model, groups, cells,
                                         rules_version=rules.version,
                                         checklist=rules.version, date=_today(),
                                         notes=notes)
            out = self._new_output_path('结果', f'赋值对比-{snap.model}vs{comp_lad.model}', '.md')
            atomic_write_text(out, md)
            missing = sorted({n for g in groups for n in (g.get("valuation") or {}).get("missing", [])})
            from engine.comparison_review import build_review
            review = build_review(self_lad, comp_lad, pairs, rules, valuation, cells, groups)
            result = {"ok": True, "md_path": out, "md": md,
                    "self_model": snap.model, "comp_model": comp_lad.model,
                    "cells": cells, "groups": groups, "missing_valuation": missing, **review}
            if plan_session:
                excluded_rows = session['excluded_rows']
            else:
                excluded_rows = self._stage_excluded_rows()
            inputs = {'left_kind': 'ladder' if left_is_competitor else 'snapshot',
                      'left': left_input, 'right': comp_lad.to_dict(), 'pairs': pairs,
                      'valuation': vd, 'rules': rules.to_snapshot(),
                      'excluded_rows': excluded_rows}
            return self._remember_comparison(inputs, result)
        except Exception as e:
            return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=5)}

    def _remember_comparison(self, inputs, result):
        token = uuid.uuid4().hex
        result = copy.deepcopy(result)
        result['comparison_id'] = token
        self._comparison_records[token] = {'inputs': copy.deepcopy(inputs), 'result': copy.deepcopy(result)}
        while len(self._comparison_records) > 8:
            self._comparison_records.pop(next(iter(self._comparison_records)))
        return result

    def save_comparison_plan(self, name, comparison_id):
        try:
            from engine.comparison_plan import save_plan
            record = self._comparison_records.get(comparison_id)
            if not record:
                raise ValueError('该结果已失效，请重新运行对比后保存方案')
            return {'ok': True, **save_plan(os.path.join(self.workdir, '方案'), name,
                                          record['inputs'], record['result'], __version__)}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def comparison_plans(self):
        from engine.comparison_plan import load_plan
        records = []
        for filename in self.list_files('方案'):
            if not filename.endswith('.json'):
                continue
            try:
                plan = load_plan(os.path.join(self.workdir, '方案'), filename)
                records.append({'file': filename, 'name': plan['name'], 'created_at': plan['created_at']})
            except Exception:
                records.append({'file': filename, 'name': filename+'（无法读取）', 'created_at': ''})
        return {'ok': True, 'plans': sorted(records, key=lambda record: record['created_at'], reverse=True)}

    def open_comparison_plan(self, filename):
        try:
            from engine.comparison_plan import load_plan
            plan = load_plan(os.path.join(self.workdir, '方案'), filename)
            inputs = plan['inputs']
            rules = Rules.from_snapshot(inputs['rules'])
            token = uuid.uuid4().hex
            directory = os.path.join(self.workdir, '方案', '工作副本', token)
            os.makedirs(directory)
            paths = {key: os.path.join(directory, key+'.json') for key in ('left', 'right', 'valuation')}
            for key, path in paths.items():
                atomic_write_text(path, json.dumps(inputs[key], ensure_ascii=False, indent=2)+'\n')
            self._plan_sessions[token] = {'paths': paths, 'rules': rules.to_snapshot(),
                                          'directory': os.path.realpath(directory),
                                          'left_kind': inputs['left_kind'], 'excluded_rows': inputs['excluded_rows']}
            while len(self._plan_sessions) > 8:
                self._plan_sessions.pop(next(iter(self._plan_sessions)))
            result = self._remember_comparison(inputs, plan['result'])
            return {'ok': True, 'name': plan['name'], 'created_at': plan['created_at'],
                    'app_version': plan['app_version'], 'session': token, 'paths': paths,
                    'inputs': inputs, 'result': result}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def build_ladder_md_only(self, ladder_path: str):
        """由已存阶梯 JSON 重新渲染 md（GUI 编辑后导出用）"""
        try:
            lad = Ladder.load(ladder_path)
            md = ladder_mod.render_md(lad)
            out = str(Path(ladder_path).with_suffix('.md'))
            atomic_write_text(out, md)
            return {"ok": True, "path": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def write_text_file(self, path: str, text: str):
        """GUI 导出：把文本写到使用者选的路径"""
        try:
            atomic_write_text(path, text)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_5c(self, ladder_path: str):
        """5C 五段制 md 导出（P2 实装）"""
        try:
            from engine import render_5c
            lad = Ladder.load(ladder_path)
            md = render_5c.render_md(lad)
            out = self._new_output_path('结果', f'5C-看竞争-{lad.model}', '.md')
            atomic_write_text(out, md)
            return {"ok": True, "path": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}
