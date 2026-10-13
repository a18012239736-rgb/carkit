"""Autohome front-row scope follows pjy's confirmed 2026-10-13 convention."""
import pytest

from engine import seat_adjust, stage_one
from engine.mapper import map_raw_to_ladder, n_seat_func
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules
from engine.seat_functions import from_text
from engine.valuer import dynamic_delta


def source(rows):
    return RawTable(model='前排来源回归', series_id='scope-test', trims=[Trim(0, '测试版')],
                    rows=[RawRow(name=name, cells=[cell]) for name, cell in rows.items()])


def seats(raw):
    return {row['sub']: row['values'][0] for row in map_raw_to_ladder(raw, Rules())[36]['subs']}


@pytest.mark.parametrize('text,expected', [
    ('头枕扬声器', ('●', '●')),
    ('头枕扬声器(主驾驶)', ('●', '✕')),
    ('头枕扬声器(仅驾驶位)', ('●', '✕')),
    ('头枕扬声器(仅副驾驶位)', ('✕', '●')),
])
def test_front_seat_function_row_defaults_to_both_unless_explicitly_restricted(text, expected):
    # L8 / M9 use the unqualified standard front-row headrest-speaker subitem.
    values = seats(source({'前排座椅功能': Cell(dot='●', text=text)}))
    assert (values['主驾头枕音响'], values['副驾头枕音响']) == expected


def test_separate_front_headrest_row_has_known_scope_but_generic_row_does_not():
    values = seats(source({'前排座椅头枕扬声器': Cell(dot='●')}))
    assert values['主驾头枕音响'] == values['副驾头枕音响'] == '●'
    generic = seats(source({'头枕音响': Cell(dot='●', text='头枕音响')}))
    assert all('[待定]' in generic[seat+'头枕音响'] for seat in ('主驾', '副驾'))
    assert '[待定]' in from_text('头枕扬声器')['主驾头枕音响']
    assert from_text('前排头枕音响(仅主驾)')['副驾头枕音响'] == '✕'
    restricted = seats(source({'前排座椅头枕扬声器': Cell(dot='●', text='前排头枕音响（仅驾驶位）')}))
    assert restricted['主驾头枕音响'] == '●' and restricted['副驾头枕音响'] == '✕'


def test_previous_automatic_source_mapping_is_available_for_safe_cache_upgrade():
    raw = source({'前排座椅功能': Cell(dot='●', text='头枕扬声器')})
    old = n_seat_func(raw, 0, {}, assume_front=False)
    assert all('[待定]' in old[2][seat+'头枕音响'] for seat in ('主驾', '副驾'))
    raw.row('前排座椅功能').cells[0].text = '头枕加热'
    old = n_seat_func(raw, 0, {}, assume_front=False)
    assert old[2]['主驾加热'] == old[2]['副驾加热'] == '●'
    assert seats(raw)['主驾加热'] == '✕'


def test_front_headrest_optional_subitem_is_not_promoted_to_standard():
    raw = source({'前排座椅功能': Cell(dot='●', text='加热', subs=[
        Cell(dot='○', text='头枕扬声器(2000元)'),
    ])})
    values = seats(raw)
    assert values['主驾加热'] == values['副驾加热'] == '●'
    assert values['主驾头枕音响'] == values['副驾头枕音响'] == '✕'
    assert stage_one._option_lines(raw, 0, []) == ['前排座椅功能：头枕扬声器(2000元)']


@pytest.mark.parametrize('text,positions', [
    ('第一排', [0, 1]), ('前排', [0, 1]),
    ('第一排(主驾驶)', [0]), ('前排(仅副驾驶位)', [1]),
    ('副驾驶', [1]), ('第二排', []),
])
def test_front_zero_gravity_scope_does_not_change_confirmed_direction_totals(text, positions):
    raw = source({'主/副驾驶座电动调节': Cell(dot='●', text='主/副'),
                  '主座椅调节方式': Cell(dot='●', text='6向'),
                  '副座椅调节方式': Cell(dot='●', text='4向'),
                  '零重力座椅': Cell(dot='●', text=text)})
    counts, modes, actual_positions = seat_adjust.raw_details(raw, 0)
    assert (counts, modes, actual_positions) == ([6, 4], ['电调', '电调'], positions)
    assert seat_adjust.components(seat_adjust.from_raw(raw, 0)) == (10, 2)
    if positions:
        assert '零重力座椅座位未说明' not in seat_adjust.from_raw(raw, 0)
    raw.row('零重力座椅').cells[0] = Cell(dot='○', text=text)
    assert seat_adjust.zero_gravity_positions(raw, 0) == []


def test_previous_seat_mapping_keeps_old_first_row_scope_for_safe_cache_upgrade():
    raw = source({'主/副驾驶座电动调节': Cell(dot='●', text='主/副'),
                  '主座椅调节方式': Cell(dot='●', text='6向'),
                  '副座椅调节方式': Cell(dot='●', text='4向'),
                  '零重力座椅': Cell(dot='●', text='第一排')})
    assert seat_adjust.zero_gravity_positions(raw, 0, legacy_scope=True) == []
    assert '零重力座椅座位未说明' in seat_adjust.from_raw(raw, 0, legacy_price_notes=True)
    assert '零重力座椅座位未说明' not in seat_adjust.from_raw(raw, 0)


@pytest.mark.parametrize('text,heat', [('头枕加热', False), ('加热头枕加热', True)])
def test_headrest_heating_retains_source_word_without_ordinary_seat_heating_price(text, heat):
    # L9 explicitly lists headrest heating, not an ordinary seat heating subitem.
    raw = source({'前排座椅功能': Cell(dot='●', text=text)})
    feature = next(f for f in stage_one.features(raw, excluded_rows=[]) if f['key'] == '前排座椅功能')
    assert '前排座椅功能：头枕加热' in feature['values'][0]
    assert '前排座椅功能：头枕' not in feature['values'][0]
    values = seats(raw)
    assert values['主驾加热'] == values['副驾加热'] == ('●' if heat else '✕')
    assert dynamic_delta(36, values, from_text()) == (500 if heat else 0)
