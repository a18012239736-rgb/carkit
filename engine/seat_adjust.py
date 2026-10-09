"""Shared seat-adjustment parsing; persisted configuration values stay strings."""
from __future__ import annotations
import re

NAMES = ('主驾', '副驾')
EMPTY = {'', '✕', '×', 'X', '-', '—', '无', '无配置'}
POSITION = r'(主(?:驾(?:驶(?:位|座)?)?)?|副(?:驾(?:驶(?:位|座)?)?)?)'


def _clean(text):
    return re.sub(r'\s+', '', text).replace('电动调节', '电调').replace('手动调节', '手调').replace('电动', '电调').replace('手动', '手调')


def _notes(text):
    body, notes, depth, start = [], [], 0, 0
    for i, char in enumerate(text):
        if char in '(（':
            if depth == 0:
                start = i
            depth += 1
        elif char in ')）':
            depth -= 1
            if depth < 0:
                return text, ''
            if depth == 0:
                notes.append(text[start:i+1])
        elif depth == 0:
            body.append(char)
    return (text, '') if depth else (''.join(body), ''.join(notes))


def parse(value):
    text = str(value or '').strip()
    prefix = text[:1] if text.startswith(('○', '●')) else ''
    seats = [{'name': name, 'count': None, 'mode': None} for name in NAMES]
    body, suffix = _notes(text)
    result = {'seats': seats, 'suffix': suffix, 'prefix': prefix, 'editable': False, 'hint': ''}
    if '[待' in text or text == '不适用' or prefix == '○' or text.lstrip('●') in EMPTY:
        result['hint'] = '选装，不计入标准配置' if prefix == '○' else '保留原状态；请核对原文'
        return result
    # Parenthetical support notes are not seat direction totals.
    body = _clean(body.lstrip('●'))
    common = re.fullmatch(r'(?:主/?副(?:驾)?|前排)(手调|电调)', body)
    compact = re.fullmatch(POSITION+r'(\d+)向?'+POSITION+r'(\d+)向?(手调|电调)', body)
    if common:
        for seat in seats:
            seat['mode'] = common[1]
    elif compact and compact[1].startswith('主') and compact[3].startswith('副'):
        for seat, count in zip(seats, (compact[2], compact[4])):
            seat.update(count=int(count), mode=compact[5])
    else:
        pattern = POSITION+r'(?:(手调|电调)(\d+)?向?|(\d+)向?(手调|电调)?)'
        matches = list(re.finditer(pattern, body))
        rest = re.sub(pattern, '', body)
        if not matches or re.sub(r'[+/、,，;；]', '', rest):
            result['hint'] = '未识别调节方式，保留原文'
            return result
        seen = set()
        for match in matches:
            index = 0 if match[1].startswith('主') else 1
            if index in seen:
                result['seats'] = [{'name': name, 'count': None, 'mode': None} for name in NAMES]
                result['hint'] = '座位描述重复，请核对原文'
                return result
            seen.add(index)
            count = match[3] or match[4]
            seats[index].update(count=int(count) if count else None, mode=match[2] or match[5])
    if any(seat['count'] is not None and seat['count'] <= 0 for seat in seats):
        result['seats'] = [{'name': name, 'count': None, 'mode': None} for name in NAMES]
        result['hint'] = '方向数须大于0，请核对原文'
        return result
    defaulted = []
    if all(seat['mode'] == '手调' for seat in seats):
        for seat, default in zip(seats, (6, 4)):
            if seat['count'] is None:
                seat['count'] = default
                defaulted.append(seat['name']+str(default)+'向')
    result.update(suffix=suffix, editable=True)
    if any(seat['mode'] is None for seat in seats):
        result['hint'] = '调节方式未确定，未推定手调或电调'
    elif any(seat['count'] is None for seat in seats):
        result['hint'] = '方向数未说明，未推定；电调方式仍参与计价'
    elif defaulted:
        result['hint'] = '主副均手调，未说明的方向按默认'+ '、'.join(defaulted)+'计价'
    return result


def label(value):
    parsed = parse(value)
    if not parsed['editable']:
        return str(value or '')
    return parsed['prefix'] + '+'.join(
        seat['name'] + (str(seat['count'])+'向' if seat['count'] is not None else '') + (seat['mode'] or '')
        for seat in parsed['seats'] if seat['count'] is not None or seat['mode'] is not None
    ) + parsed['suffix']


def components(value):
    text = str(value or '').strip()
    if text.lstrip('●') in EMPTY or text.startswith('○'):
        return 0, 0
    parsed = parse(value)
    if not parsed['editable']:
        return None, None
    seats = parsed['seats']
    directions = sum(seat['count'] for seat in seats) if all(seat['count'] is not None for seat in seats) else None
    electric = sum(seat['mode'] == '电调' for seat in seats) if all(seat['mode'] is not None for seat in seats) else None
    return directions, electric


def raw_directions(cell):
    from .stage_one import clean, parts
    text = clean(' '.join(parts(cell)))
    # Existing stage-one convention: lumbar/headrest support is not counted.
    matches = list(re.finditer(r'(?:前后调节|靠背调节|高低调节|腿托调节|腿部支撑调节)(?:\((\d+)向\))?', text))
    if matches:
        return sum(int(match[1] or 2) for match in matches)
    body, _ = _notes(_clean(text))
    total = re.fullmatch(r'(?:主驾|副驾|座椅)?(?:手调|电调)?(\d+)向(?:手调|电调|调节)*', body)
    return int(total[1]) if total and int(total[1]) > 0 else None


def raw_modes(electric, main=None, passenger=None):
    from .stage_one import parts
    modes = [None, None]
    if electric is not None or main is not None or passenger is not None:
        modes = ['手调', '手调']
    for part in ([electric]+list(electric.subs)) if electric else []:
        text = _clean(part.text or '')
        if not text and electric.subs:
            continue
        matches = list(re.finditer(POSITION+r'(●|○|✕|×|-)?', text))
        if matches:
            explicit = parse(text)
            for j, match in enumerate(matches):
                index = 0 if match[1].startswith('主') else 1
                segment = text[match.end():matches[j+1].start() if j+1 < len(matches) else len(text)]
                detail = re.sub(r'[+/、,，;；]', '', segment)
                if '[待' in segment:
                    modes[index] = None
                elif explicit['editable'] and explicit['seats'][index]['mode'] and part.dot != '○':
                    modes[index] = explicit['seats'][index]['mode']
                elif detail in ('手调', '电调') and part.dot != '○':
                    modes[index] = detail
                elif detail not in ('', '无', '不支持'):
                    modes[index] = None
                else:
                    modes[index] = '电调' if detail not in ('无', '不支持') and (match[2] == '●' or (not match[2] and part.dot == '●')) else '手调'
        elif part.dot == '●' and text in ('', '有'):
            modes = ['电调', '电调']
        elif '[待' in text or (text and text not in EMPTY and part.dot != '○'):
            modes = [None, None]
    for i, cell in enumerate((main, passenger)):
        text = _clean(' '.join(parts(cell)))
        if '[待' in text:
            modes[i] = None
        else:
            explicit = parse(text if text.startswith(('主', '副')) else NAMES[i]+text.removeprefix('座椅'))
            if explicit['editable'] and explicit['seats'][i]['mode']:
                modes[i] = explicit['seats'][i]['mode']
    return modes


def _cells(raw, i):
    return [row.cells[i] if (row := raw.row(name)) and i < len(row.cells) else None
            for name in ('主/副驾驶座电动调节', '主座椅调节方式', '副座椅调节方式')]


def _extras(cell, standard=False):
    from .stage_one import clean, parts
    joined = clean(' '.join(parts(cell))) if standard else ' '.join([cell.text]+[sub.text for sub in cell.subs]) if cell else ''
    values = ['腿托'] if '腿托' in joined else []
    lumbar = re.search(r'腰[部]?支撑\((\d+)向\)', joined)
    return values + ([f'腰撑{lumbar[1]}向'] if lumbar else [])


def _suffix(left, right):
    if left and right:
        return f"(主{'+'.join(left)}/副{'+'.join(right)})"
    return f"({'主' if left else '副'}含{'+'.join(left or right)})" if left or right else ''


def legacy_summary(raw, i):
    """Pre-shared-parser mapper output, only for safe old-cache comparison."""
    from .stage_one import clean, parts
    electric, main, passenger = _cells(raw, i)
    solid = bool(electric and electric.dot == '●')
    electric_text = ' '.join(parts(electric))
    explicit = []
    for seat, cell, short in zip(NAMES, (main, passenger), ('主', '副')):
        match = re.fullmatch(r'(?:主驾|副驾|座椅)?(\d+)向((?:电动|手动|电调|手调|调节)*)', clean(''.join(parts(cell))))
        if not match:
            explicit.append(None)
            continue
        mode = '电调' if '电' in match[2] else '手调' if '手' in match[2] else '电调' if solid and (not electric_text or re.search(short+r'(?:驾|驾驶位)?(?:●|(?=/|$))', electric_text)) else '手调'
        explicit.append(f'{seat}{match[1]}向{mode}')
    if all(explicit):
        return '+'.join(explicit)
    base = '主副电调' if solid else '主副手调'
    return base+_suffix(_extras(main), _extras(passenger))


def from_raw(raw, i):
    from .stage_one import clean, parts
    electric, main, passenger = _cells(raw, i)
    if electric is None and main is None and passenger is None:
        return '✕'
    modes = raw_modes(electric, main, passenger)
    counts = [raw_directions(cell) for cell in (main, passenger)]
    if any(mode is None for mode in modes):
        evidence = '/'.join(clean(' '.join(parts(cell))) for cell in (electric, main, passenger))
        return '[待定]座椅调节：'+evidence
    values = [name+(str(count)+'向' if count is not None else '')+mode for name, count, mode in zip(NAMES, counts, modes)]
    extras = [_extras(cell, standard=True) for cell in (main, passenger)]
    for i, (name, cell) in enumerate(zip(NAMES, (main, passenger))):
        text = clean(' '.join(parts(cell)))
        if counts[i] is None and text and not extras[i]:
            extras[i].append('原文：'+text)
    suffix = _suffix(*extras)
    return label('+'.join(values)+suffix)
