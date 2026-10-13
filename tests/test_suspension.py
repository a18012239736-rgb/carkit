"""Air/magic-carpet aliases share the two existing capability prices."""
import pytest

from engine.mapper import legacy_mapped_item, map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules
from engine.valuer import _default_rule_amount, dynamic_delta
from test_calculation_accuracy import compare


def mapped(rows):
    raw = RawTable(trims=[Trim(idx=0, short='源格回归')], rows=[
        RawRow(name=name, cells=[cell]) for name, cell in rows.items()
    ])
    return raw, map_raw_to_ladder(raw, Rules())[6]['values'][0]


@pytest.mark.parametrize('name,expected', [
    ('空气悬架', '●空气悬架'), ('魔毯智能悬架', '●魔毯悬架'),
])
def test_air_and_magic_carpet_sources_use_soft_hard_plus_height(name, expected):
    _, value = mapped({name: Cell(dot='●')})
    assert value == expected
    assert dynamic_delta(6, value, '✕') == 9000


def test_parent_soft_hard_and_standard_height_child_are_both_kept():
    raw, value = mapped({'可变悬架功能': Cell(dot='●', text='悬架软硬调节', subs=[
        Cell(dot='●', text='悬架高低调节'),
    ])})
    assert value == '●软硬调节+高低调节'
    assert legacy_mapped_item(raw, 0, 6) == {'value': '●软硬调节'}
    assert dynamic_delta(6, value, '✕') == 9000
    # Two functions alone do not establish the source's brand/type name.
    assert '魔毯' not in value and '空气' not in value


def test_standard_head_and_optional_air_child_do_not_promote_optional_height():
    _, value = mapped({'可变悬架功能': Cell(dot='●', text='悬架软硬调节', subs=[
        Cell(dot='○', text='空气悬架 (20000元)'),
    ])})
    assert value == '●软硬调节(○空气悬架选装)'
    assert dynamic_delta(6, value, '✕') == 1000
    assert dynamic_delta(6, value, '软硬调节') == 0


def test_optional_parent_standard_height_child_uses_its_own_marker():
    _, value = mapped({'可变悬架功能': Cell(dot='○', text='悬架软硬调节', subs=[
        Cell(dot='●', text='悬架高低调节'),
    ])})
    assert value == '●高低调节(○软硬调节选装)'
    assert dynamic_delta(6, value, '✕') == 8000


@pytest.mark.parametrize('name', ['空气悬架', '魔毯智能悬架', '可变悬架功能'])
def test_optional_only_sources_are_not_priced_as_standard(name):
    _, value = mapped({name: Cell(dot='○', text='' if name != '可变悬架功能' else '悬架软硬调节')})
    assert value.startswith('○')
    assert dynamic_delta(6, value, '✕') == 0
    assert _default_rule_amount(6, value, 'more') == 0


def test_redundant_air_magic_and_capability_rows_are_not_counted_twice():
    raw, value = mapped({'空气悬架': Cell(dot='●'), '魔毯智能悬架': Cell(dot='●'),
                        '可变悬架功能': Cell(dot='●', text='悬架软硬调节', subs=[
                            Cell(dot='●', text='悬架高低调节')])})
    assert value == '●魔毯悬架'
    assert legacy_mapped_item(raw, 0, 6) == {'value': '●魔毯悬架'}
    assert dynamic_delta(6, value, '软硬调节+高低调节') == 0


@pytest.mark.parametrize('left,right,expected', [
    ('魔毯悬架', '软硬调节', 8000),
    ('空气悬架', '✕', 9000),
    ('魔毯悬架', '空气悬架', 0),
    ('空气悬架', '软硬调节+高低调节', 0),
    ('●软硬调节(○高低调节选装)', '✕', 1000),
    ('软硬调节+○高低调节', '软硬调节', 0),
])
def test_manual_ppt_aliases_and_both_directions_reach_the_comparison(left, right, expected):
    for reverse, sign in ((False, 1), (True, -1)):
        cell, group = compare(6, left, right, reverse=reverse)
        assert cell['verdict'] == ('同' if expected == 0 else '多' if sign > 0 else '少')
        assert group['valuation']['config_adv'] == sign * expected
        assert dynamic_delta(6, right if reverse else left, left if reverse else right) == sign * expected


@pytest.mark.parametrize('params,expected', [
    ({'soft_hard': 200, 'height_or_air': 1500}, 1500),
    ({'soft_hard': 0, 'height_or_air': 0}, 0),
])
def test_custom_parameters_control_suspension_money_and_verdict(params, expected):
    cell, group = compare(6, '魔毯悬架', '软硬调节', params)
    assert cell['verdict'] == ('多' if expected else '同')
    assert group['valuation']['config_adv'] == expected
