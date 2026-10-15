"""Read-only comparison evidence and review hints; never change decisions or prices."""
from __future__ import annotations

from copy import deepcopy
import re

from . import differ, valuer
from .ladder import build_ladder
from .models import RawTable


def _trim_index(names, target):
    if target in names:
        return names.index(target)
    matches = [i for i, name in enumerate(names) if name.rstrip('版') == target.rstrip('版')]
    return matches[0] if len(matches) == 1 else None


def _source(ladder, rules):
    saved = ladder.evidence.get('raw') if isinstance(ladder.evidence, dict) else None
    if not isinstance(saved, dict):
        return None, None, None
    try:
        raw = RawTable.from_dict(saved)
        return saved, raw, build_ladder(raw, rules)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError):
        # Imported old or incomplete evidence cannot make a valid comparison fail.
        return saved, None, None


def _same_value(no, value, source_value):
    if no == 35:
        from .seat_adjust import label
        return label(value) == label(source_value)
    if no == 9:
        return differ.normalize_adas(value) == differ.normalize_adas(source_value)
    if no in (21, 22, 29):
        from .screen_config import normalize_screen
        return normalize_screen(value, no) == normalize_screen(source_value, no)
    return value == source_value


def _seat_calculation(value, raw, index):
    from .seat_adjust import components, parse, raw_directions
    from .stage_one import parts
    lines = []
    if raw is not None and index is not None:
        for name, row_name in (('主驾', '主座椅调节方式'), ('副驾', '副座椅调节方式')):
            row = raw.row(row_name)
            if row is None or index >= len(row.cells):
                continue
            cell = row.cells[index]
            motions = {}
            for text in parts(cell):
                for match in re.finditer(r'([○✕×-]?)\s*(前后调节|靠背调节|高低调节|腿托调节|腿部支撑调节)(?:\s*[(（](\d+)向[)）])?', text):
                    if match[1]:
                        continue
                    motion = match[2].replace('腿部支撑', '腿托')
                    count = (int(match[3]) if match[3] else None) if motion == '高低调节' else 2
                    motions.setdefault(motion, count)
            total = raw_directions(cell)
            if motions:
                terms = [motion + (f'{count}向' if count is not None else '方向未注明')
                         for motion, count in motions.items()]
                lines.append(name + '原文：' + '＋'.join(terms) + (f'＝{total}向' if total is not None else '；方向合计需核对'))
    parsed = parse(value)
    if parsed['editable']:
        for seat in parsed['seats']:
            lines.append('当前计算采用：' + seat['name'] +
                         (f"{seat['count']}向" if seat['count'] is not None else '方向未确定') +
                         (seat['mode'] or '调节方式未确定'))
        count, electric = components(value)
        lines.append('当前合计：' + (f'{count}向' if count is not None else '方向未知，不建立方向差额') +
                     '；' + (f'{electric}个电调座椅' if electric is not None else '电调数量未知'))
    lines.append('前后、靠背、腿托各计2向；高低按原表注明方向；腰撑、侧翼等不计方向；选配不计入标配，电调加价保持原规则。')
    return lines


def _calculation(no, value, raw, index):
    if no == 35:
        return _seat_calculation(value, raw, index)
    if no == 33:
        from .wireless import units
        labels = {'fast': '快充', 'slow': '慢充', 'unknown': '功率未注明，沿用快充单价，不补写功率'}
        parsed = units(value)
        lines = [f'{position or "未标位置"}：{count}个，{labels[kind]}' for position, count, kind in parsed]
        if not parsed and _active(value):
            lines.append('现有识别未确认无线充电的位置或数量；不改计算结果，请核对原文。')
        return lines + [
            '前后排分别计数；≥40W为快充，低于40W为慢充；选配不计入标配。']
    return []


def _side(ladder, trim, no, value, rules, valuation, context):
    saved, raw, mapped = context
    item = ladder.item(no)
    index = _trim_index([entry['name'] for entry in ladder.trims], trim)
    source_index = _trim_index([entry.short for entry in raw.trims], trim) if raw is not None else None
    result = {'model': ladder.model, 'trim': trim, 'value': deepcopy(value),
              'source_kind': 'unavailable', 'source_url': '', 'captured_at': '',
              'rows': [], 'source_value': None, 'notes': [], 'calculation': []}
    if raw is not None:
        autohome = str(raw.series_id).isdigit() and raw.source != 'manual'
        result['source_kind'] = 'autohome' if autohome else 'input'
        result['source_url'] = f'https://www.autohome.com.cn/config/series/{raw.series_id}.html' if autohome else ''
        result['captured_at'] = raw.scraped_at
        if source_index is None:
            result['notes'].append('原始配置无法唯一对应此版型，未推定来源。')
        else:
            names = set(rules.items_by_no.get(no, {}).get('source_rows', []))
            names.update(name for name, item_no in rules.row_to_item.items() if item_no == no)
            result['rows'] = [{'name': row['name'], 'group': row.get('group', ''),
                               'cell': deepcopy(row['cells'][source_index])}
                              for row in saved.get('rows', []) if row.get('name') in names and source_index < len(row.get('cells', []))]
            vitem = valuation.item(no) if valuation is not None else None
            source_value = differ._pair_values(mapped, mapped, no, source_index, source_index,
                                              usb_base=(vitem.get('params') or {}).get('base_count', 3) if vitem else 3)[0]
            result['source_value'] = source_value
            if not _same_value(no, value, source_value):
                result['notes'].append('计算用配置与原文识别不同，可能有人工修正或识别版本差异。')
            if not result['rows']:
                result['notes'].append('原始表没有对应配置行；沿用现有无行处理规则，不代表另行核实为无配置。')
    elif ladder.side == 'self' or str(ladder.source or '').startswith('snapshot'):
        result['source_kind'] = 'input'
        result['captured_at'] = ladder.date
        result['notes'].append('输入依据：' + item.note if item and item.note else '人工输入配置，未保存原始配置页。')
    else:
        result['notes'].append('未保存原始配置页；已有配置和计算结果保留，无法追溯原文。')
        if item and item.note:
            result['notes'].append('已有记录说明：' + item.note)
        if saved is not None:
            result['notes'].append('保存的原文格式不完整，未推定配置内容。')
    result['calculation'] = _calculation(no, value, raw, source_index)
    if index is None or (item and index >= len(item.values)):
        result['notes'].append('输入配置未提供此版型的该项值，沿用当前计算值。')
    return result


def _pending(value, token):
    return any(_pending(v, token) for v in value.values()) if isinstance(value, dict) else token in str(value)


def _active(value):
    if isinstance(value, dict):
        return any(_active(v) for v in value.values())
    text = str(value or '').strip()
    return text not in ('', '✕', '×', 'X', '-', '—', '无', '无配置', '不适用', '0', '0气囊') and not text.startswith('○')


def _unknown_count(no, value):
    if no == 35:
        from .seat_adjust import components
        return None in components(value)
    if no == 32:
        from .usb import usb_total
        return usb_total(value) is None
    if no == 33:
        from .wireless import units
        return not units(value)
    if no in (5, 8, 37, 38):
        return not re.search(r'\d', str(value))
    return False


def build_review(left, right, pairs, rules, valuation, cells, groups):
    """Return per-pair/per-item source evidence and non-blocking review entries."""
    contexts = [_source(ladder, rules) for ladder in (left, right)]
    evidence, review = [], []
    for cell in cells:
        pair_index, no = cell['pair'], cell['no']
        pair = pairs[pair_index]
        cfg = rules.items_by_no.get(no, {})
        name = cfg.get('name', str(no))
        group_value = groups[pair_index].get('valuation', {}) if pair_index < len(groups) else {}
        detail = next((row for row in group_value.get('detail', []) if row['no'] == no), None)
        entry = {'pair': pair_index, 'no': no, 'name': name,
                 'rule': valuer.explain_rule(valuation, no) if valuation is not None and valuation.item(no) else '未提供赋值规则',
                 'amount': detail['amount'] if detail is not None else None}
        vitem = valuation.item(no) if valuation is not None else None
        excluded = bool(cfg.get('exempt_from_valuation') or (vitem and vitem.get('rule') == 'excluded'))
        if excluded:
            entry['rule'] = '本项不参与赋值计算。'
        for side, ladder, trim_key, value_key, context in (
            ('left', left, 'self_trim', 'self_config', contexts[0]),
            ('right', right, 'comp_trim', 'comp_config', contexts[1]),
        ):
            value = cell.get(value_key, cell.get('self_val' if side == 'left' else 'comp_val', '✕'))
            item = ladder.item(no)
            entry[side] = _side(ladder, pair[trim_key], no, value, rules, valuation, context)
            if excluded or not _active(value):
                continue
            code = ('pending' if _pending(value, '[待定]') or str(value).strip() == '?' else
                    'unmapped' if (item and item.unmapped) or _pending(value, '[待映射]') else
                    'unknown_count' if _unknown_count(no, value) else '')
            messages = {'pending': '该项待定，需核对来源或补充配置。',
                        'unmapped': '该项尚未完成识别映射，需核对原文。',
                        'unknown_count': '有配置，但计算所需的数量或调节方式未确定；沿用现有处理规则。'}
            if code:
                review.append({'pair': pair_index, 'no': no, 'name': name, 'side': side,
                               'level': 'warning', 'code': code, 'message': messages[code]})
        if not excluded:
            for side, ladder, context in (('left', left, contexts[0]), ('right', right, contexts[1])):
                item = ladder.item(no)
                if context[1] is not None and item and item.row_absent and entry[side]['value'] != '不适用':
                    review.append({'pair': pair_index, 'no': no, 'name': name, 'side': side,
                                   'level': 'info', 'code': 'source_row_absent',
                                   'message': '原始表没有该配置行；沿用现有无行处理规则，可查看来源核对。'})
            if no in group_value.get('missing', []) and any(_active(entry[side]['value']) for side in ('left', 'right')):
                review.append({'pair': pair_index, 'no': no, 'name': name, 'side': 'both',
                               'level': 'warning', 'code': 'missing_valuation', 'message': '此项差异缺少赋值规则，金额未确定。'})
        evidence.append(entry)
    return {'evidence': evidence, 'review': review}
