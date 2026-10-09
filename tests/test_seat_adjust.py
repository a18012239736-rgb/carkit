from pathlib import Path

import pytest

from engine import rawschema, seat_adjust, stage_one
from engine.differ import assemble_backup, diff
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.valuer import _seat_adjust_components, default_valuation, dynamic_delta


@pytest.mark.parametrize('value,counts,modes', [
    ('主副手调', [6, 4], ['手调', '手调']),
    ('主驾手动+副驾手动', [6, 4], ['手调', '手调']),
    ('主驾8向手调+副驾手调', [8, 4], ['手调', '手调']),
    ('主副电调(主含腰撑4向)', [None, None], ['电调', '电调']),
    ('主6副4电调', [6, 4], ['电调', '电调']),
    ('主6向副4向手调', [6, 4], ['手调', '手调']),
    ('主驾电动10向+副驾手动4向', [10, 4], ['电调', '手调']),
    ('主驾10向电动+副驾4向手动', [10, 4], ['电调', '手调']),
    ('主驾10向电动调节/副驾手动调节4向', [10, 4], ['电调', '手调']),
    ('主驾电调+副驾手调', [None, None], ['电调', '手调']),
    ('主驾电调6向+副驾手调', [6, None], ['电调', '手调']),
    ('主驾6向+副驾4向', [6, 4], [None, None]),
])
def test_parse_seats_without_guessing_electric_directions(value, counts, modes):
    parsed = seat_adjust.parse(value)
    assert parsed['editable']
    assert [seat['count'] for seat in parsed['seats']] == counts
    assert [seat['mode'] for seat in parsed['seats']] == modes
    assert _seat_adjust_components(value) == seat_adjust.components(value)
    assert seat_adjust.parse(seat_adjust.label(value))['seats'] == parsed['seats']


@pytest.mark.parametrize('value', [
    '[待定]主副手调', '[待pjy核]主副电调', '○主副电调(主含腰撑4向)',
    '不适用', '未说明', '✕', '主驾6向电调+副驾未知', '主驾6向手调+主驾4向手调',
    '主驾0向电调+副驾4向手调',
])
def test_noneditable_states_preserve_original_and_never_fill_manual(value):
    parsed = seat_adjust.parse(value)
    assert not parsed['editable']
    assert all(seat['mode'] is None and seat['count'] is None for seat in parsed['seats'])
    assert seat_adjust.label(value) == value
    assert parsed['hint']


def test_support_suffix_and_prefix_are_preserved_without_counting_lumbar():
    value = '●主驾10向电动（主含腰撑4向）+副驾4向手动(副含腿托(2向))'
    parsed = seat_adjust.parse(value)
    assert parsed['prefix'] == '●'
    assert parsed['suffix'] == '（主含腰撑4向）(副含腿托(2向))'
    assert seat_adjust.components(value) == (14, 1)
    assert seat_adjust.label(value) == '●主驾10向电调+副驾4向手调（主含腰撑4向）(副含腿托(2向))'


def test_manual_default_hint_only_names_counts_that_were_defaulted():
    assert '主驾6向、副驾4向' in seat_adjust.parse('主副手调')['hint']
    assert '副驾4向' in seat_adjust.parse('主驾8向手调+副驾手调')['hint']
    assert '主驾6向' not in seat_adjust.parse('主驾8向手调+副驾手调')['hint']
    assert seat_adjust.parse('主驾6向手调+副驾4向手调')['hint'] == ''
    assert '默认' not in seat_adjust.parse('主副电调')['hint']
    assert '默认' not in seat_adjust.parse('主驾电调+副驾手调')['hint']


@pytest.mark.parametrize('dot,text,expected', [
    ('●', '主/副', ['电调', '电调']),
    ('', '主●/副●', ['电调', '电调']),
    ('', '主●/副-', ['电调', '手调']),
    ('', '主-/副●', ['手调', '电调']),
    ('', '主○/副●', ['手调', '电调']),
    ('●', '主驾●/副驾○', ['电调', '手调']),
    ('○', '主/副', ['手调', '手调']),
    ('●', '', ['电调', '电调']),
    ('', '[待定]', [None, None]),
    ('●', '方式未说明', [None, None]),
])
def test_raw_modes_respect_each_standard_marker(dot, text, expected):
    assert seat_adjust.raw_modes(Cell(dot=dot, text=text)) == expected


def test_raw_modes_read_subitems_and_keep_each_pending_state_independent():
    assert seat_adjust.raw_modes(Cell(dot='●', text='主', subs=[Cell(dot='●', text='副')])) == ['电调', '电调']
    assert seat_adjust.raw_modes(Cell(dot='●', text='主', subs=[Cell(dot='○', text='副')])) == ['电调', '手调']
    assert seat_adjust.raw_modes(Cell(dot='●', text='主●/副[待定]')) == ['电调', None]
    assert seat_adjust.raw_modes(Cell(dot='●', text='主[待定]/副●')) == [None, '电调']
    assert seat_adjust.raw_modes(Cell(dot='●', text='主●/副未知')) == ['电调', None]
    assert seat_adjust.raw_modes(Cell(dot='●', text='主●/副无')) == ['电调', '手调']
    assert seat_adjust.raw_modes(Cell(dot='●', text='主驾电调/副驾手调')) == ['电调', '手调']


def test_raw_mode_and_direction_explicit_evidence_overrides_common_row():
    main = Cell(dot='●', text='主驾电动10向(腰撑4向)')
    passenger = Cell(dot='●', text='副驾4向手动')
    assert seat_adjust.raw_modes(Cell(dot='●', text='主/副'), main, passenger) == ['电调', '手调']
    assert seat_adjust.raw_directions(main) == 10
    assert seat_adjust.raw_directions(passenger) == 4


def test_raw_direction_count_uses_only_standard_motion_not_lumbar():
    cell = Cell(dot='●', text='前后调节', subs=[Cell(dot='●', text='靠背调节'),
        Cell(dot='●', text='高低调节(2向)'), Cell(dot='●', text='腿托调节'),
        Cell(dot='●', text='腰部支撑(4向)'), Cell(dot='○', text='腿部支撑调节(4向)')])
    assert seat_adjust.raw_directions(cell) == 8
    assert seat_adjust.raw_directions(Cell(dot='○', text='10向电动')) is None
    assert seat_adjust.raw_directions(Cell(dot='●', text='腰部支撑(4向)')) is None


def test_q05_raw_map_stage_and_calculation_share_the_same_evidence():
    raw = rawschema.detect_and_load(str(Path(__file__).parent/'golden'/'raw-Q05-汽车之家全表-2026-09-11.json'))
    values = map_raw_to_ladder(raw, Rules())[35]['values']
    assert [seat_adjust.components(value) for value in values] == [(10, 0), (10, 2), (10, 2), (12, 2), (12, 2), (10, 2), (12, 2)]
    assert seat_adjust.legacy_summary(raw, 0) == '主副手调'
    assert seat_adjust.legacy_summary(raw, 1) == '主副电调(主含腰撑4向)'
    assert seat_adjust.legacy_summary(raw, 3) == '主副电调(主腰撑4向/副腿托+腰撑4向)'
    electric = next(item for item in stage_one.features(raw) if item['key'] == '座椅电调')
    assert electric['values'] == [[]] + [['主驾座椅电调', '副驾座椅电调']]*6
    assert dynamic_delta(35, values[3], values[1]) == 100
    assert dynamic_delta(35, values[1], values[3]) == -100
    assert dynamic_delta(35, values[1], '主副手调') == 800


def test_legacy_summary_still_matches_preexisting_explicit_input():
    raw = RawTable(trims=[Trim(idx=0, short='A')], rows=[
        RawRow(name='主座椅调节方式', cells=[Cell(dot='●', text='主驾10向电动')]),
        RawRow(name='副座椅调节方式', cells=[Cell(dot='●', text='副驾4向手动')]),
        RawRow(name='主/副驾驶座电动调节', cells=[Cell(dot='●', text='主/副')]),
    ])
    assert seat_adjust.legacy_summary(raw, 0) == '主驾10向电调+副驾4向手调'


def test_manual_default_amount_reverses_in_end_to_end_backup():
    rules = Rules()
    table = ValuationTable(items=[ValuationItem(**item) for item in default_valuation(rules)['items']])
    for left, right, expected in [('主副手调', '主驾8向手调+副驾4向手调', -100),
                                  ('主驾8向手调+副驾4向手调', '主副手调', 100)]:
        ours = Ladder(trims=[{'name':'A'}], items=[LadderItem(no=35, name='座椅调节', values=[left])])
        theirs = Ladder(trims=[{'name':'B'}], items=[LadderItem(no=35, name='座椅调节', values=[right])])
        pairs = [{'self_trim':'A', 'comp_trim':'B'}]
        cells = diff(ours, theirs, pairs, rules, valuation=table)
        assert next(cell for cell in cells if cell['no'] == 35)['verdict'] == ('多' if expected > 0 else '少')
        group = assemble_backup(cells, pairs, '本品', '竞品', {'A':10}, {'B':10}, table)[0]
        assert group['valuation']['config_adv'] == expected
