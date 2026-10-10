"""Exact Autohome source cells from the 2026-10-10 multi-car replay.

Historical captures are software fixtures, not declarations of current trims.
"""
import pytest

from engine.mapper import legacy_mapped_item, map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules
from engine.seat_functions import from_text
from engine.valuer import dynamic_delta


def mapped(rows):
    raw = RawTable(trims=[Trim(idx=0, short='源格回归')], rows=[
        RawRow(name=name, cells=[Cell.from_dict(cell)]) for name, cell in rows.items()
    ])
    return raw, map_raw_to_ladder(raw, Rules())


@pytest.mark.parametrize('row,no', [('座椅材质', 34), ('方向盘材质', 25)])
def test_standard_material_after_optional_material(row, no):
    # MONA M03 / YU7: optional leather precedes the standard imitation leather.
    raw, result = mapped({row: {'dot': '○', 'text': '真皮', 'subs': [
        {'dot': '●', 'text': '仿皮'}, {'dot': '○', 'text': '皮/Alcantara混搭'},
    ]}})
    assert result[no]['values'] == ['仿皮']
    assert dynamic_delta(no, result[no]['values'][0], '仿皮') == 0
    assert legacy_mapped_item(raw, 0, no) == {'value': '○(选装)'}


def test_standard_highway_after_optional_city():
    # 海狮05 EV 540智航版, historical raw-7982-2026-09-24.json.
    raw, result = mapped({
        '辅助驾驶路段': {'dot': '○', 'text': '城市路段', 'subs': [
            {'dot': '●', 'text': '高速路段'},
        ]},
        '辅助驾驶等级': {'dot': '●', 'text': 'L2'},
        '辅助驾驶系统': {'dot': '●', 'text': 'DiPilot 100', 'subs': [
            {'dot': '○', 'text': 'DiPilot 300 (1.20万元)'},
        ]},
    })
    assert result[9]['values'] == ['高速NOA']
    assert dynamic_delta(9, result[9]['values'][0], '基础L2') == 4000
    assert legacy_mapped_item(raw, 0, 9) == {'value': '基础L2'}


def test_standard_instrument_size_after_optional_size():
    # 帕萨特 330TSI精英版, historical raw-528-2026-09-30.json.
    raw, result = mapped({
        '液晶仪表尺寸': {'dot': '○', 'text': '8英寸', 'subs': [
            {'dot': '●', 'text': '10.2英寸'},
        ]},
        '全液晶仪表盘': {'dot': '●', 'text': ''},
    })
    assert result[29]['values'] == ['全液晶仪表(10.2寸)']
    assert dynamic_delta(29, result[29]['values'][0], '全液晶仪表(10.2寸)') == 0
    assert legacy_mapped_item(raw, 0, 29) == {'value': '全液晶仪表(8寸)'}


def test_optional_instrument_size_not_used_as_standard_size():
    _, result = mapped({
        '液晶仪表尺寸': {'dot': '○', 'text': '12英寸'},
        '全液晶仪表盘': {'dot': '●', 'text': ''},
    })
    assert result[29]['values'] == ['全液晶仪表']


@pytest.mark.parametrize('cell', [
    {'dot': '●', 'text': '自动防眩目'},  # 凯美瑞, raw-110-2026-09-22.json.
    {'dot': '●', 'text': '自动防眩目', 'subs': [{'dot': '○', 'text': '流媒体'}]},
    {'dot': '○', 'text': '流媒体', 'subs': [{'dot': '●', 'text': '自动防眩目'}]},
])
def test_automatic_rearview_not_manual_or_optional_streaming(cell):
    _, result = mapped({'内后视镜功能': cell})
    assert result[31]['values'] == ['自动防眩目']
    assert dynamic_delta(31, result[31]['values'][0], '手动防眩目') == 0


def test_standard_streaming_rearview_retained():
    _, result = mapped({'内后视镜功能': {
        'dot': '○', 'text': '自动防眩目', 'subs': [{'dot': '●', 'text': '流媒体'}],
    }})
    assert result[31]['values'] == ['流媒体']


def test_headrest_speaker_and_independent_front_scopes():
    # SU7 后驱标准版, historical raw-6962-2026-09-30.json.
    raw, result = mapped({'前排座椅功能': {'dot': '●', 'text': '加热', 'subs': [
        {'dot': '●', 'text': '通风'},
        {'dot': '●', 'text': '按摩(仅驾驶位)'},
        {'dot': '○', 'text': '按摩(仅副驾驶位)'},
        {'dot': '●', 'text': '头枕扬声器(仅驾驶位)'},
    ]}})
    seats = {row['sub']: row['values'][0] for row in result[36]['subs']}
    assert all(seats[seat + feature] == '●' for seat in ('主驾', '副驾') for feature in ('加热', '通风'))
    assert seats['主驾按摩'] == seats['主驾头枕音响'] == '●'
    assert seats['副驾按摩'] == seats['副驾头枕音响'] == '✕'
    assert result[36]['values'] == ['前排加热/通风(主副)+按摩(仅主驾)']
    summary = from_text(result[36]['values'][0])
    assert all(summary[seat + feature] == seats[seat + feature]
               for seat in ('主驾', '副驾') for feature in ('加热', '通风', '按摩'))
    old = legacy_mapped_item(raw, 0, 36)
    assert old['value'] == '加热/通风/按摩(仅主驾)'
    assert old['subs']['主驾头枕音响'] == '✕'


def test_headrest_only_driver_does_not_restrict_other_features():
    # Same subitem form reported on YU7 / E5 / A06.
    _, result = mapped({'前排座椅功能': {'dot': '●', 'text': '加热', 'subs': [
        {'dot': '●', 'text': '通风'}, {'dot': '●', 'text': '头枕扬声器(仅驾驶位)'},
    ]}})
    assert result[36]['values'] == ['前排加热/通风(主副)']
    seats = {row['sub']: row['values'][0] for row in result[36]['subs']}
    assert seats['主驾头枕音响'] == '●' and seats['副驾头枕音响'] == '✕'


@pytest.mark.parametrize('text,expected', [
    ('头枕扬声器(仅驾驶位)', ('●', '✕')),
    ('头枕扬声器(仅副驾驶位)', ('✕', '●')),
    ('头枕扬声器（仅驾驶位）', ('●', '✕')),
])
def test_headrest_alias_keeps_explicit_scope(text, expected):
    seats = from_text(text)
    assert (seats['主驾头枕音响'], seats['副驾头枕音响']) == expected


def test_separate_headrest_row_supports_driver_position_and_optional_subitems():
    _, result = mapped({'前排座椅头枕扬声器': {
        'dot': '○', 'text': '副驾驶位', 'subs': [{'dot': '●', 'text': '驾驶位'}],
    }})
    seats = {row['sub']: row['values'][0] for row in result[36]['subs']}
    assert seats['主驾头枕音响'] == '●' and seats['副驾头枕音响'] == '✕'


def test_seat_memory_alias_keeps_front_scope_not_rear():
    # A06 240Max: driver, passenger and rear in the same cell; front-only pricing.
    _, result = mapped({'电动座椅记忆功能': {
        'dot': '●', 'text': '驾驶位', 'subs': [
            {'dot': '●', 'text': '副驾驶位'}, {'dot': '●', 'text': '后排'},
        ],
    }})
    assert result[45]['values'] == ['前排座椅记忆']
    assert dynamic_delta(45, result[45]['values'][0], '✕') == 200
