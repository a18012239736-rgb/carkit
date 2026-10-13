"""pjy confirmed counting rules; use source markers, not a minimum or car price."""
import pytest

from engine.differ import diff
from engine.mapper import map_raw_to_ladder, n_airbag
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.stage_one import features, render
from engine.valuer import default_valuation, value_pair


@pytest.mark.parametrize('name,cell,expected', [
    ('主/副驾驶座安全气囊', Cell(dot='●', text='主●/副●'), 2),
    ('主/副驾驶座安全气囊', Cell(dot='●', text='主●/副-'), 1),
    ('主/副驾驶座安全气囊', Cell(dot='●', text='主/副-'), 1),
    ('主/副驾驶座安全气囊', Cell(dot='●', text='主●/副○ (2000元)'), 1),
    ('主/副驾驶座安全气囊', Cell(dot='○', text='主○/副● (2000元)'), 1),
    ('主/副驾驶座安全气囊', Cell(text='主●/副●'), 2),
    ('主/副驾驶座安全气囊', Cell(subs=[Cell(dot='●', text='主驾'), Cell(dot='●', text='副驾')]), 2),
    ('主/副驾驶座安全气囊', Cell(dot='●', text='主驾', subs=[Cell(dot='○', text='副驾')]), 1),
    ('主/副驾驶座安全气囊', Cell(dot='●', text='[待定]主/副'), 0),
    ('前/后排头部气囊(气帘)', Cell(dot='●', text='前●/后●'), 2),
    ('前/后排头部气囊(气帘)', Cell(dot='●', text='前●/后-'), 1),
    ('前/后排头部气囊(气帘)', Cell(dot='●', text='前/后-'), 1),
    ('前/后排头部气囊(气帘)', Cell(dot='●', text='前●/后○ (2000元)'), 1),
    ('前/后排头部气囊(气帘)', Cell(dot='○', text='前○/后●'), 1),
    ('前/后排头部气囊(气帘)', Cell(subs=[Cell(dot='●', text='前排'), Cell(dot='●', text='后排')]), 2),
    ('前/后排头部气囊(气帘)', Cell(dot='●', text='后排'), 1),
    ('前/后排头部气囊(气帘)', Cell(dot='○', text='前/后'), 0),
    ('前/后排头部气囊(气帘)', Cell(dot='●', text='[待定]前/后'), 0),
    ('前排中间气囊', Cell(dot='●'), 1),
    ('前排中央气囊', Cell(dot='●'), 1),
    ('前排中央安全气囊', Cell(dot='●'), 1),
    ('中央安全气囊', Cell(dot='●'), 1),
    ('前排中间气囊', Cell(dot='○'), 0),
    ('前排中间气囊', Cell(dot='●', text='[待定]'), 0),
    ('膝部气囊', Cell(dot='●', text='主驾膝部气囊', subs=[Cell(dot='●', text='副驾膝部气囊')]), 2),
    ('膝部气囊', Cell(subs=[Cell(dot='●', text='主驾膝部气囊'), Cell(dot='●', text='副驾膝部气囊')]), 2),
    ('膝部气囊', Cell(dot='●', text='主驾膝部气囊', subs=[Cell(dot='○', text='副驾膝部气囊 (2000元)')]), 1),
    ('膝部气囊', Cell(dot='○', text='主驾膝部气囊', subs=[Cell(dot='●', text='副驾膝部气囊')]), 1),
    ('膝部气囊', Cell(dot='●', text='主●/副●'), 2),
    ('膝部气囊', Cell(dot='●'), 1),
    ('膝部气囊', Cell(dot='○', text='主驾膝部气囊'), 0),
    ('膝部气囊', Cell(dot='●', text='[待定]主驾膝部气囊'), 0),
    ('后排中央安全气囊', Cell(dot='●'), 0),
    ('后排防下滑气囊', Cell(dot='●'), 0),
])
def test_major_airbag_markers_have_one_shared_count(name, cell, expected):
    raw = RawTable(trims=[Trim(0, '测试', price_guide=50)], rows=[RawRow(name, [cell])])
    assert n_airbag(raw, 0, {})[0] == expected
    mapped = map_raw_to_ladder(raw, Rules())[5]
    assert mapped['values'] == [expected]
    if name not in ('后排中央安全气囊', '后排防下滑气囊'):
        assert not mapped['row_absent']
    visible = [feature for feature in features(raw, excluded_rows=[]) if feature['key'] == '气囊']
    if expected:
        assert visible[0]['values'] == [[f'{expected}气囊']]
    else:
        assert all(not any('气囊' in value and value[:1].isdigit() for value in feature['values'][0])
                   for feature in visible)


def test_aliases_and_repeated_parent_child_markers_do_not_count_twice():
    raw = RawTable(trims=[Trim(0, '测试')], rows=[
        RawRow(name, [Cell(dot='●', text='有', subs=[Cell(dot='●', text='有')])])
        for name in ('前排中间气囊', '前排中央气囊', '前排中央安全气囊', '中央安全气囊')
    ] + [RawRow('膝部气囊', [Cell(dot='●', text='主驾膝部气囊', subs=[
        Cell(dot='●', text='主驾膝部气囊'), Cell(dot='●', text='副驾膝部气囊')])])])
    assert n_airbag(raw, 0, {})[0] == 3
    assert next(feature for feature in features(raw, excluded_rows=[]) if feature['key'] == '气囊')['values'] == [['3气囊']]


def test_empty_source_has_no_airbag_minimum_even_at_a_high_price():
    raw = RawTable(trims=[Trim(0, '高价', price_guide=100)], rows=[])
    assert n_airbag(raw, 0, {}) == (0, [])
    assert map_raw_to_ladder(raw, Rules())[5]['values'] == [0]
    assert not any(feature['key'] == '气囊' for feature in features(raw, excluded_rows=[]))


def test_unconfirmed_special_airbags_remain_visible_without_invented_quantity():
    names = ['后排中央安全气囊', '后排防下滑气囊']
    raw = RawTable(trims=[Trim(0, '测试', price_guide=10)], rows=[
        RawRow(name, [Cell(dot='●')]) for name in names])
    assert n_airbag(raw, 0, {})[0] == 0
    visible = {feature['key']: feature['values'][0] for feature in features(raw, excluded_rows=[])}
    assert all(visible[name] == [name] for name in names)


def test_mapper_ladder_stage_differ_and_money_use_the_same_standard_count():
    raw = RawTable(model='气囊回归', trims=[Trim(0, '基础', price_guide=10), Trim(1, '增配', price_guide=10)], rows=[
        RawRow('主/副驾驶座安全气囊', [Cell(dot='●', text='主●/副●')] * 2),
        RawRow('前/后排侧气囊', [Cell(dot='○', text='前○/后○ (2000元)'), Cell(dot='●', text='前●/后●')]),
        RawRow('前/后排头部气囊(气帘)', [Cell(dot='●', text='前●/后●')] * 2),
        RawRow('前排中间气囊', [Cell(), Cell(dot='●')]),
        RawRow('前排中央安全气囊', [Cell(), Cell(dot='●')]),
        RawRow('膝部气囊', [Cell(), Cell(dot='●', text='主驾膝部气囊', subs=[Cell(dot='●', text='副驾膝部气囊')])]),
    ])
    rules = Rules()
    mapped = map_raw_to_ladder(raw, rules)[5]
    assert mapped['values'] == [4, 11]
    ladder = Ladder(model=raw.model, trims=[{'name': trim.short, 'price_guide': trim.price_guide} for trim in raw.trims],
                    items=[LadderItem(no=5, name='气囊数量', values=mapped['values'], row_absent=mapped['row_absent'])])
    assert Ladder.from_dict(ladder.to_dict()).item(5).values == [4, 11]
    assert next(feature for feature in features(raw, excluded_rows=[]) if feature['key'] == '气囊')['values'] == [['4气囊'], ['11气囊']]
    markdown = render(raw, [{'target': 0, 'base': None}, {'target': 1, 'base': 0}], excluded_rows=[])
    assert '4气囊' in markdown and '11气囊' in markdown
    valuation = ValuationTable(items=[ValuationItem(**item) for item in default_valuation(rules)['items']])
    for left, right, expected in [('增配', '基础', 2450), ('基础', '增配', -2450), ('增配', '增配', 0)]:
        cells = [cell for cell in diff(ladder, ladder, [{'self_trim': left, 'comp_trim': right}], rules, valuation) if cell['no'] == 5]
        amounts = value_pair({}, {}, 10, 10, valuation, cells=cells)
        assert amounts['config_adv'] == expected
        assert amounts['flat_adv'] == expected
