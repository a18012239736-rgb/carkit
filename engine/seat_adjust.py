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


def label(value, *, include_notes=False):
    parsed = parse(value)
    if not parsed['editable']:
        return str(value or '')
    return parsed['prefix'] + '+'.join(
        seat['name'] + (str(seat['count'])+'向' if seat['count'] is not None else '') + (seat['mode'] or '')
        for seat in parsed['seats'] if seat['count'] is not None or seat['mode'] is not None
    ) + (parsed['suffix'] if include_notes else '')


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


def raw_directions(cell, *, legacy_support=False):
    """Count only standard whole-seat motions; support adjustments are not axes."""
    from .stage_one import parts
    motions = {}
    pattern = '前后调节|靠背调节|高低调节' + ('|腿托调节|腿部支撑调节' if legacy_support else '')
    for text in parts(cell):
        if '[待' in text:
            return None
        for match in re.finditer(r'([○✕×-]?)\s*('+pattern+r')(?:\s*[(（](\d+)向[)）])?', text):
            if match[1]:
                continue
            motion = match[2].replace('腿部支撑', '腿托')
            count = (int(match[3]) if match[3] else None) if motion == '高低调节' else 2
            if motion in motions and motions[motion] != count:
                return None  # Conflicting height annotations need review, not addition.
            motions[motion] = count
    if motions:
        return sum(motions.values()) if all(count and count > 0 for count in motions.values()) else None
    # Explicit totals (including manual corrections) remain authoritative.
    from .stage_one import clean
    body, _ = _notes(_clean(clean(' '.join(parts(cell)))))
    total = re.fullmatch(r'(?:主驾|副驾|座椅)?(?:手调|电调)?(\d+)向(?:手调|电调|调节)*', body)
    return int(total[1]) if total and int(total[1]) > 0 else None


def _legacy_raw_directions(cell):
    """Frozen previous auto value, used only to recognize untouched caches."""
    from .stage_one import clean, parts
    text = clean(' '.join(parts(cell)))
    # Existing stage-one convention: lumbar/headrest support is not counted.
    matches = list(re.finditer(r'(?:前后调节|靠背调节|高低调节|腿托调节|腿部支撑调节)(?:\((\d+)向\))?', text))
    if matches:
        return sum(int(match[1] or 2) for match in matches)
    body, _ = _notes(_clean(text))
    total = re.fullmatch(r'(?:主驾|副驾|座椅)?(?:手调|电调)?(\d+)向(?:手调|电调|调节)*', body)
    return int(total[1]) if total and int(total[1]) > 0 else None


def raw_modes(electric, main=None, passenger=None, *, legacy_price_notes=False):
    from .stage_one import parts
    modes = [None, None]
    if electric is not None or main is not None or passenger is not None:
        modes = ['手调', '手调']
    for part in ([electric]+list(electric.subs)) if electric else []:
        text = _clean(part.text or '')
        if not legacy_price_notes:
            # A price annotation is not an adjustment mode or seat marker.
            text = re.sub(r'[(（]\d+(?:\.\d+)?(?:万)?元[)）]', '', text)
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


def standard_front_positions(cell, *, legacy_scope=False):
    """Explicit front seats only; embedded optional/pending markers stay excluded."""
    from .stage_one import parts
    positions = set()
    for text in parts(cell):
        if '[待' in text:
            continue
        pattern = r'(主副(?:驾)?|前排|第一排|主(?:驾(?:驶(?:位|座)?)?)?|副(?:驾(?:驶(?:位|座)?)?)?|驾驶位)([●○✕×-]?)'
        if legacy_scope:
            pattern = pattern.replace('|第一排', '')
        else:
            text = re.sub(r'(?:前排|第一排)[(（](?:仅)?(驾驶位|主驾(?:驶(?:位|座)?)?|副驾(?:驶(?:位|座)?)?)[)）]', r'\1', text)
        for match in re.finditer(pattern, text):
            scope, marker = match.groups()
            if marker in {'○', '✕', '×', '-'}:
                continue
            positions.update((0, 1) if scope.startswith(('主副','前排','第一排')) else (1,) if scope.startswith('副') else (0,))
    return sorted(positions)


def zero_gravity_positions(raw, i, *, legacy_scope=False):
    """Never infer a seat position from the presence of a zero-gravity dot alone."""
    row = raw.row('零重力座椅')
    return standard_front_positions(row.cells[i], legacy_scope=legacy_scope) if row and i < len(row.cells) else []


_SUPPORTS = {'腿托': r'腿托|腿部支撑', '腰托': r'腰托|腰撑|腰部支撑|腰支撑'}
_FRONT_SCOPE = re.compile(r'主副(?:驾)?|前排|第一排|' + POSITION + r'|驾驶位')


def _support_positions(value, feature, default=(), *, named=False, absent=False, keep_unknown=False):
    aliases = _SUPPORTS[feature]
    text = re.sub(r'\s+', '', str(value or '')).replace('（', '(').replace('）', ')')
    text = re.sub(r'主(?:驾)?(?:/|和|与|及)副(?:驾)?(?=[^驾●○✕×-]|$)', '主副', text)
    if text.startswith('○') or '[待' in text:
        return set()
    positions, scope = set(), set(default)
    for phrase in re.split(r'[+＋/／、,，;；\n]', text):
        if re.search(r'后排|二排|第二排|第三排', phrase):
            scope = set()
            continue
        scopes = list(_FRONT_SCOPE.finditer(phrase))
        matches = list(re.finditer(aliases, phrase))
        if not matches and named:
            matches = [re.search(r'$', phrase)]
        for match in matches:
            before = [entry for entry in scopes if entry.end() <= match.start()]
            active = before[-1] if before else None
            current = set(scope)
            if active:
                name = active[0]
                current = {0, 1} if name.startswith(('主副', '前排', '第一排')) else {1} if name.startswith('副') else {0}
            # A local qualifier overrides a common front-row scope.
            qualifier = re.match(r'(?:调节)?\((?:仅)?(主副(?:驾)?|前排|第一排|主驾(?:驶(?:位|座)?)?|驾驶位|副驾(?:驶(?:位|座)?)?)\)', phrase[match.end():])
            if qualifier:
                name = qualifier[1]
                current = {0, 1} if name.startswith(('主副', '前排', '第一排')) else {1} if name.startswith('副') else {0}
            prefix = _FRONT_SCOPE.sub('', phrase[:match.start()])
            suffix = phrase[match.end():]
            markers = re.findall(r'[●○✕×-]', prefix)
            optional = bool(markers and markers[-1] == '○') or bool(re.search(r'选装|选配', phrase)) or bool(re.match(r'(?:调节)?○', suffix))
            negative = r'无|取消|不支持|未配备|不再配备|不带'
            missing = (bool(markers and markers[-1] in '✕×-')
                       or bool(re.search(r'(?:'+negative+r')(?:座椅)?$', prefix))
                       or bool(re.match(r'(?:调节)?(?:[：:]?\(?(?:'+negative+r')|[✕×-])', suffix)))
            if not optional and missing == absent:
                positions.update(current or ({None} if keep_unknown else set()))
        if scopes:
            name = scopes[-1][0]
            scope = {0, 1} if name.startswith(('主副', '前排', '第一排')) else {1} if name.startswith('副') else {0}
    return positions


def _support_label(positions, feature):
    known = positions - {None}
    label = '前排'+feature if known == {0, 1} else '+'.join(NAMES[i]+feature for i in sorted(known))
    if None in positions:
        return '[待定]' + (label+'；另有' if label else '') + feature+'座位未说明'
    return label or '✕'


def support_from_text(value, feature):
    """Read explicitly assigned front-seat supports, including old #35 notes."""
    return _support_label(_support_positions(value, feature), feature)


def update_support_text(previous, value, feature):
    """Apply an explicit front-seat addition/removal without losing inherited seats."""
    added = _support_positions(value, feature, keep_unknown=True)
    removed = _support_positions(value, feature, absent=True, keep_unknown=True)
    if not added and not removed:
        return None  # Rear-only or optional text does not alter the front supports.
    if None in added | removed or '[待' in str(previous):
        return f'[待定]原配置：{previous}；原文：{value}（请确认{feature}座位及变更）'
    return _support_label((_support_positions(previous, feature) | added) - removed, feature)


def support_source_rows(raw, feature):
    """Return the same front-seat source rows used for support normalization."""
    return [row for row in raw.rows if not re.search(r'后排|二排|第二排|第三排', row.name)
            and (row.name in ('主座椅调节方式', '副座椅调节方式', '前排座椅功能')
                 or re.search(_SUPPORTS[feature], row.name))]


def support_from_raw(raw, i, feature):
    """Separate standard front supports; adjustment-row names establish the seat."""
    from .stage_one import parts
    positions = set()
    for row in support_source_rows(raw, feature):
        if i >= len(row.cells):
            continue
        named = bool(re.search(_SUPPORTS[feature], row.name))
        if row.name in ('主座椅调节方式', '副座椅调节方式'):
            default = (0,) if row.name.startswith('主') else (1,)
        elif row.name == '前排座椅功能':
            default = (0, 1)
        else:
            default = _support_positions(row.name, feature)
        for text in parts(row.cells[i]):
            positions.update(_support_positions(text, feature, default, named=named, keep_unknown=True))
    return _support_label(positions, feature)


def raw_details(raw, i, *, include_terms=True, legacy_price_notes=False, legacy_display=False, legacy_support=False):
    return _raw_details(raw, i, _cells(raw, i), include_terms=include_terms,
                        legacy_price_notes=legacy_price_notes, legacy_display=legacy_display,
                        legacy_support=legacy_support)


def _raw_details(raw, i, cells, *, include_terms, legacy_price_notes, legacy_display, legacy_support=False):
    electric, main, passenger = cells
    count_directions = _legacy_raw_directions if legacy_display or legacy_price_notes else raw_directions
    counts = [count_directions(cell) if count_directions is _legacy_raw_directions
              else raw_directions(cell, legacy_support=legacy_support) for cell in (main, passenger)]
    positions = zero_gravity_positions(raw, i, legacy_scope=legacy_price_notes) if include_terms else []
    # pjy confirmed this mapping for MG 07, not every brand's zero-gravity seat.
    if raw.series_id == '8563' or re.sub(r'\s+', '', raw.model).upper() == 'MG07':
        for j in positions:
            if counts[j] is None:
                counts[j] = 10
    return counts, raw_modes(electric, main, passenger, legacy_price_notes=legacy_price_notes), positions


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


def from_raw(raw, i, *, include_terms=True, legacy_price_notes=False, legacy_display=False, legacy_support=False):
    """Normalize adjustment totals; legacy_support freezes the previous leg-rest count."""
    from .stage_one import clean, parts
    electric, main, passenger = _cells(raw, i)
    counts, modes, positions = _raw_details(raw, i, (electric, main, passenger), include_terms=include_terms,
                                          legacy_price_notes=legacy_price_notes, legacy_display=legacy_display,
                                          legacy_support=legacy_support)
    gravity = raw.row('零重力座椅') if include_terms else None
    unknown = parts(gravity.cells[i]) if gravity and i < len(gravity.cells) else []
    if unknown and not positions and electric is None and main is None and passenger is None:
        return '[待定]零重力座椅：'+ '+'.join(unknown) + '（请确认座位和方向数）'
    if electric is None and main is None and passenger is None and not positions:
        return '✕'
    if modes == ['手调', '手调'] and not (legacy_display or legacy_price_notes) and any(
        count is None and any('高低调节' in text for text in parts(cell))
        for count, cell in zip(counts, (main, passenger))
    ):
        # Do not guess the manual default; known electric modes still price below.
        return '[待定]座椅调节方向数未说明或冲突'
    if any(mode is None for mode in modes):
        if not (legacy_display or legacy_price_notes):
            return '[待定]座椅调节：' + '+'.join(
                name+(str(count)+'向' if count is not None else '')+(mode or '调节方式未说明')
                for name, count, mode in zip(NAMES, counts, modes))
        evidence = '/'.join(clean(' '.join(parts(cell))) for cell in (electric, main, passenger))
        if positions:
            evidence += '/' + '+'.join(NAMES[j]+(str(counts[j])+'向' if counts[j] else '')+'零重力座椅' for j in positions)
        return '[待定]座椅调节：'+evidence
    values = [name+(str(count)+'向' if count is not None else '')+mode for name, count, mode in zip(NAMES, counts, modes)]
    if not (legacy_display or legacy_price_notes):
        return label('+'.join(values))
    extras = [_extras(cell, standard=True) for cell in (main, passenger)]
    for i, (name, cell) in enumerate(zip(NAMES, (main, passenger))):
        text = clean(' '.join(parts(cell)))
        if counts[i] is None and text and not extras[i]:
            extras[i].append('原文：'+text)
    suffix = _suffix(*extras)
    if positions:
        suffix += '(' + '+'.join(NAMES[j]+'零重力座椅' for j in positions) + ')'
    elif unknown:
        suffix += '(零重力座椅座位未说明)'
    return label('+'.join(values)+suffix, include_notes=True)


def upgrade_ladder_support(ladder):
    """Upgrade normal file loads explicitly; frozen comparison plans skip this."""
    from .models import LadderItem, RawTable
    errors = (KeyError, TypeError, ValueError, IndexError, AttributeError)
    items = {}
    for item in ladder.items:
        items.setdefault(item.no, item)
    seat = items.get(35)
    raw = None
    try:
        saved = ladder.evidence.get('raw') if isinstance(ladder.evidence, dict) else None
        if isinstance(saved, dict):
            raw = RawTable.from_dict(saved)
    except errors:
        pass  # An incomplete old source must not prevent opening hand edits.
    values = {46: [], 47: []}
    recovered = False
    for i, trim in enumerate(ladder.trims):
        old = seat.values[i] if seat and i < len(seat.values) else ''
        try:
            source_i = None
            if raw is not None:
                matches = [j for j, entry in enumerate(raw.trims) if entry.short == trim['name']]
                if not matches:
                    matches = [j for j, entry in enumerate(raw.trims) if entry.short.rstrip('版') == trim['name'].rstrip('版')]
                if len(matches) == 1:
                    source_i = matches[0]
            if source_i is None:
                raise ValueError('原始版型无法对应')
            supports = {no: support_from_raw(raw, source_i, feature)
                        for no, feature in ((46, '腿托'), (47, '腰托'))}
            previous = [from_raw(raw, source_i, legacy_support=True),
                        from_raw(raw, source_i, legacy_support=True, include_terms=False),
                        from_raw(raw, source_i, legacy_display=True),
                        from_raw(raw, source_i, legacy_display=True, include_terms=False),
                        from_raw(raw, source_i, legacy_price_notes=True)]
            # A legacy manual default without adjustment rows is not source evidence.
            if raw.row('主座椅调节方式', '副座椅调节方式') is not None:
                previous.append(legacy_summary(raw, source_i))
            if seat and i < len(seat.values) and old in previous:
                seat.values[i] = from_raw(raw, source_i)
        except errors:
            _, notes = _notes(str(old or ''))
            supports = {no: support_from_text(notes, feature) for no, feature in ((46, '腿托'), (47, '腰托'))}
            recovered = True
        for no in values:
            values[no].append(supports[no])
    for no, feature in ((46, '腿托'), (47, '腰托')):
        if no not in items:
            ladder.items.append(LadderItem(no=no, name='座椅'+feature, values=values[no],
                note='旧文件仅从座椅调节附注恢复；未记录按无配置比较' if recovered else '从原始配置独立记录；不计入座椅调节方向'))
    return ladder
