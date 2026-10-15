import pytest

from api.bridge import Bridge
from engine import stage_one
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules


RESTORED = {
    '驾驶辅助影像', '辅助驾驶路段', '电动座椅记忆功能', '手机无线充电功率',
    '内后视镜功能', '近光灯光源', '中控屏幕尺寸', '前排座椅功能',
}
PLAN = [{'target': 0, 'base': None}, {'target': 1, 'base': 0}]


def raw_table(rows):
    return RawTable(model='默认展示测试车', source='rich', trims=[
        Trim(0, '基础', price_guide=10), Trim(1, '升级', price_guide=11),
    ], rows=rows)


def items(raw, excluded_rows=None):
    return stage_one._compact_items(
        stage_one._change_items(stage_one.features(raw, excluded_rows), 1, 0), 0)


@pytest.mark.parametrize('name, cell, expected', [
    ('驾驶辅助影像', Cell(dot='●', text='360度全景影像'), '360度全景影像'),
    ('辅助驾驶路段', Cell(dot='●', text='城市'), '城市NOA'),
    ('电动座椅记忆功能', Cell(dot='●', text='主驾驶位'), '主驾记忆'),
    ('手机无线充电功率', Cell(dot='●', text='40W'), '50W手机无线充电'),
    ('手机无线充电功率', Cell(dot='●', text='50W'), '50W手机无线充电'),
    ('手机无线充电功率', Cell(dot='●', text='15W'), '慢充手机无线充电'),
    ('内后视镜功能', Cell(dot='●', text='自动防眩目'), '自动防眩目内后视镜'),
    ('近光灯光源', Cell(dot='●', text='LED'), 'LED大灯'),
    ('中控屏幕尺寸', Cell(dot='●', text='15.6英寸'), '15.6寸中控'),
    ('前排座椅功能', Cell(subs=[
        Cell(dot='●', text='通风'), Cell(dot='●', text='加热'),
    ]), '前排通风加热'),
])
def test_restored_sources_display_by_default_and_remain_explicitly_hideable(name, cell, expected):
    raw = raw_table([RawRow(name, [Cell(), cell])])
    original = raw.to_json()
    assert not RESTORED.intersection(stage_one.DEFAULT_EXCLUDED_ROWS)
    assert items(raw) == [expected]
    assert expected in stage_one.render(raw, PLAN)
    assert items(raw, excluded_rows=[name]) == []
    assert raw.to_json() == original


@pytest.mark.parametrize('name', sorted(RESTORED))
def test_restored_optional_sources_stay_separate_from_standard_equipment(name):
    raw = raw_table([RawRow(name, [Cell(), Cell(dot='○', text='选装扩展包')])])
    original = raw.to_json()
    assert items(raw) == []
    assert stage_one._option_lines(raw, 1) == [name + '：选装扩展包']
    assert stage_one._option_lines(raw, 1, excluded_rows=[name]) == []
    standard, optional = stage_one.render(raw, PLAN).split('## 选装')
    assert '选装扩展包' not in standard and '选装扩展包' in optional
    assert raw.to_json() == original


def test_restored_display_preferences_leave_raw_and_valuation_mapping_unchanged(tmp_path):
    raw = raw_table([
        RawRow('驾驶辅助影像', [Cell(), Cell(dot='●', text='360度全景影像')]),
        RawRow('手机无线充电功能', [Cell(), Cell(dot='●', text='前排')]),
        RawRow('手机无线充电功率', [Cell(), Cell(dot='●', text='50W')]),
        RawRow('前排座椅功能', [Cell(), Cell(dot='●', text='通风')]),
    ])
    original = raw.to_json()
    mapped = map_raw_to_ladder(raw, Rules())
    bridge = Bridge(str(tmp_path))
    bridge.stage_raw = raw
    try:
        assert bridge.stage_preview(PLAN)['columns'][1]['items']
        assert bridge.save_stage_display_rules(sorted(RESTORED | {'手机无线充电功能'}))['ok']
        assert bridge.stage_preview(PLAN)['columns'][1]['items'] == []
        assert map_raw_to_ladder(raw, Rules()) == mapped
        assert raw.to_json() == original
    finally:
        bridge.shutdown()
