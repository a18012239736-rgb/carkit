"""pjy 确认的主要气囊口径；按来源标配位置计数，不预设最低数量。"""
import re
from .models import Cell


DRIVER_ROWS = ('主/副驾驶座安全气囊',)
SIDE_ROWS = ('前/后排侧气囊',)
HEAD_ROWS = ('前/后排头部气囊(气帘)', '前/后排头部气囊（气帘）')
MIDDLE_ROWS = ('前排中间气囊', '前排中央气囊', '前排中央安全气囊', '中央安全气囊')
KNEE_ROWS = ('膝部气囊', '主驾膝部气囊', '副驾膝部气囊', '主驾驶膝部气囊', '副驾驶膝部气囊')
SOURCE_ROWS = DRIVER_ROWS + SIDE_ROWS + HEAD_ROWS + MIDDLE_ROWS + KNEE_ROWS
_DRIVER_POSITION = r'(主|副)(?:驾驶座|驾驶|驾)?(?:安全气囊|膝部气囊)?'
_ROW_POSITION = r'(前|后)(?:排)?(?:侧气囊|头部气囊(?:[（(]气帘[）)])?|气帘)?'


def _parts(cell):
    return [cell] + list(cell.subs) if cell is not None else []


def _standard(part):
    text = (part.text or '').strip()
    return part.dot == '●' and '[待' not in text and not text.startswith('○') and text not in ('?', '-', '—', '无', '✕')


def _positions(cell, pattern, order):
    if cell is None:
        return []
    positions = set()
    for part in _parts(cell):
        text = part.text or ''
        if '[待' in text:
            continue
        for match in re.finditer(pattern + r'\s*[:：]?\s*([●○✕×-]?)', text):
            position, marker = match.groups()
            if marker == '●' or (not marker and _standard(part)):
                positions.add(position)
    return [position for position in order if position in positions]


def side_positions(cell):
    return _positions(cell, _ROW_POSITION, ('前', '后'))


def _cells(raw, names, i):
    return [(row.name, row.cells[i]) for row in raw.rows if row.name in names and i < len(row.cells)]


def _knee_components(raw, i):
    positions, mentioned, generic = set(), set(), False
    for name, cell in _cells(raw, KNEE_ROWS, i):
        for part in _parts(cell):
            text = part.text or ''
            # A dedicated row supplies the position when its cell is only ●.
            if name != '膝部气囊' and not re.search(_DRIVER_POSITION, text):
                text = name + text
            mentioned.update(re.findall(_DRIVER_POSITION, text))
            positions.update(_positions(Cell(dot=part.dot, text=text), _DRIVER_POSITION, ('主', '副')))
            if not re.search(_DRIVER_POSITION, text) and _standard(part):
                generic = True
    # A blank parent marker is not a third item above its named children.
    if positions:
        return [pos + '驾膝部气囊' for pos in ('主', '副') if pos in positions]
    return ['膝部气囊'] if generic and not mentioned else []


def from_raw(raw, i):
    """返回 (数量, 组成)，同一位置/同类别名不重复计；○ 不计。"""
    count, components = 0, []
    for rows, pattern, order, per_position, labels in (
        (DRIVER_ROWS, _DRIVER_POSITION, ('主', '副'), 1, {'主': '主驾', '副': '副驾'}),
        (SIDE_ROWS, _ROW_POSITION, ('前', '后'), 2, {'前': '前侧', '后': '后侧'}),
        (HEAD_ROWS, _ROW_POSITION, ('前', '后'), 1, {'前': '前气帘', '后': '后气帘'}),
    ):
        positions = {pos for _, cell in _cells(raw, rows, i) for pos in _positions(cell, pattern, order)}
        count += per_position * len(positions)
        components.extend(['主副'] if rows == DRIVER_ROWS and len(positions) == 2
                          else [labels[pos] for pos in order if pos in positions])
    if any(_standard(part) for _, cell in _cells(raw, MIDDLE_ROWS, i) for part in _parts(cell)):
        count += 1
        components.append('中央气囊')
    knees = _knee_components(raw, i)
    return count + len(knees), components + knees
