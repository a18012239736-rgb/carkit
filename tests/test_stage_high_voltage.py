from engine import stage_one
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules


def table(rows):
    count = len(rows[0].cells)
    return RawTable(model='高压展示测试', trims=[Trim(i, f'版型{i}') for i in range(count)], rows=rows)


def voltage(raw, excluded=()):
    return stage_one.features(raw, excluded_rows=excluded)


def test_voltage_and_fast_charge_are_one_compact_feature_in_either_source_order():
    rows = [
        RawRow('高压快充', [Cell(), Cell(text='支持'), Cell(text='支持')]),
        RawRow('高压平台（V）', [Cell(text='400'), Cell(text='800'), Cell(text='1000V')]),
    ]
    for order in (rows, rows[::-1]):
        raw = table(order)
        original = raw.to_json()
        calculated = map_raw_to_ladder(raw, Rules())
        features = voltage(raw)
        assert features == [{'key': '高压平台', 'values': [['400V'], ['800V'], ['1000V']], 'scalar': True}]
        assert stage_one._change_items(features, 1, 0) == [('高压平台', '800V')]
        assert stage_one._change_items(features, 0, 1) == [('高压平台', '400V')]
        assert stage_one._change_items(features, 2, 1) == [('高压平台', '1000V')]
        assert raw.to_json() == original
        assert map_raw_to_ladder(raw, Rules()) == calculated


def test_standard_boolean_platform_or_fast_charge_uses_800v_without_guessing_missing_values():
    cells = [Cell(dot='●'), Cell(text='支持'), Cell(text='有'), Cell(), Cell(text='无'),
             Cell(text='不支持'), Cell(dot='○', text='800'), Cell(text='[待定]800'), Cell(text='未知')]
    for source in ('高压平台', '800V高压平台', '高压快充'):
        raw = table([RawRow(source, cells)])
        values = voltage(raw)[0]['values']
        assert values[:3] == [['800V']] * 3
        assert values[3:7] == [[]] * 4
        assert values[7:] == [[source+'[待定]800'], [source+'未知']]
        assert stage_one._option_lines(raw, 6, []) == [source+'：800']


def test_optional_or_unknown_platform_cannot_become_standard_from_fast_charge_presence():
    raw = table([
        RawRow('高压快充', [Cell(text='支持')] * 4),
        RawRow('高压平台（V）', [Cell(dot='○', text='800'), Cell(text='[待定]800'),
                              Cell(text='未知'), Cell(text='400')]),
    ])
    assert voltage(raw)[0]['values'] == [[], ['高压平台（V）[待定]800'], ['高压平台（V）未知'], ['400V']]
    assert stage_one._option_lines(raw, 0, []) == ['高压平台（V）：800']


def test_voltage_display_exclusions_apply_to_each_source_row_without_mutation():
    raw = table([
        RawRow('高压快充', [Cell(text='支持')]),
        RawRow('高压平台（V）', [Cell(text='1000')]),
    ])
    assert voltage(raw, ['高压快充'])[0]['values'] == [['1000V']]
    assert voltage(raw, ['高压平台（V）'])[0]['values'] == [['800V']]
    assert voltage(raw, ['高压快充', '高压平台（V）']) == []
