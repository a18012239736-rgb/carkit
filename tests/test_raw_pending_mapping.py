"""Unknown source cells survive mapping; only confirmed seat subitems are priced."""
import pytest

from engine import differ, valuer
from engine.ladder import build_ladder
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.seat_functions import SUBS, from_text


RULES = Rules()
VALUATION = ValuationTable(items=[ValuationItem(**item)
                                 for item in valuer.default_valuation(RULES)['items']])


def source(rows):
    return RawTable(trims=[Trim(0, '测试版')], rows=[
        RawRow(name=name, cells=[cell]) for name, cell in rows.items()
    ])


def compare(left, right, no):
    pair = {'self_trim': '测试版', 'comp_trim': '测试版'}
    cells = differ.diff(left, right, [pair], RULES, valuation=VALUATION)
    group = differ.assemble_backup(cells, [pair], left.model, right.model,
                                   {'测试版': 10}, {'测试版': 10}, VALUATION)[0]
    return next(cell for cell in cells if cell['no'] == no), group['valuation']


@pytest.mark.parametrize('unknown', ['[待定]', '?'])
@pytest.mark.parametrize('row,no,known', [
    ('方向盘材质', 25, '仿皮'),
    ('座椅材质', 34, '仿皮'),
    ('内后视镜功能', 31, '流媒体'),
    ('液晶仪表尺寸', 29, '10寸仪表'),
    ('辅助驾驶路段', 9, '高速NOA'),
    ('辅助驾驶系统', 9, '基础L2'),
    ('辅助驾驶等级', 9, '基础L2'),
    ('巡航系统', 9, '定速巡航'),
])
def test_raw_unknown_scalar_is_not_mapped_as_presence_or_absence(row, no, known, unknown):
    left = build_ladder(source({row: Cell(dot='●', text=unknown)}), RULES)
    left = Ladder.from_dict(left.to_dict())
    right = Ladder(trims=[{'name': '测试版'}], items=[LadderItem(no=no, name=row, values=[known])])
    assert '[待定]' in left.item(no).values[0]
    for a, b in ((left, right), (right, left)):
        cell, result = compare(a, b, no)
        assert cell['verdict'] == '不计' and cell['exempt_id'] == 'pending'
        assert not any(row['no'] == no for row in result['detail'])
        assert result['config_adv'] == 0


@pytest.mark.parametrize('row,no,known', [
    ('方向盘材质', 25, '仿皮'),
    ('座椅材质', 34, '仿皮'),
    ('内后视镜功能', 31, '自动防眩目'),
    ('液晶仪表尺寸', 29, '10寸仪表'),
    ('辅助驾驶路段', 9, '高速NOA'),
])
def test_confirmed_standard_subitem_wins_over_unknown_or_optional_siblings(row, no, known):
    text = '10英寸' if no == 29 else '高速路段' if no == 9 else known
    raw = source({row: Cell(dot='●', text='[待定]', subs=[
        Cell(dot='●', text=text), Cell(dot='○', text='[待定]选装'),
    ])})
    assert map_raw_to_ladder(raw, RULES)[no]['values'] == [known]


@pytest.mark.parametrize('rows,confirmed', [
    ({'全液晶仪表盘': Cell(dot='●'), '液晶仪表尺寸': Cell(dot='●', text='[待定]')}, '全液晶'),
    ({'全液晶仪表盘': Cell(dot='●', text='[待定]'), '液晶仪表尺寸': Cell(dot='●', text='10英寸')}, '10寸'),
])
def test_instrument_unknown_size_or_type_stays_pending_and_keeps_known_attribute(rows, confirmed):
    left = build_ladder(source(rows), RULES)
    assert confirmed in left.item(29).values[0]
    assert '[待定]' in left.item(29).values[0]
    right = Ladder(trims=[{'name': '测试版'}], items=[LadderItem(no=29, name='仪表', values=['10寸全液晶仪表'])])
    assert compare(left, right, 29)[0]['verdict'] == '不计'


def test_confirmed_l2_does_not_turn_unknown_or_optional_route_into_noa():
    raw = source({'辅助驾驶等级': Cell(dot='●', text='L2'),
                  '辅助驾驶路段': Cell(dot='●', text='[待定]城市路段',
                                       subs=[Cell(dot='○', text='高速路段')])})
    assert map_raw_to_ladder(raw, RULES)[9]['values'] == ['基础L2']


@pytest.mark.parametrize('row,no', [('方向盘材质', 25), ('座椅材质', 34), ('内后视镜功能', 31)])
def test_optional_pending_source_does_not_become_unknown_standard_equipment(row, no):
    left = build_ladder(source({row: Cell(dot='○', text='[待定]')}), RULES)
    right = Ladder(trims=[{'name': '测试版'}], items=[LadderItem(no=no, name=row, values=['✕'])])
    assert left.item(no).values == ['○(选装)']
    assert compare(left, right, no)[1]['config_adv'] == 0


def seat_ladder(states):
    return Ladder(trims=[{'name': '测试版'}], items=[LadderItem(no=36, name='座椅功能', values=['座椅功能'],
                  subs=[{'sub': sub, 'values': [states[sub]]} for sub in SUBS])])


def test_only_unknown_driver_ventilation_is_excluded_while_confirmed_heating_is_priced():
    raw = source({'前排座椅功能': Cell(dot='●', text='加热', subs=[
        Cell(dot='●', text='[待定]通风(仅驾驶位)'),
        Cell(dot='○', text='按摩(仅副驾驶位)'),
    ])})
    left = Ladder.from_dict(build_ladder(raw, RULES).to_dict())
    states = {row['sub']: row['values'][0] for row in left.item(36).subs}
    assert states['主驾加热'] == states['副驾加热'] == '●'
    assert states['主驾通风'].startswith('[待定]')
    assert states['副驾通风'] == states['副驾按摩'] == '✕'
    assert '加热' in left.item(36).values[0] and '[待定]' in left.item(36).values[0]
    right = seat_ladder(from_text('主驾通风'))
    for a, b, amount in ((left, right, 500), (right, left, -500)):
        cell, result = compare(a, b, 36)
        assert result['config_adv'] == amount
        assert '主驾通风' in cell['display'] and '待核对' in cell['display']


@pytest.mark.parametrize('row,text,keys', [
    ('前排座椅功能', '[待定]通风', ['主驾通风', '副驾通风']),
    ('第二排座椅功能', '[待定]加热', ['二排加热']),
    ('前排座椅头枕扬声器', '[待定]驾驶位', ['主驾头枕音响']),
    ('前排座椅功能', '[待定]', [sub for sub in SUBS if not sub.startswith('二排')]),
])
def test_pending_seat_scope_excludes_only_its_related_subitems(row, text, keys):
    left = build_ladder(source({row: Cell(dot='●', text=text)}), RULES)
    states = {row['sub']: row['values'][0] for row in left.item(36).subs}
    assert {key for key, state in states.items() if '[待定]' in state} == set(keys)
    right = seat_ladder({sub: '●' if sub in keys else '✕' for sub in SUBS})
    assert compare(left, right, 36)[1]['config_adv'] == 0


def test_confirmed_seat_function_wins_over_unknown_sibling_and_optional_pending_is_ignored():
    raw = source({'前排座椅功能': Cell(dot='●', text='通风', subs=[
        Cell(dot='●', text='[待定]通风(仅驾驶位)'),
        Cell(dot='○', text='[待定]加热'),
    ])})
    item = map_raw_to_ladder(raw, RULES)[36]
    assert item['values'] == ['前排通风(主副)']
    states = {row['sub']: row['values'][0] for row in item['subs']}
    assert states['主驾通风'] == states['副驾通风'] == '●'
    assert states['主驾加热'] == states['副驾加热'] == '✕'
