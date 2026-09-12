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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.rules import Rules
from engine import rawschema, ladder as ladder_mod, differ, render_backup, valuer
from engine.models import Snapshot, Ladder, ValuationTable, ValuationItem
from engine.snapshot import resolve
from engine import acquire, stage_one


def _today():
    return datetime.date.today().isoformat()


class Bridge:
    def __init__(self, workdir: str):
        self.workdir = workdir          # 使用者数据目录（快照/阶梯/赋值表/结果）
        self.rules = Rules()
        self.acquirer = acquire.Acquirer()
        self.stage_raw = None
        os.makedirs(workdir, exist_ok=True)
        for sub in ("raw", "阶梯", "快照", "赋值", "结果"):
            os.makedirs(os.path.join(workdir, sub), exist_ok=True)

    # ---------- 通用 ----------

    def ping(self):
        return {"ok": True, "version": "0.1.0", "rules": self.rules.version,
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

    def checklist(self):
        return self.rules.checklist

    def remove_imported_snapshot(self, filename):
        """Move an imported snapshot to a recoverable local recycle folder."""
        try:
            import uuid
            from pathlib import Path
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
            import uuid
            from pathlib import Path
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
                date = raw.scraped_at[:10] if raw.scraped_at else '日期未记录'
                label = f"{raw.model or '未命名车型'} · {' / '.join(years)+'款' if years else '年款未记录'} · {date}"
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
            key = hashlib.sha256(open(raw_path, 'rb').read() + b"|cell-marker-v2").hexdigest()[:16]
            output = os.path.join(self.workdir, '阶梯', 'compare-'+key+'.json')
            if os.path.exists(output):
                lad = Ladder.load(output)
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
        try:
            result = self.acquirer.search(query, year=year)
            if result.get('raw'):
                return self._stage_store(result['raw'])
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stage_choose_series(self, sid: str):
        try:
            result = self.acquirer.fetch(sid)
            if result.get('raw'):
                return self._stage_store(result['raw'])
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stage_continue(self):
        try:
            result = self.acquirer.resume()
            if result.get('raw'):
                return self._stage_store(result['raw'])
            return {"ok": True, **result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _stage_store(self, raw_dict):
        raw = rawschema.RawTable.from_dict(raw_dict)
        stage_one.validate_raw(raw)
        self.stage_raw = raw
        raw_path = os.path.join(self.workdir, "raw", f"raw-{raw.series_id or raw.model}-{_today()}.json")
        raw.save(raw_path)
        return {"ok": True, "model": raw.model, "series_id": raw.series_id,
                "trims": [{"idx": t.idx, "name": t.short, "full": t.full,
                           "price_guide": t.price_guide} for t in raw.trims],
                "rows": len(raw.rows), "complete": True, "raw_path": raw_path}

    def stage_get_raw(self):
        if not self.stage_raw:
            return {"ok": False, "error": "请先抓取车型。"}
        return {"ok": True, "raw": self.stage_raw.to_dict()}

    def stage_export(self, plan, filename=''):
        try:
            if not self.stage_raw:
                return {"ok": False, "error": "请先抓取车型。"}
            stage_one.validate_plan(self.stage_raw, plan)
            md = stage_one.render(self.stage_raw, plan)
            safe = re.sub(r'[^\w\-一-龥]+', '_', filename or self.stage_raw.model or '车型配置阶梯').strip('_')
            path = os.path.join(self.workdir, '阶梯', safe + '-' + _today() + '.md')
            with open(path, 'w', encoding='utf-8') as f: f.write(md)
            return {"ok": True, "path": path, "md": md}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def scrape_capture(self, model: str = ""):
        """第2步：确认抓取 → canonical RawTable 落盘"""
        try:
            from engine import scrape
            raw = scrape.scrape_capture(model)
            sid = raw.series_id or "import"
            out = os.path.join(self.workdir, "raw", f"raw-{sid}-{_today()}.json")
            with open(out, "w", encoding="utf-8") as f:
                f.write(raw.to_json(indent=1))
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
            out = os.path.join(self.workdir, "raw",
                               f"raw-{raw.model or 'import'}-{_today()}.json")
            with open(out, "w", encoding="utf-8") as f:
                f.write(raw.to_json(indent=1))
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
            out = os.path.join(self.workdir, "阶梯", f"竞品阶梯-{lad.model}-{_today()}.json")
            lad.save(out)
            md = ladder_mod.render_md(lad)
            md_out = out.replace(".json", ".md")
            with open(md_out, "w", encoding="utf-8") as f:
                f.write(md)
            return {"ok": True, "path": out, "md_path": md_out, "ladder": lad.to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=3)}

    def load_ladder(self, path: str):
        try:
            return {"ok": True, "ladder": Ladder.load(path).to_dict()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_ladder_edit(self, path: str, ladder_dict: dict):
        """GUI 表格手工微调后回存"""
        try:
            Ladder.from_dict(ladder_dict).save(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
            return {'ok': True, 'snapshot': json.loads(snap.to_json())}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def save_ppt_snapshot(self, snap_dict, confirmed=False):
        try:
            if confirmed is not True:
                raise ValueError('请先核对解析结果并勾选确认')
            snap = Snapshot.from_dict(snap_dict)
            if not snap.trims or not snap.model.strip():
                raise ValueError('请填写车型和版型')
            names = [t['name'] for t in snap.trims]
            if len(set(names)) != len(names) or any(not n.strip() for n in names):
                raise ValueError('版型名称不能为空或重复')
            snap.status = '已确认（未明确项保留待定）'
            safe = re.sub(r'[^\w\-一-龥]+', '_', snap.model).strip('_')
            import uuid
            path = os.path.join(self.workdir, '快照', safe+'-PPT导入-'+_today()+'-'+uuid.uuid4().hex[:8]+'.json')
            snap.save(path)
            return {'ok': True, 'path': path, 'snapshot': json.loads(snap.to_json())}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}

    def new_snapshot(self, model: str, trims: list):
        snap = Snapshot(model=model, version="v1", date=_today(), status="编辑中",
                        trims=trims,
                        cells=[{"no": it["no"], "values": {t["name"]: "✕" for t in trims},
                                "basis": ""} for it in self.rules.items])
        out = os.path.join(self.workdir, "快照", f"{model}-配置阶梯快照-{_today()}.json")
        snap.save(out)
        return {"ok": True, "path": out, "snapshot": json.loads(snap.to_json())}

    def load_snapshot(self, path: str):
        try:
            snap = resolve(Snapshot.load(path))
            return {"ok": True, "snapshot": json.loads(snap.to_json())}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_snapshot(self, path: str, snap_dict: dict):
        try:
            Snapshot.from_dict(snap_dict).save(path)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- ④ 赋值表 ----------

    def make_valuation_template(self):
        out = os.path.join(self.workdir, "赋值", f"赋值表模板-{_today()}.xlsx")
        built_in = valuer.default_valuation(self.rules)
        valuer.make_template_xlsx(out, self.rules, {it["no"]: it for it in built_in["items"]})
        return {"ok": True, "path": out}

    def load_valuation(self, path: str):
        try:
            if path.endswith(".xlsx"):
                d = valuer.load_xlsx(path)
            else:
                d = json.load(open(path, encoding="utf-8"))
            return {"ok": True, "valuation": d}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_valuation(self, path: str, val_dict: dict):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(val_dict, f, ensure_ascii=False, indent=1)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- ⑤ 对比 ----------

    def run_diff(self, snapshot_path: str, ladder_path: str, pairs: list,
                 valuation_path: str = ""):
        """pairs: [{"self_trim":..,"comp_trim":..}] —— 必须由使用者指定（铁律）"""
        try:
            if not pairs:
                return {"ok": False, "error": "请先指定版型配对（程序不自动配对）"}
            snap = resolve(Snapshot.load(snapshot_path))
            if snap.status == '待确认':
                raise ValueError('PPT解析草稿尚未确认，请先到本品配置核对并保存')
            self_lad = snap.to_ladder(self.rules.checklist["items"])
            comp_lad = Ladder.load(ladder_path)
            self_trims = [t["name"] for t in self_lad.trims]
            comp_trims = [t["name"] for t in comp_lad.trims]
            for p in pairs:
                if p["self_trim"] not in self_trims:
                    return {"ok": False, "error": f"自产品版型不存在: {p['self_trim']}"}
                if p["comp_trim"] not in comp_trims and p["comp_trim"] + "版" not in comp_trims:
                    return {"ok": False, "error": f"竞品版型不存在: {p['comp_trim']}"}
            cells = differ.diff(self_lad, comp_lad, pairs, self.rules)
            name_by_no = {it["no"]: (it.get("md_name") or it["name"])
                          for it in self.rules.checklist["items"]}
            for c in cells:
                c["name"] = name_by_no.get(c["no"], str(c["no"]))
            valuation = None
            if valuation_path:
                vd = valuer.load_xlsx(valuation_path) if valuation_path.endswith(".xlsx") \
                    else json.load(open(valuation_path, encoding="utf-8"))
                valuation = ValuationTable(version=vd.get("version", ""),
                                           source=vd.get("source", ""),
                                           items=[ValuationItem(**it) for it in vd["items"]])
            else:
                # The supplied reference workbook is now the default; the UI
                # can still load a user-edited table to override it.
                vd = valuer.default_valuation(self.rules)
                valuation = ValuationTable(version=vd["version"], source=vd["source"],
                                           items=[ValuationItem(**it) for it in vd["items"]])
            excluded = {it.no for it in valuation.items if it.rule == 'excluded'}
            cells = [c for c in cells if c['no'] not in excluded]
            self_prices = {t["name"]: t.get("price_guide") for t in self_lad.trims}
            comp_prices = {t["name"]: t.get("price_guide") for t in comp_lad.trims}
            groups = differ.assemble_backup(cells, pairs, snap.model, comp_lad.model,
                                            self_prices, comp_prices, valuation)
            notes = [f"[暂定/待定]：{p.get('reason')}（{p.get('handling')}）" for p in snap.pending]
            md = render_backup.render_md(snap.model, comp_lad.model, groups, cells,
                                         rules_version=self.rules.version,
                                         checklist=self.rules.version, date=_today(),
                                         notes=notes)
            out = os.path.join(self.workdir, "结果",
                               f"赋值对比-{snap.model}vs{comp_lad.model}-{_today()}.md")
            with open(out, "w", encoding="utf-8") as f:
                f.write(md)
            missing = sorted({n for g in groups for n in (g.get("valuation") or {}).get("missing", [])})
            return {"ok": True, "md_path": out, "md": md,
                    "self_model": snap.model, "comp_model": comp_lad.model,
                    "cells": cells, "groups": groups, "missing_valuation": missing}
        except Exception as e:
            return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=5)}

    def build_ladder_md_only(self, ladder_path: str):
        """由已存阶梯 JSON 重新渲染 md（GUI 编辑后导出用）"""
        try:
            lad = Ladder.load(ladder_path)
            md = ladder_mod.render_md(lad)
            out = ladder_path.replace(".json", ".md")
            with open(out, "w", encoding="utf-8") as f:
                f.write(md)
            return {"ok": True, "path": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def write_text_file(self, path: str, text: str):
        """GUI 导出：把文本写到使用者选的路径"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_5c(self, ladder_path: str):
        """5C 五段制 md 导出（P2 实装）"""
        try:
            from engine import render_5c
            lad = Ladder.load(ladder_path)
            md = render_5c.render_md(lad)
            out = os.path.join(self.workdir, "结果", f"5C-看竞争-{lad.model}.md")
            with open(out, "w", encoding="utf-8") as f:
                f.write(md)
            return {"ok": True, "path": out}
        except Exception as e:
            return {"ok": False, "error": str(e)}
