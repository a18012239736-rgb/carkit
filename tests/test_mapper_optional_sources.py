"""Regression cells from the October 2026 Autohome multi-car replay."""
import pytest

from engine import seat_adjust, stage_one
from engine.mapper import legacy_mapped_item, map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules
from engine.valuer import dynamic_delta
from test_config_editor_mapping import run_editor


def mapped(rows):
    raw = RawTable(trims=[Trim(idx=0, short='源格回归')], rows=[
        RawRow(name=name, cells=[cell]) for name, cell in rows.items()
    ])
    return raw, map_raw_to_ladder(raw, Rules())


def test_optional_360_does_not_replace_standard_reverse_camera():
    # 速腾 S 1.5L 精英版 / L 300TSI DSG 豪华型.
    raw, result = mapped({'驾驶辅助影像': Cell(dot='●', text='倒车影像', subs=[
        Cell(dot='○', text='360度全景影像 (3000元)'),
    ])})
    assert result[7]['values'] == ['倒车影像']
    assert dynamic_delta(7, result[7]['values'][0], '倒车影像') == 0
    assert dynamic_delta(7, result[7]['values'][0], '✕') == 1000
    assert legacy_mapped_item(raw, 0, 7) == {'value': '360影像'}
    assert stage_one._option_lines(raw, 0, []) == ['驾驶辅助影像：360度全景影像 (3000元)']


@pytest.mark.parametrize('head,child,expected', [
    ('○', '●', '360影像'),
    ('●', '○', '倒车影像'),
    ('●', '●', '360影像'),
])
def test_camera_type_uses_each_subitems_standard_marker(head, child, expected):
    _, result = mapped({'驾驶辅助影像': Cell(dot=head, text='倒车影像', subs=[
        Cell(dot=child, text='360度全景影像'),
    ])})
    assert result[7]['values'] == [expected]


def test_optional_540_child_does_not_upgrade_standard_360():
    _, result = mapped({'驾驶辅助影像': Cell(dot='●', text='360度全景影像', subs=[
        Cell(dot='○', text='540度影像'),
    ])})
    assert result[7]['values'] == ['360影像']
    assert dynamic_delta(7, result[7]['values'][0], '360影像') == 0


def test_optional_only_camera_stays_outside_standard_mapping():
    raw, result = mapped({'驾驶辅助影像': Cell(dot='○', text='360度全景影像 (3000元)')})
    assert result[7]['values'] == ['✕']
    assert dynamic_delta(7, result[7]['values'][0], '✕') == 0
    assert stage_one._option_lines(raw, 0, []) == ['驾驶辅助影像：360度全景影像 (3000元)']


@pytest.mark.parametrize('text', ['[待定]', '?'])
def test_unknown_standard_camera_remains_pending_not_absent(text):
    _, result = mapped({'驾驶辅助影像': Cell(dot='●', text=text)})
    value = result[7]['values'][0]
    assert '[待定]' in value


@pytest.mark.parametrize('row', ['副驾娱乐屏尺寸', '副驾驶位屏幕尺寸', '副驾娱乐屏'])
@pytest.mark.parametrize('dot,prefix', [('●', ''), ('○', '○')])
def test_passenger_screen_source_alias_keeps_size_and_optionality(row, dot, prefix):
    # 极氪9X / 海狮06 use the newer 副驾娱乐屏尺寸 row.
    raw, result = mapped({row: Cell(dot=dot, text='16英寸')})
    value = result[22]['values'][0]
    assert value == prefix + '16寸副驾屏'
    assert result[22]['row_absent'] is False
    assert Rules().row_to_item[row] == 22
    if prefix:
        assert dynamic_delta(22, value, '✕') == 0
    else:
        assert dynamic_delta(22, value, '✕') == 2000
    if row == '副驾娱乐屏尺寸':
        assert legacy_mapped_item(raw, 0, 22) == {'value': '✕'}
    run_editor(r"""
const instance=makeCell(values[0],22);
assert.strictEqual(instance.cell.screen.value.state,values[0].startsWith('○')?'optional':'present');
assert.strictEqual(instance.cell.screen.value.size,'16');
assert.deepStrictEqual(instance.emitted,[]);
""", [value])


def test_passenger_dimensions_take_priority_over_presence_only_alias():
    _, result = mapped({'副驾娱乐屏': Cell(dot='●'),
                        '副驾娱乐屏尺寸': Cell(dot='●', text='16英寸')})
    assert result[22]['values'] == ['16寸副驾屏']


def test_explicit_optional_center_size_is_kept_and_shown_without_emitting_changes():
    # 奔腾小马 222km 伶俐马 / 玲珑马: both screen rows are optional.
    raw, result = mapped({'中控彩色屏幕': Cell(dot='○', text='触控液晶屏'),
                          '中控屏幕尺寸': Cell(dot='○', text='10.1英寸')})
    value = result[21]['values'][0]
    assert value == '○10.1寸中控'
    assert dynamic_delta(21, value, '✕') == 0
    assert legacy_mapped_item(raw, 0, 21) == {'value': '○(选装)'}
    run_editor(r"""
const instance=makeCell(values[0],21);
assert.strictEqual(instance.cell.screen.value.state,'optional');
assert.strictEqual(instance.cell.screen.value.size,'10.1');
assert.deepStrictEqual(instance.emitted,[]);
""", [value])


@pytest.mark.parametrize('row,no', [('中控屏幕尺寸', 21), ('副驾娱乐屏尺寸', 22)])
@pytest.mark.parametrize('text', ['触控液晶屏 (1000元)', '2K触控液晶屏', '[待定]10.1英寸', '[待pjy核]10.1英寸', '101英寸'])
def test_unknown_optional_screen_size_is_not_guessed_from_price_or_resolution(row, no, text):
    _, result = mapped({row: Cell(dot='○', text=text)})
    assert result[no]['values'] == ['○(选装)']


@pytest.mark.parametrize('dot,text,modes', [
    ('○', '主○/副- (2000元)', ['手调', '手调']),
    ('●', '主●/副○ (2000元)', ['电调', '手调']),
    ('●', '主●/副○（2000元）', ['电调', '手调']),
    ('●', '主●/副○ (1.20万元)', ['电调', '手调']),
])
def test_seat_price_note_does_not_hide_standard_adjustment(dot, text, modes):
    electric = Cell(dot=dot, text=text)
    assert seat_adjust.raw_modes(electric) == modes
    assert seat_adjust.raw_modes(electric, legacy_price_notes=True) == [modes[0], None]
    raw, result = mapped({'主/副驾驶座电动调节': electric,
                          '主座椅调节方式': Cell(dot='●', text='6向调节'),
                          '副座椅调节方式': Cell(dot='●', text='4向调节')})
    expected = f'主驾6向{modes[0]}+副驾4向{modes[1]}'
    assert result[35]['values'] == [expected]
    assert seat_adjust.components(expected) == (10, int(modes[0] == '电调'))
    assert '[待定]' in legacy_mapped_item(raw, 0, 35)['value']
    assert legacy_mapped_item(raw, 0, 35)['value'] == seat_adjust.from_raw(raw, 0, legacy_price_notes=True)
    assert stage_one._option_lines(raw, 0, []) == ([f'主/副驾驶座电动调节：{text}'] if dot == '○' else [])


@pytest.mark.parametrize('text', ['主●/副未知 (2000元)', '主●/副[待定] (2000元)',
                                 '主●/副○ (方式未说明)'])
def test_seat_price_note_fix_does_not_guess_unknown_adjustment(text):
    assert seat_adjust.raw_modes(Cell(dot='●', text=text)) == ['电调', None]
