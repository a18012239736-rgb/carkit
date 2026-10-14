from pathlib import Path

import pytest

from api.bridge import Bridge
from engine import rawschema, stage_one
from engine.models import Cell, RawRow, RawTable, Trim


PLAN = [{'target': 0, 'base': None}, {'target': 1, 'base': 0}]


def table(rows):
    return RawTable(model='子项展示测试', trims=[Trim(0, '基础'), Trim(1, '升级')], rows=rows)


def lines(raw, target=1, base=0, excluded=None):
    features = stage_one.features(raw, [] if excluded is None else excluded)
    return stage_one._compact_items(stage_one._change_items(features, target, base), base)


def test_real_q05_standard_lumbar_is_omitted_without_changing_direction_totals():
    raw = rawschema.detect_and_load(str(Path(__file__).parent / 'golden' / 'raw-Q05-汽车之家全表-2026-09-11.json'))
    original = raw.to_json()
    result = lines(raw)
    assert not any('腰部支撑' in line for line in result)
    assert not any('主驾10向' in line for line in result)
    assert raw.to_json() == original


def test_seat_supports_are_omitted_and_optional_information_is_preserved_separately():
    raw = table([RawRow('主座椅调节方式', [
        Cell(text='前后调节靠背调节'),
        Cell(text='前后调节靠背调节腰部支撑(4向)', subs=[
            Cell(dot='●', text='头枕调节(2向)'), Cell(dot='○', text='侧翼支撑(2000元)'),
        ]),
    ])])
    original = raw.to_json()
    result = lines(raw)
    assert result == []  # Supports do not alter the seat direction/mode summary.
    assert not any('侧翼' in line for line in result)
    assert stage_one._option_lines(raw, 1, []) == ['主座椅调节方式：侧翼支撑(2000元)']
    assert lines(raw, excluded=['主座椅调节方式']) == []
    assert stage_one._option_lines(raw, 1, ['主座椅调节方式']) == []
    assert raw.to_json() == original


def test_removed_standard_seat_support_does_not_create_absent_adjustment_description():
    raw = table([RawRow('主座椅调节方式', [
        Cell(text='前后调节靠背调节腰部支撑(4向)'), Cell(text='前后调节靠背调节'),
    ])])
    assert lines(raw) == []


def test_flattened_unknown_seat_and_mirror_functions_reach_preview_and_markdown(tmp_path):
    raw = table([
        RawRow('前排座椅功能', [Cell(text='加热(仅驾驶位)'), Cell(text='加热(仅驾驶位)腿托')]),
        RawRow('外后视镜功能', [Cell(text='电动调节'), Cell(text='电动调节自动防眩目')]),
    ])
    original = raw.to_json()
    bridge = Bridge.__new__(Bridge)
    bridge.workdir = str(tmp_path)
    bridge.stage_raw = raw
    assert bridge.save_stage_display_rules([])['ok']
    preview = bridge.stage_preview(PLAN)
    assert preview['ok']
    assert '前排座椅功能：腿托' in preview['columns'][1]['items']
    assert '外后视镜电调+自动防眩目' in preview['columns'][1]['items']
    assert not any('(仅驾驶位)' in line for line in preview['columns'][1]['items'])
    markdown = stage_one.render(raw, PLAN, excluded_rows=[])
    assert all(line in markdown for line in preview['columns'][1]['items'])
    assert bridge.save_stage_display_rules(['前排座椅功能', '外后视镜功能'])['ok']
    assert bridge.stage_preview(PLAN)['columns'][1]['items'] == []
    assert raw.to_json() == original


def test_removed_flattened_mirror_function_shows_only_current_description():
    raw = table([RawRow('外后视镜功能', [Cell(text='电动调节自动防眩目'), Cell(text='电动调节')])])
    assert lines(raw) == ['外后视镜电调']


def test_mirror_summary_deduplicates_folding_and_keeps_memory_downturn_and_unknown_functions():
    raw = table([RawRow('外后视镜功能', [Cell(), Cell(dot='●', text='电动调节', subs=[
        Cell(dot='●', text='电动折叠'), Cell(dot='●', text='后视镜记忆'),
        Cell(dot='●', text='后视镜加热'), Cell(dot='●', text='倒车自动下翻'),
        Cell(dot='●', text='锁车自动折叠'), Cell(dot='●', text='自动防眩目'),
        Cell(dot='○', text='投影照明(500元)'),
    ])])])
    original = raw.to_json()
    expected = ['外后视镜电调+折叠+加热+记忆+倒车下翻+自动防眩目']
    assert lines(raw) == expected
    assert lines(raw, target=1, base=None) == expected
    assert lines(raw, target=0, base=1) == ['无（' + expected[0] + '）']
    assert stage_one._option_lines(raw, 1, []) == ['外后视镜功能：投影照明(500元)']
    assert lines(raw, excluded=['外后视镜功能']) == []
    assert raw.to_json() == original


def test_structured_and_flattened_mirror_functions_share_the_same_compact_description():
    raw = table([RawRow('外后视镜功能', [
        Cell(dot='●', text='电动调节', subs=[
            Cell(dot='●', text='电动折叠'), Cell(dot='●', text='后视镜加热'),
            Cell(dot='●', text='后视镜记忆'), Cell(dot='●', text='锁车自动折叠'),
        ]),
        Cell(text='外后视镜电调+外后视镜电动折叠+锁车自动折叠+后视镜加热+后视镜记忆'),
    ])])
    assert lines(raw, target=0, base=None) == ['外后视镜电调+折叠+加热+记忆']
    assert lines(raw, target=1, base=None) == ['外后视镜电调+折叠+加热+记忆']
    assert lines(raw) == []


@pytest.mark.parametrize('target,base', [(1, 0), (0, 1)])
def test_automatic_folding_changes_are_not_lost_when_the_display_label_is_compact(target, base):
    raw = table([RawRow('外后视镜功能', [
        Cell(text='电动调节电动折叠'),
        Cell(text='电动调节电动折叠锁车自动折叠'),
    ])])
    assert lines(raw, target=target, base=base) == ['外后视镜电调+折叠']


def test_v2l_power_is_not_hidden_when_only_presence_row_is_excluded():
    raw = table([
        RawRow('对外放电', [Cell(), Cell(dot='●')]),
        RawRow('对外交流放电功率(kW)', [Cell(), Cell(text='3.3')]),
    ])
    original = raw.to_json()
    assert lines(raw) == ['对外放电3.3kW']
    assert lines(raw, excluded=['对外放电']) == ['对外交流放电功率(kW)3.3']
    assert lines(raw, excluded=['对外交流放电功率(kW)']) == ['对外放电']
    assert lines(raw, excluded=[row.name for row in raw.rows]) == []
    assert raw.to_json() == original


def test_different_duplicate_merged_row_is_displayed_but_identical_duplicate_stays_compact():
    common = RawRow('手机无线充电功能', [Cell(text='前排'), Cell(text='前排')])
    rear = RawRow('手机无线充电功能', [Cell(), Cell(text='后排')], group='后排')
    raw = table([common, rear])
    assert lines(raw) == ['手机无线充电功能后排']
    assert lines(raw, excluded=['手机无线充电功能']) == []
    identical = table([common, RawRow(common.name, common.cells)])
    assert len(stage_one.features(identical, [])) == 1


def test_confirmed_color_exclusions_can_be_restored_and_apply_to_options():
    raw = table([
        RawRow('外观颜色', [Cell(text='白'), Cell(text='黑')]),
        RawRow('内饰颜色', [Cell(), Cell(dot='○', text='红')]),
    ])
    excluded = ['外观颜色', '内饰颜色']
    assert lines(raw, excluded=excluded) == []
    assert stage_one._option_lines(raw, 1, excluded) == []
    assert lines(raw, excluded=[]) == ['外观颜色黑（外观颜色白）']
    assert stage_one._option_lines(raw, 1, []) == ['内饰颜色：红']


def test_adas_system_names_are_compared_without_changing_the_known_l2_label():
    raw = table([
        RawRow('辅助驾驶系统', [Cell(text='甲系统'), Cell(text='天枢领航激光版')]),
        RawRow('辅助驾驶等级', [Cell(text='L2'), Cell(text='L2')]),
    ])
    original = raw.to_json()
    assert lines(raw) == ['辅助驾驶系统天枢领航激光版(辅助驾驶系统甲系统)']
    assert lines(raw, target=0, base=None) == ['基础L2辅助驾驶', '辅助驾驶系统甲系统']
    assert lines(raw, excluded=['辅助驾驶系统']) == []
    assert raw.to_json() == original


def test_unknown_adas_grade_and_route_keep_source_words_without_inventing_a_level():
    raw = table([
        RawRow('辅助驾驶等级', [Cell(text='L2'), Cell(text='L3')]),
        RawRow('辅助驾驶路段', [Cell(text='高速路段'), Cell(text='园区道路')]),
    ])
    result = lines(raw)
    assert '辅助驾驶等级L3' in result
    assert '辅助驾驶路段园区道路' in result
    assert not any('城市NOA' in value for value in result)
    assert lines(raw, excluded=['辅助驾驶等级', '辅助驾驶路段']) == []


def test_common_adas_words_stay_compact_and_optional_names_are_not_standard():
    raw = table([
        RawRow('辅助驾驶系统', [Cell(text='基础L2辅助驾驶'), Cell(dot='●', text='L2', subs=[Cell(dot='○', text='系统增强包')])]),
        RawRow('辅助驾驶等级', [Cell(text='L2'), Cell(text='L2')]),
        RawRow('辅助驾驶路段', [Cell(text='高速路段'), Cell(text='城市/高速路段')]),
    ])
    assert lines(raw) == ['城市NOA(高速NOA)']
    assert stage_one._option_lines(raw, 1, []) == ['辅助驾驶系统：系统增强包']
    assert '系统增强包' not in '\n'.join(lines(raw))


def test_real_q05_adas_brand_remains_visible_in_addition_to_highway_noa():
    raw = rawschema.detect_and_load(str(Path(__file__).parent / 'golden' / 'raw-Q05-汽车之家全表-2026-09-11.json'))
    result = lines(raw, target=5, base=4)
    assert any('高速NOA' in value for value in result)
    assert any('天枢领航激光版' in value for value in result)
    assert not any('天枢领航激光版' in value for value in lines(raw, target=5, base=4, excluded=['辅助驾驶系统']))
