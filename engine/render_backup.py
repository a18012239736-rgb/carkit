"""render_backup — DiffResult → deck BACKUP 页表格式 md（对齐 golden 输出）"""
from __future__ import annotations
import datetime
import html
import re
from .rules import display_order_key

VERDICT_MARK = {"多": "**多**", "少": "**少**", "同": "同", "豁免": "豁免", "不计": "不计"}


def _configuration_label(no, value):
    """Format evidence for reading, never normalize the calculation values."""
    from .seat_adjust import parse
    text = str(value or '').strip()
    if text in {'', '✕', '×', 'X', '-', '—', '无', '无配置'}:
        return '无'
    if '[待' in text or text == '不适用':
        return text
    if text.startswith('○'):
        return '选配：' + _configuration_label(no, text[1:].replace('(选装)', ''))
    text = text.lstrip('●').strip()
    if no == 3:
        voltage = re.search(r'(\d+(?:\.\d+)?)\s*[Vv]', text)
        return voltage[1]+'V' if voltage else '800V' if text in {'', '有', '支持', '高压平台', '高压快充'} else text
    if no == 18:
        if '光感天幕' in text:
            return re.sub(r'^不可开启全景(?:天窗)?[（(](光感天幕[^()（）]*)[)）]', r'\1', text)
        return text if '天窗' in text or '天幕' in text else text+'天窗'
    if no == 20:
        from .stage_one import mirror_description
        return mirror_description([text or '有'])[0]
    if no in (21, 22, 29):
        size = re.search(r'\d+(?:\.\d+)?', text)
        size = f'{float(size[0]):g}寸' if size and 0 < float(size[0]) <= 100 else ''
        if no == 29:
            optional_full = bool(re.search(r'○\s*全液晶', text))
            full = '全液晶' in text and not optional_full
            label = ('全液晶' if full else '') + size + '仪表'
            return label + ('（全液晶选配）' if optional_full else '') if full or size or not text else text
        label = size + ('中控' if no == 21 else '副驾屏')
        options = re.findall(r'○\s*(\d+(?:\.\d+)?)\s*(?:寸|英寸)?选装', text)
        return label + ''.join(f'（{float(option):g}寸选配）' for option in options) if size else text
    if no == 34:
        return text if text.endswith('座椅') else text+'座椅' if text else '座椅材质'
    if no == 35:
        parsed = parse(value)
        if parsed['editable']:
            return '，'.join(_seat_label(seat) for seat in parsed['seats'] if seat['count'] is not None or seat['mode'])
    return text


def _seat_label(seat):
    return seat['name'] + (str(seat['count'])+'向' if seat['count'] is not None else '') + (seat['mode'] or '调节')


def _configuration_difference(no, left, right):
    from .differ import _has
    from .seat_adjust import parse
    a, b = _configuration_label(no, left), _configuration_label(no, right)
    if a == b:
        return a
    if no == 35:
        s, c = parse(left), parse(right)
        if s['editable'] and c['editable']:
            changes = []
            for current, previous in zip(s['seats'], c['seats']):
                if current == previous:
                    continue
                label = _seat_label(current) if current['count'] is not None or current['mode'] else '无'
                if previous['count'] is not None or previous['mode']:
                    label += '（'+_seat_label(previous)+'）'
                changes.append(label)
            return '，'.join(changes)
    if _has(str(left)) and _has(str(right)):
        return a+'('+b+')'
    return a if _has(str(left)) else b if _has(str(right)) else a+'('+b+')'


def format_configurations(cells, groups):
    """Apply ladder wording after pricing; UI and both exports share the result."""
    from .differ import MORE, LESS, SAME, _has, _merge_seat_labels, BACKUP_MORE_ORDER, BACKUP_LESS_ORDER
    affected = {3, 18, 20, 21, 22, 29, 34, 35}
    for cell in cells:
        no, verdict = cell['no'], cell['verdict']
        if no not in affected:
            continue
        left, right = cell['self_config'], cell['comp_config']
        cell['self_val'], cell['comp_val'] = _configuration_label(no, left), _configuration_label(no, right)
        if verdict not in (MORE, LESS, SAME):
            continue  # Keep the original pending / exemption explanation.
        difference = _configuration_difference(no, left, right)
        option_notes = ''.join(re.findall(r' (?:左侧|右侧)选装按无配置计', cell['display']))
        cell['display'] = verdict+' '+difference+option_notes
        if verdict in (MORE, LESS):
            summary = difference
            if no == 3:
                value = left if verdict == MORE and _has(str(left)) else right
                summary = _configuration_label(no, value)
            cell['backup_more'], cell['backup_less'] = (summary, '') if verdict == MORE else ('', summary)
    for pi, group in enumerate(groups):
        pair_cells = {cell['no']: cell for cell in cells if cell['pair'] == pi}
        for side, order, field in (('more', BACKUP_MORE_ORDER, 'backup_more'), ('less', BACKUP_LESS_ORDER, 'backup_less')):
            labels = {no: cell[field] for no, cell in pair_cells.items() if cell[field]}
            group[side] = _merge_seat_labels([labels[no] for no in order+sorted(labels.keys()-set(order)) if no in labels])
        for detail in (group.get('valuation') or {}).get('detail', []):
            if detail['no'] in affected and (cell := pair_cells.get(detail['no'])):
                detail['display'] = cell['backup_more'] or cell['backup_less'] or cell['display']


def _fmt_price(p):
    return f"{p:g}" if p is not None else "?"


def _fmt_money(value):
    return f"{value:.2f}".rstrip('0').rstrip('.') if value is not None else '未填写'


def missing_metric_reason(group, key):
    valuation = group.get('valuation') or {}
    if valuation.get(key + '_reason'):
        return valuation[key + '_reason']
    if valuation.get('config_adv') is None:
        return '缺少赋值规则'
    return '左侧或右侧底价未填写' if key == 'overall' else '左侧或右侧指导价未填写'


def floor_calculation(group):
    valuation = group.get('valuation') or {}
    if valuation.get('overall') is None:
        return valuation.get('overall_reason') or '缺少底价或赋值数据'
    return (f"{_fmt_money(valuation['config_adv'])} + {_fmt_money(group.get('comp_floor_price'))} "
            f"− {_fmt_money(group.get('self_floor_price'))} = {_fmt_money(valuation['overall'])}")


def render_md(self_model, comp_model, groups, cells, rules_version="v1",
              checklist="v1", date=None, notes=None, pair_labels=None):
    date = date or datetime.date.today().isoformat()
    lines = []
    lines.append(f"# 赋值对比：{self_model} vs {comp_model}（{date}）")
    lines.append("")
    lines.append(f"- 配对：使用者指定（程序绝不自动配对）")
    lines.append(f"- 规则：对比配置清单 {checklist} / 豁免规则 {rules_version}（carkit engine 生成）")
    lines.append("- 价格口径：指导价单位为万元；底价及计算金额单位为元。底价为本次配对手动填写，不修改车型指导价。")
    lines.append("")
    lines.append("## 竞争力对比表（deck BACKUP 格式）")
    lines.append("")
    n = len(groups)
    header = "|  | " + " | ".join(
        f"{self_model} {_fmt_price(g['self_price'])} VS {comp_model} {_fmt_price(g['comp_price'])}"
        for g in groups) + " |"
    lines.append(header)
    lines.append("| ---" * (n + 1) + " |")
    lines.append("| 版型 | " + " | ".join(
        f"{g['pair']['self_trim']} vs {g['pair']['comp_trim']}" for g in groups) + " |")
    lines.append(f"| {self_model}多 | " + " | ".join("<br>".join(g["more"]) or "—" for g in groups) + " |")
    lines.append(f"| {self_model}少 | " + " | ".join("<br>".join(g["less"]) or "—" for g in groups) + " |")

    def money_row(key, label):
        row = []
        for g in groups:
            v = g.get("valuation") or {}
            val = v.get(key)
            row.append(missing_metric_reason(g, key) if val is None else _fmt_money(val))
        lines.append(f"| {label} | " + " | ".join(row) + " |")

    money_row("config_adv", "配置优势（元）")
    money_row("flat_adv", "拉平指导价优势（元）")
    money_row("overall", "综合竞争力（元）")
    for field, model in (('self_options', self_model), ('comp_options', comp_model)):
        if any(g.get(field) for g in groups):
            def safe(text):
                text = html.escape(str(text)).replace('|', '&#124;')
                return re.sub(r'([\\`*_\[\]~])', r'\\\1', text).replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')
            lines.append(f"| {safe(model)}选装（仅展示，不参与赋值） | " + " | ".join(
                '<br>'.join(safe(option) for option in g.get(field, []) or []) or '—' for g in groups) + " |")
    lines.append("")
    lines.append("## 底价与价格计算依据")
    lines.append("")
    lines.append("综合竞争力（拉平底价优势）＝配置优势＋右侧底价−左侧底价。底价缺失时不使用指导价或0代替。")
    lines.append("")
    lines.append("| 版型配对 | 左侧底价（元） | 右侧底价（元） | 综合竞争力计算（元） |")
    lines.append("| --- | --- | --- | --- |")
    for g in groups:
        left, right = g.get('self_floor_price'), g.get('comp_floor_price')
        lines.append(f"| {g['pair']['self_trim']} vs {g['pair']['comp_trim']} | {_fmt_money(left)} | {_fmt_money(right)} | {floor_calculation(g)} |")
    lines.append("")
    if notes:
        for nt in notes:
            lines.append(f"> {nt}")
        lines.append("")

    lines.append("## 附：配置项判定明细（追溯用）")
    lines.append("")
    plabels = pair_labels or [f"{g['pair']['self_trim']}vs{g['pair']['comp_trim']}" for g in groups]
    lines.append("| # | 配置项 | " + " | ".join(plabels) + " |")
    lines.append("|---" * (len(plabels) + 2) + "|")
    # 按项号分组渲染
    nos = sorted({c["no"] for c in cells}, key=display_order_key)
    item_names = {c["no"]: c.get("name", "") for c in cells}
    for serial, no in enumerate(nos, 1):
        row_cells = [c for c in cells if c["no"] == no]
        row_cells.sort(key=lambda c: c["pair"])
        name = item_names.get(no) or str(no)
        disp_cells = []
        for c in row_cells:
            d = c["display"]
            # 判定词加粗对齐 golden：**多** / **少**
            for v in ("多", "少"):
                if d.startswith(v + " "):
                    d = f"**{v}** " + d[len(v) + 1:]
                    break
            disp_cells.append(d)
        lines.append(f"| {serial} | {name} | " + " | ".join(disp_cells) + " |")
    lines.append("")
    lines.append("> 由 carkit engine 生成；判定词：多/少/同/豁免/不计；豁免规则见 rules/exemptions.json。")
    return "\n".join(lines) + "\n"
