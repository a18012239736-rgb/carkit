"""MG 07 live-source regression; raw fixture is a subset of the 2026-10-10 capture.

Source: https://www.autohome.com.cn/config/series/8563.html
The 10-direction fallback for MG 07 zero-gravity seats was confirmed by pjy.
"""
from pathlib import Path

import pytest

from engine import seat_adjust, stage_one
from engine.mapper import map_raw_to_ladder, n_sunroof
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules
from engine.valuer import dynamic_delta


def mg07():
    return RawTable.load(Path(__file__).parent / 'golden' / 'raw-MG07-terms-2026-10-10.json')


def source(rows, model='MG 07', series='8563'):
    return RawTable(model=model, series_id=series, trims=[Trim(0, '版型')],
                    rows=[RawRow(name=name, cells=[cell]) for name, cell in rows.items()])


def test_live_roof_and_seat_terms_are_visible_but_never_double_priced():
    raw = mg07()
    mapped = map_raw_to_ladder(raw, Rules())
    features = {f['key']: f['values'] for f in stage_one.features(raw)}
    for i in range(7):
        flagship = i in (4, 6)
        roof, seat = mapped[18]['values'][i], mapped[35]['values'][i]
        assert ('光感天幕' in roof) == flagship
        assert ('副驾零重力座椅' in seat) == flagship
        assert features['天窗类型'][i] == ['不可开启全景天窗']
        assert features['光感天幕'][i] == (['光感天幕'] if flagship else [])
        assert features['零重力座椅'][i] == (['副驾驶零重力座椅'] if flagship else [])
        assert '零重力' not in ''.join(features['副驾座椅调节'][i])
        parsed = seat_adjust.parse(seat)
        assert parsed['editable']
        assert parsed['seats'][0]['count'] == 6
        assert parsed['seats'][1]['count'] == (10 if flagship else 4)
        assert [s['mode'] for s in parsed['seats']] == ['电调', '电调']
        # Labels explain the source; the existing direction and roof rules still apply.
        assert dynamic_delta(18, roof, n_sunroof(raw, i, {}, include_terms=False)) == 0
        assert dynamic_delta(35, seat, seat_adjust.from_raw(raw, i, include_terms=False)) == 0
    assert dynamic_delta(35, mapped[35]['values'][4], mapped[35]['values'][3]) == 300
    assert not mapped[18]['row_absent'] and not mapped[35]['row_absent']


def test_live_new_literal_row_aliases_preserve_value_and_seat_scope():
    raw = mg07()
    mapped = map_raw_to_ladder(raw, Rules())
    assert mapped[3]['values'] == ['●400V'] * 5 + ['●800V'] * 2
    assert mapped[45]['values'] == ['主驾座椅记忆'] * 4 + ['前排座椅记忆', '主驾座椅记忆', '前排座椅记忆']
    assert dynamic_delta(45, mapped[45]['values'][4], mapped[45]['values'][3]) == 100
    features = {f['key']: f['values'] for f in stage_one.features(raw)}
    assert features['高压平台'] == [['400V']] * 5 + [['800V']] * 2
    assert features['电动座椅记忆'][4] == ['主驾座椅记忆', '副驾座椅记忆']
    assert features['电动座椅记忆'][3] == ['主驾座椅记忆']


@pytest.mark.parametrize('dot,expected', [('●', '●不可开启全景(光感天幕)'),
                                          ('○', '○不可开启全景(光感天幕)(选装)'), ('', '✕')])
def test_roof_brand_row_alone_is_a_known_type_not_a_new_pricing_item(dot, expected):
    raw = source({'光感天幕': Cell(dot=dot)})
    mapped = map_raw_to_ladder(raw, Rules())
    assert mapped[18]['values'] == [expected]
    assert not mapped[18]['row_absent']
    feature = next(f for f in stage_one.features(raw) if f['key'] == '光感天幕')
    assert bool(feature['values'][0]) == (dot == '●')
    if dot == '○':
        assert stage_one._option_lines(raw, 0) == ['光感天幕']


def test_roof_brand_inside_type_and_optional_subitems_are_recognized():
    raw = source({'天窗类型': Cell(dot='○', text='可开启全景天窗',
        subs=[Cell(dot='●', text='光感天幕')])})
    value = map_raw_to_ladder(raw, Rules())[18]['values'][0]
    assert value == '●不可开启全景(光感天幕)'
    assert dynamic_delta(18, value, '●不可开启全景') == 0


def test_pending_roof_brand_is_not_converted_into_a_standard_type():
    raw = source({'光感天幕': Cell(dot='●', text='[待定]')})
    value = map_raw_to_ladder(raw, Rules())[18]['values'][0]
    assert value.startswith('[待定]')
    assert dynamic_delta(18, value, '✕') == 0
    raw.rows.insert(0, RawRow(name='天窗类型', cells=[Cell(dot='●', text='不可开启全景天窗')]))
    assert map_raw_to_ladder(raw, Rules())[18]['values'] == ['●不可开启全景']


@pytest.mark.parametrize('model,series,count', [('MG 07','8563',10), ('MG07','',10),
                                               ('其他车型','other',None)])
def test_ten_directions_fallback_is_model_specific_and_does_not_guess_power(model, series, count):
    raw = source({'零重力座椅': Cell(dot='●', text='副驾驶')}, model, series)
    counts, modes, positions = seat_adjust.raw_details(raw, 0)
    assert counts == [None, count]
    assert modes == [None, None]
    assert positions == [1]
    assert seat_adjust.from_raw(raw, 0).startswith('[待定]')
    feature = next(f for f in stage_one.features(raw) if f['key'] == '零重力座椅')
    assert feature['values'] == [['副驾驶零重力座椅']]


def test_explicit_directions_win_and_optional_brand_never_changes_standard_count():
    raw = source({'主/副驾驶座电动调节': Cell(dot='●', text='主/副'),
                  '主座椅调节方式': Cell(dot='●', text='6向'),
                  '副座椅调节方式': Cell(dot='●', text='8向'),
                  '零重力座椅': Cell(dot='●', text='副驾驶')})
    assert seat_adjust.raw_details(raw, 0)[0] == [6, 8]
    raw.row('副座椅调节方式').cells[0] = Cell()
    raw.row('零重力座椅').cells[0] = Cell(dot='○', text='副驾驶')
    assert seat_adjust.raw_details(raw, 0)[0] == [6, None]
    assert '零重力' not in seat_adjust.from_raw(raw, 0)
    assert stage_one._option_lines(raw, 0) == ['零重力座椅：副驾驶']


def test_memory_alias_respects_each_subitem_standard_optional_marker():
    raw = source({'电动座椅记忆功能': Cell(dot='○', text='副驾驶位',
        subs=[Cell(dot='●', text='驾驶位')])})
    mapped = map_raw_to_ladder(raw, Rules())
    assert mapped[45]['values'] == ['主驾座椅记忆']
    assert not mapped[45]['row_absent']
    assert '副驾' not in str(next(f for f in stage_one.features(raw) if f['key'] == '电动座椅记忆')['values'])


@pytest.mark.parametrize('cell,expected', [
    (Cell(dot='●', text='后排'), ['后排座椅记忆']),
    (Cell(dot='●', text='主驾', subs=[Cell(dot='●', text='后排')]), ['主驾座椅记忆','后排座椅记忆']),
    (Cell(dot='●', text='前排', subs=[Cell(dot='●', text='后排')]), ['主驾座椅记忆','副驾座椅记忆','后排座椅记忆']),
    (Cell(dot='●', text='主驾', subs=[Cell(dot='○', text='后排')]), ['主驾座椅记忆']),
    (Cell(dot='●', text='主驾●/后排○'), ['主驾座椅记忆']),
    (Cell(dot='●', text='[待定]后排'), ['电动座椅记忆']),
])
def test_ladder_preserves_standard_rear_memory_without_new_rear_pricing(cell, expected):
    raw = source({'电动座椅记忆': cell}, model='其他车型', series='other')
    feature = next(f for f in stage_one.features(raw) if f['key'] == '电动座椅记忆')
    assert feature['values'] == [expected]
    value = map_raw_to_ladder(raw, Rules())[45]['values'][0]
    front_count = sum(v in expected for v in ['主驾座椅记忆', '副驾座椅记忆'])
    if front_count:
        assert dynamic_delta(45, value, '✕') == 100 * front_count
    else:
        # The comparer excludes pending values; preserve the old #45 marker
        # rather than introducing a new rear-seat pricing definition.
        assert value == '[待定]座椅记忆位置未说明'


def test_alias_rows_can_precede_canonical_rows_without_duplication():
    raw = mg07()
    before = stage_one.features(raw)
    names = {'光感天幕', '零重力座椅', '电动座椅记忆功能'}
    raw.rows = [r for r in raw.rows if r.name in names] + [r for r in raw.rows if r.name not in names]
    after = stage_one.features(raw)
    assert {f['key']: f['values'] for f in before} == {f['key']: f['values'] for f in after}
    assert len({f['key'] for f in after}) == len(after)


@pytest.mark.parametrize('text', ['主驾○/副驾●', '副驾驶位'])
def test_embedded_optional_memory_seat_is_not_standard(text):
    raw = source({'电动座椅记忆功能': Cell(dot='●', text=text)})
    assert map_raw_to_ladder(raw, Rules())[45]['values'] == ['副驾座椅记忆']


@pytest.mark.parametrize('name,text', [('零重力座椅','[待定]副驾驶'),
                                      ('电动座椅记忆功能','[待定]驾驶位')])
def test_pending_scope_is_not_converted_into_standard_seats(name, text):
    raw = source({name: Cell(dot='●', text=text)})
    mapped = map_raw_to_ladder(raw, Rules())
    assert mapped[35 if name == '零重力座椅' else 45]['values'][0].startswith('[待定]')
    assert seat_adjust.raw_details(raw, 0)[0] == [None, None]


def test_unknown_gravity_scope_does_not_erase_other_confirmed_adjustments():
    raw = source({'主/副驾驶座电动调节': Cell(dot='●', text='主/副'),
                  '主座椅调节方式': Cell(dot='●', text='6向'),
                  '副座椅调节方式': Cell(dot='●', text='4向'),
                  '零重力座椅': Cell(dot='●')}, model='其他车型', series='other')
    value = seat_adjust.from_raw(raw, 0)
    assert seat_adjust.components(value) == (10, 2)
    assert '零重力座椅座位未说明' in value


@pytest.mark.parametrize('cell', [Cell(dot='○', text='800'), Cell(text='[待定]800'), Cell(text='-')])
def test_voltage_optional_pending_or_absent_never_becomes_standard(cell):
    raw = source({'高压平台（V）': cell})
    assert map_raw_to_ladder(raw, Rules())[3]['values'][0] == '✕'
