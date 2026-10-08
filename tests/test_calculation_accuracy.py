import pytest

from engine.differ import assemble_backup, diff
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim, ValuationItem, ValuationTable
from engine.mapper import map_raw_to_ladder
from engine.rules import Rules
from engine.valuer import default_valuation, normalize_valuation


def compare(no, left, right, params=None, *, reverse=False):
    rules = Rules()
    data = default_valuation(rules)
    next(item for item in data['items'] if item['no'] == no)['params'].update(params or {})
    table = ValuationTable(items=[ValuationItem(**item) for item in normalize_valuation(data, rules)['items']])
    if reverse:
        left, right = right, left
    ours = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=no, name='配置', values=[left])])
    theirs = Ladder(trims=[{'name': 'B'}], items=[LadderItem(no=no, name='配置', values=[right])])
    pairs = [{'self_trim': 'A', 'comp_trim': 'B'}]
    cells = diff(ours, theirs, pairs, rules, valuation=table)
    prices = (11, 10) if reverse else (10, 11)
    group = assemble_backup(cells, pairs, '本品', '竞品', {'A': prices[0]}, {'B': prices[1]}, table)[0]
    return next(cell for cell in cells if cell['no'] == no), group


@pytest.mark.parametrize('no,left,right,expected', [
    (31, '流媒体', '手动防眩目', 1000),
    (29, '全液晶10寸仪表', '10寸仪表', 200),
    (29, '全液晶仪表(10寸)', '10寸仪表', 200),
    (36, {'主驾通风': '●', '副驾通风': '●'}, {'主驾按摩': '●'}, 200),
    (36, {'主驾加热': '●', '二排加热': '●'}, {}, 500),
    (35, '主驾10向电调+副驾4向手调', '主驾6向电调+副驾4向手调', 200),
    (35, '主6副4电调', '主6副4手调', 800),
    (35, '主驾10向电动(腰撑4向)+副驾4向手动', '主驾6向电调+副驾4向手调', 200),
    (35, '主驾6向电调+副驾4向电调', '主驾6向电调+副驾4向手调', 400),
])
def test_configuration_net_value_and_reversing_both_sides(no, left, right, expected):
    for reverse, sign in ((False, 1), (True, -1)):
        cell, group = compare(no, left, right, reverse=reverse)
        result = group['valuation']
        assert cell['verdict'] == ('多' if sign == 1 else '少')
        assert result['config_adv'] == sign * expected
        assert result['flat_adv'] == sign * (expected + 10000)
        assert result['detail'][0]['amount'] == sign * expected


@pytest.mark.parametrize('no,left,right,params,expected', [
    (4, 'R17钢轮毂', 'R16铝轮毂', {'per_inch': 100, 'alloy_bonus': 500}, -400),
    (25, '真皮', '仿皮', {'leather': 100, 'faux': 500}, -400),
    (36, {'主驾通风': '●'}, {'主驾加热': '●'}, {'ventilation': 100, 'heating': 800}, -700),
    (36, {'主驾加热': '●', '副驾加热': '●'},
     {'主驾通风': '●', '副驾头枕音响': '●'}, {'heating': 100}, -300),
])
def test_custom_values_control_direction_and_formerly_equal_configs(no, left, right, params, expected):
    for reverse, sign in ((False, 1), (True, -1)):
        cell, group = compare(no, left, right, params, reverse=reverse)
        assert cell['verdict'] == ('少' if sign == 1 else '多')
        assert group['valuation']['config_adv'] == sign * expected


@pytest.mark.parametrize('no,left,right,expected,verdict', [
    (31, '○流媒体(选装)', '手动防眩目', 0, '同'),
    (31, '流媒体', '○流媒体(选装)', 1000, '多'),
    (29, '全液晶10寸仪表', '10寸仪表(○全液晶选装)', 200, '多'),
    (29, '○12寸全液晶仪表', '10寸仪表', -1000, '少'),
    (35, '○主驾10向电调+副驾4向手调', '主驾6向电调+副驾4向手调', -900, '少'),
    (36, {'主驾通风': '○'}, {}, 0, '同'),
    (36, {'主驾通风': '[待定]'}, {}, 0, '同'),
    (31, '[待定]流媒体', '流媒体', 0, '不计'),
    (35, '不适用', '主驾6向电调+副驾4向手调', 0, '不计'),
    (1, '350km', '450km', 0, '豁免'),
])
def test_optional_pending_and_exempt_configs_keep_their_policy(no, left, right, expected, verdict):
    cell, group = compare(no, left, right)
    assert cell['verdict'] == verdict
    assert group['valuation']['config_adv'] == expected


def test_structured_calculation_ignores_summary_wording():
    rules = Rules()
    table = ValuationTable(items=[ValuationItem(**item) for item in default_valuation(rules)['items']])
    pairs = [{'self_trim': 'A', 'comp_trim': 'B'}]
    left = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=29, name='仪表', values=['全液晶10寸'])])
    right = Ladder(trims=[{'name': 'B'}], items=[LadderItem(no=29, name='仪表', values=['10寸'])])
    cells = diff(left, right, pairs, rules, valuation=table)
    next(cell for cell in cells if cell['no'] == 29)['backup_more'] = '本品仪表有升级'
    result = assemble_backup(cells, pairs, '本品', '竞品', {'A': 10}, {'B': 10}, table)[0]['valuation']
    assert result['config_adv'] == 200


def test_explicit_source_seat_directions_and_modes_reach_the_calculation():
    values = []
    for total in (10, 6):
        raw = RawTable(trims=[Trim(idx=0, short='测试')], rows=[
            RawRow(name='主座椅调节方式', cells=[Cell(dot='●', text=f'主驾{total}向电动')]),
            RawRow(name='副座椅调节方式', cells=[Cell(dot='●', text='副驾4向手动')]),
            RawRow(name='主/副驾驶座电动调节', cells=[Cell(dot='●', text='主●/副-')]),
        ])
        values.append(map_raw_to_ladder(raw, Rules())[35]['values'][0])
    assert values == ['主驾10向电调+副驾4向手调', '主驾6向电调+副驾4向手调']
    cell, group = compare(35, *values)
    assert cell['verdict'] == '多'
    assert group['valuation']['config_adv'] == 200


def test_explicit_source_seat_modes_are_independent():
    raw = RawTable(trims=[Trim(idx=0, short='测试')], rows=[
        RawRow(name='主座椅调节方式', cells=[Cell(dot='●', text='6向调节')]),
        RawRow(name='副座椅调节方式', cells=[Cell(dot='●', text='4向调节')]),
        RawRow(name='主/副驾驶座电动调节', cells=[Cell(dot='●', text='主●/副-')]),
    ])
    assert map_raw_to_ladder(raw, Rules())[35]['values'][0] == '主驾6向电调+副驾4向手调'
