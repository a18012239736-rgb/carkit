import pytest

from engine import stage_one
from engine.differ import _cmp_generic, ambient_level
from engine.mapper import legacy_mapped_item, map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules
from engine.valuer import _default_rule_amount, dynamic_delta

def test_equivalent_multicolor_values():
    for a,b in [('256色氛围灯','多色(256色)'),('64色','256色'),('多色','128色')]:
        assert _cmp_generic(39,{},a,b) == ('同','多色','多色')
        assert _default_rule_amount(39,f'{a}（{b}）','less') == 0
    assert _cmp_generic(39,{},'单色','256色') == ('少','单色','多色')
    assert _default_rule_amount(39,'单色(256色)','less') == 400


@pytest.mark.parametrize('source, expected', [
    ('1680万色', '多色'), ('1600万色', '多色'), ('1万色', '多色'),
    ('256色', '多色'), ('64色', '多色'), ('双色', '多色'),
    ('多色', '多色'), ('单色', '单色'), ('1色', '单色'),
])
def test_captured_ambient_colors_are_canonical_in_editor_and_stage(source, expected):
    raw = RawTable(trims=[Trim(0, '测试')], rows=[
        RawRow('车内环境氛围灯', [Cell(dot='●', text=source)]),
        RawRow('主动式环境氛围灯', [Cell(dot='●')]),
    ])
    original = raw.to_json()
    mapped = map_raw_to_ladder(raw, Rules())
    assert mapped[39]['values'] == [expected]
    feature = next(item for item in stage_one.features(raw, excluded_rows=[]) if item['key'] == '氛围灯')
    assert feature['values'] == [[expected+'氛围灯', '主动式环境氛围灯']]
    assert raw.to_json() == original
    # Existing monetary tiers do not depend on how many colors the source lists.
    assert _default_rule_amount(39, '', 'more', values=(expected, '✕')) == (600 if expected == '多色' else 200)


def test_standard_ambient_subitem_does_not_take_the_optional_color_tier():
    raw = RawTable(trims=[Trim(0, '测试')], rows=[
        RawRow('车内环境氛围灯', [Cell(dot='○', text='1680万色', subs=[Cell(dot='●', text='单色')])]),
    ])
    assert map_raw_to_ladder(raw, Rules())[39]['values'] == ['单色']
    assert stage_one.features(raw, excluded_rows=[])[0]['values'] == [['单色氛围灯']]
    assert legacy_mapped_item(raw, 0, 39) == {'value': '○(选装)'}


def test_ambient_absent_optional_and_unspecified_source_are_not_invented():
    raw = RawTable(trims=[Trim(i, str(i)) for i in range(3)], rows=[
        RawRow('车内环境氛围灯', [Cell(text='-'), Cell(dot='○', text='256色'), Cell(dot='●')]),
    ])
    assert map_raw_to_ladder(raw, Rules())[39]['values'] == ['✕', '○(选装)', '●']
    assert stage_one.features(raw, excluded_rows=[])[0]['values'] == [[], [], ['氛围灯']]


def test_old_ambient_automatic_value_is_frozen_for_precise_cache_migration():
    raw = RawTable(trims=[Trim(0, '测试')], rows=[
        RawRow('车内环境氛围灯', [Cell(dot='●', text='1680万色')]),
    ])
    assert legacy_mapped_item(raw, 0, 39) == {'value': '多色(1680色)'}
    assert map_raw_to_ladder(raw, Rules())[39]['values'] == ['多色']


@pytest.mark.parametrize('value, level', [
    ('无', 0), ('无氛围灯', 0), ('✕', 0), ('单色', 1), ('1色', 1),
    ('多色', 2), ('256色', 2), ('1680万色氛围灯', 2), ('1600万色', 2),
    ('1万色', 2), ('0.8万色', 2), ('1亿色', 2), ('两色', 2), ('双色', 2),
    ('○1680万色', 0), ('○两色', 0), ('多色(选装)', 0),
    ('单色(○1680万色选装)', 1), ('单色（○1600万色选装）', 1),
    ('●', 1), ('有', 1), ('氛围灯', 1),
])
def test_direct_or_ppt_ambient_values_use_the_same_monetary_classification(value, level):
    assert ambient_level(value) == level
    assert _default_rule_amount(39, '', 'more', values=(value, '✕')) == [0, 200, 600][level]
    assert _default_rule_amount(39, '', 'more', {'single': 300, 'multi': 900}, values=(value, '✕')) == [0, 300, 900][level]


def test_ambient_multicolor_units_preserve_positive_negative_custom_amounts():
    for multi in ('1680万色氛围灯', '1600万色', '256色', '两色'):
        assert _cmp_generic(39, {}, multi, '单色') == ('多', '多色', '单色')
        assert _cmp_generic(39, {}, '单色', multi) == ('少', '单色', '多色')
        assert dynamic_delta(39, multi, '单色') == 400
        assert dynamic_delta(39, '单色', multi) == -400
        assert dynamic_delta(39, multi, '单色', {'single': 300, 'multi': 900}) == 600
        assert dynamic_delta(39, '单色', multi, {'single': 300, 'multi': 900}) == -600
        assert dynamic_delta(39, multi, '多色') == 0
