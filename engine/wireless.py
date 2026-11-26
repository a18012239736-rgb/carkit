"""无线充电按明确位置/数量与快慢充计价，不把功率当数量。"""
import re


def units(value):
    text = str(value or '').strip()
    if (text.startswith('○')
            or text in ('', '✕', '×', 'X', '-', '—', '无', '无配置', '不适用', '选装', '选配')
            or re.search(r'[（(]\s*(?:选装|选配)\s*[)）]\s*$', text)
            or '[待' in text):
        return []
    text = re.sub(r'[（(][^()（）]*(?:○|选装|选配)[^()（）]*[)）]', '', text)
    positions = list(re.finditer(r'前排|后排|二排', text))
    shared = text[:positions[0].start()] if positions else text
    power = re.search(r'(\d+(?:\.\d+)?)\s*W', shared, re.I)
    common = ('slow' if '慢充' in shared else 'fast' if '快充' in shared else
              ('fast' if float(power[1]) >= 40 else 'slow') if power else 'unknown')
    result = []
    for index, match in enumerate(positions or [None]):
        if match:
            prefix = text[positions[index - 1].end() if index > 0 else 0:match.start()]
            if re.search(r'○\s*$', prefix):
                continue
        segment = text[match.end():positions[index+1].start() if index+1 < len(positions) else len(text)] if match else text
        if match and index + 1 < len(positions):
            segment = re.sub(r'[+＋/／,，、\s]*○\s*$', '', segment)
        if '○' in segment or re.match(r'^\s*[●]?\s*(?:✕|×|-|无)', segment):
            continue
        watts = re.search(r'(\d+(?:\.\d+)?)\s*W', segment, re.I)
        kind = ('slow' if '慢充' in segment else 'fast' if '快充' in segment else
                ('fast' if float(watts[1]) >= 40 else 'slow') if watts else common)
        count = re.search(r'(\d+)\s*(?:个|处)', segment)
        number = int(count[1]) if count else 2 if '双' in segment else 1
        position = match[0].replace('二排', '后排') if match else ''
        result.append((position, number, kind))
    return result


def label(value, suffix='手机无线充电'):
    parsed = units(value)
    if not parsed:
        return str(value or '✕')
    return _label_units(parsed, suffix)


def _label_units(parsed, suffix):
    return '+'.join(position + ('双' if count == 2 else f'{count}个' if count != 1 else '')
                    + ('50W' if kind == 'fast' else '慢充' if kind == 'slow' else '')
                    + suffix for position, count, kind in parsed)


def source_label(positions, power='', suffix='手机无线充电'):
    """Power rows describe existing positions, never additional chargers."""
    parsed = units(positions)
    power_units = units(power)
    if len(parsed) == 1 and parsed[0][0] == '' and parsed[0][2] == 'unknown' and any(p[0] for p in power_units):
        count = parsed[0][1]
        if len(power_units) == 1 and count > 1 and power_units[0][1] == 1:
            combined = [(power_units[0][0], count, power_units[0][2])]
        else:
            combined = power_units
        return _label_units(combined, suffix)
    powers = {position: kind for position, _, kind in power_units}
    combined = [(position, count, powers.get(position, powers.get('', kind)))
                for position, count, kind in parsed]
    return _label_units(combined, suffix)


def amount(value, fast=350, slow=100):
    # Unspecified power retains the previous unit price, never a fabricated 50W.
    return sum(count * (slow if kind == 'slow' else fast) for _, count, kind in units(value))
