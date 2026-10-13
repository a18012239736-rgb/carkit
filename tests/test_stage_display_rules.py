from pathlib import Path
import re

from openpyxl import load_workbook
import pytest

from api.bridge import Bridge
from engine import stage_one
from engine.differ import assemble_backup, diff
from engine.ladder import build_ladder
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.valuer import default_valuation


PLAN = [{'target': 0, 'base': None}, {'target': 1, 'base': 0}]


def raw_table(rows):
    return RawTable(model='全量展示测试车', source='rich', trims=[
        Trim(0, '基础', price_guide=10), Trim(1, '升级', price_guide=11),
    ], rows=rows)


def items(raw, index=1, base=0, excluded_rows=()):
    features = stage_one.features(raw, excluded_rows=excluded_rows)
    return stage_one._compact_items(stage_one._change_items(features, index, base), base)


def test_unknown_standard_presence_shows_name_and_all_values_are_compared():
    raw = raw_table([
        RawRow('智能香氛', [Cell(), Cell(dot='●')]),
        RawRow('屏幕刷新率(Hz)', [Cell(text='60'), Cell(text='120')]),
        RawRow('光感遮阳帘', [Cell(dot='●'), Cell()]),
    ])
    result = items(raw)
    assert '智能香氛' in result
    assert not {'有', '支持', '是', '●'}.intersection(result)
    assert any('屏幕刷新率(Hz)' in value and '120' in value and '60' in value
               and re.search(r'[（(].*60.*[）)]$', value) for value in result)
    assert '无（光感遮阳帘）' in result


def test_optional_unknown_equipment_is_separate_and_exclusion_hides_both_markers():
    raw = raw_table([
        RawRow('智能香氛', [Cell(), Cell(dot='●', subs=[Cell(dot='○', text='香氛盒(300元)')])]),
        RawRow('自动遮阳帘', [Cell(), Cell(dot='○')]),
    ])
    assert items(raw) == ['智能香氛']
    assert stage_one._option_lines(raw, 1) == ['智能香氛：香氛盒(300元)', '自动遮阳帘']
    hidden = ['智能香氛', '自动遮阳帘']
    assert items(raw, excluded_rows=hidden) == []
    assert stage_one._option_lines(raw, 1, excluded_rows=hidden) == []
    markdown = stage_one.render(raw, PLAN)
    standard, optional = markdown.split('## 选装')
    assert '自动遮阳帘' not in standard and '香氛盒' not in standard
    assert '自动遮阳帘' in optional and '香氛盒' in optional
    assert '智能香氛' not in stage_one.render(raw, PLAN, excluded_rows=hidden)


def test_known_seat_row_keeps_unrecognized_standard_subfunctions():
    raw = raw_table([RawRow('前排座椅功能', [Cell(), Cell(subs=[
        Cell(dot='●', text='加热'), Cell(dot='●', text='腿托'),
        Cell(dot='○', text='座椅旋转(2000元)'),
    ])])])
    result = items(raw)
    assert any('加热' in value for value in result)
    assert any('腿托' in value for value in result)
    assert not any('座椅旋转' in value for value in result)
    assert any('座椅旋转' in value for value in stage_one._option_lines(raw, 1, excluded_rows=[]))
    assert items(raw, excluded_rows=['前排座椅功能']) == []


def test_duplicate_unknown_names_keep_both_groups():
    raw = raw_table([
        RawRow('遮阳帘', [Cell(), Cell(text='电动')], group='天窗/玻璃'),
        RawRow('遮阳帘', [Cell(), Cell(text='手动')], group='车窗'),
    ])
    result = items(raw)
    assert any('电动' in value for value in result)
    assert any('手动' in value for value in result)
    assert len(stage_one.features(raw)) == 2
    assert items(raw, excluded_rows=['遮阳帘']) == []


def test_duplicate_unknown_rows_without_groups_are_not_silently_discarded():
    raw = raw_table([
        RawRow('遮阳帘', [Cell(), Cell(text='电动')]),
        RawRow('遮阳帘', [Cell(), Cell(text='手动')]),
    ])
    result = items(raw)
    assert any('电动' in value for value in result)
    assert any('手动' in value for value in result)
    assert len(stage_one.features(raw)) == 2
    assert items(raw, excluded_rows=['遮阳帘']) == []


@pytest.mark.parametrize('hidden, expected, optional', [
    ('手机无线充电功率', '前排手机无线充电', []),
    ('手机无线充电功能', '50W手机无线充电', ['手机无线充电功率：80W']),
])
def test_excluded_sources_cannot_reappear_through_merged_feature_lookups(hidden, expected, optional):
    raw = raw_table([
        RawRow('手机无线充电功能', [Cell(), Cell(dot='●', text='前排')]),
        RawRow('手机无线充电功率', [Cell(), Cell(dot='●', text='50W', subs=[Cell(dot='○', text='80W')])]),
    ])
    original = raw.to_json()
    assert items(raw) == ['前排50W手机无线充电']
    assert items(raw, excluded_rows=[hidden]) == [expected]
    assert stage_one._option_lines(raw, 1, excluded_rows=[hidden]) == optional
    assert raw.to_json() == original


def test_confirmed_exclusions_are_defaults_but_empty_list_reveals_raw_rows():
    raw = raw_table([
        RawRow('电池容量(kWh)', [Cell(text='40'), Cell(text='50')]),
        RawRow('电池能量(kWh)', [Cell(text='40'), Cell(text='50')]),
        RawRow('备胎规格', [Cell(), Cell(text='非全尺寸')]),
        RawRow('厂商指导价(元)', [Cell(text='100000'), Cell(text='110000')]),
        RawRow('智能香氛', [Cell(), Cell(dot='●')]),
    ])
    default_keys = {feature['key'] for feature in stage_one.features(raw)}
    assert '电池容量(kWh)' not in default_keys and '备胎规格' not in default_keys
    assert {'电池能量(kWh)', '智能香氛'}.issubset(default_keys)
    all_keys = {feature['key'] for feature in stage_one.features(raw, excluded_rows=[])}
    assert {row.name for row in raw.rows}.issubset(all_keys)


def test_all_confirmed_defaults_hide_standard_and_optional_but_keep_raw_data():
    defaults = stage_one.DEFAULT_EXCLUDED_ROWS
    assert len(defaults) == len(set(defaults)) == 217
    assert {
        '三电系统质保', '高精定位', '记忆泊车', '循迹倒车', '信号灯识别',
        '隐藏电动门把手', '主动降噪', 'USB/Type-C最大充电功率',
        '对外直流放电功率(kW)', '陡坡缓降', '起步提醒', '语音免唤醒词', '面部识别', '激光雷达线数',
    }.issubset(defaults)
    assert not {'樱珞粉主题套装', '牛油果绿主题套装', '罗兰紫主题套装'}.intersection(defaults)
    raw = raw_table([RawRow(name, [Cell(dot='●'), Cell(dot='○')]) for name in defaults] + [
        RawRow('新发现的配置', [Cell(), Cell(dot='●', subs=[Cell(dot='○', text='扩展包')])]),
    ])
    original = raw.to_json()
    assert [row.name for row in stage_one.display_raw(raw).rows] == ['新发现的配置']
    assert items(raw, excluded_rows=None) == ['新发现的配置']
    assert stage_one._option_lines(raw, 1) == ['新发现的配置：扩展包']
    assert stage_one.display_raw(raw, excluded_rows=[]).rows == raw.rows
    assert raw.to_json() == original


def test_new_exclusions_match_exact_names_without_hiding_other_usb_rows_or_theme_packs():
    visible = ['USB/Type-C接口数量', '其他主题套装', '三电系统质保扩展政策']
    raw = raw_table([RawRow(name, [Cell(), Cell(dot='●')]) for name in visible])
    assert [row.name for row in stage_one.display_raw(raw).rows] == visible


def test_lidar_line_count_is_hidden_by_default_but_restorable_without_valuation_changes():
    raw = raw_table([
        RawRow('激光雷达数量', [Cell(dot='●', text='1'), Cell(dot='●', text='1')]),
        RawRow('激光雷达品牌', [Cell(dot='●', text='华为'), Cell(dot='●', text='华为')]),
        RawRow('激光雷达线数', [Cell(dot='●', text='192'), Cell(dot='●', text='896')]),
    ])
    original = raw.to_json()
    assert '激光雷达线数' not in {feature['key'] for feature in stage_one.features(raw)}
    assert '激光雷达线数' in {feature['key'] for feature in stage_one.features(raw, excluded_rows=[])}
    assert stage_one.display_raw(raw, excluded_rows=[]).rows == raw.rows
    rules = Rules()
    mapped = map_raw_to_ladder(raw, rules)
    assert mapped[8]['values'][0] == mapped[8]['values'][1]
    assert map_raw_to_ladder(stage_one.display_raw(raw), rules) == mapped
    assert raw.to_json() == original


def test_new_data_folder_uses_confirmed_defaults_and_saved_empty_list_overrides_them(tmp_path):
    bridge = Bridge(str(tmp_path))
    try:
        assert bridge.stage_display_rules()['excluded_rows'] == list(stage_one.DEFAULT_EXCLUDED_ROWS)
        assert not (tmp_path / '阶梯展示排除清单.json').exists()
        assert bridge.save_stage_display_rules([])['ok']
    finally:
        bridge.shutdown()
    restarted = Bridge(str(tmp_path))
    try:
        assert restarted.stage_display_rules()['excluded_rows'] == []
    finally:
        restarted.shutdown()


def test_saved_exclusions_apply_to_history_survive_restart_and_can_be_restored(tmp_path):
    workdir = tmp_path / 'work'
    bridge = Bridge(str(workdir))
    capture = workdir / 'raw' / 'capture.json'
    raw_table([
        RawRow('智能香氛', [Cell(), Cell(dot='●')]),
        RawRow('智能香氛', [Cell(), Cell(dot='○', text='扩展包')], group='特色配置'),
        RawRow('自动遮阳帘', [Cell(), Cell(dot='●')]),
    ]).save(capture)
    original = capture.read_bytes()
    try:
        assert bridge.open_history(capture.name)['ok']
        initial = bridge.stage_display_rules()
        assert initial['ok'] and initial['rows'] == ['智能香氛', '自动遮阳帘']
        assert bridge.save_stage_display_rules([' 智能香氛 ', '智能香氛'])['ok']
        assert bridge.stage_display_rules()['excluded_rows'] == ['智能香氛']
        preview = bridge.stage_preview(PLAN)
        assert preview['ok'] and preview['columns'][1]['items'] == ['自动遮阳帘']
        assert preview['columns'][1]['options'] == []
    finally:
        bridge.shutdown()
    restarted = Bridge(str(workdir))
    try:
        assert restarted.stage_display_rules()['excluded_rows'] == ['智能香氛']
        assert restarted.open_history(capture.name)['ok']
        assert restarted.stage_preview(PLAN)['columns'][1]['items'] == ['自动遮阳帘']
        assert restarted.save_stage_display_rules([])['ok']
        assert '智能香氛' in restarted.stage_preview(PLAN)['columns'][1]['items']
        assert restarted.stage_preview(PLAN)['columns'][1]['options'] == ['智能香氛：扩展包']
        assert capture.read_bytes() == original
        # Display preferences belong to the selected data folder, not a global setting.
        other = Bridge(str(tmp_path / 'other'))
        try:
            assert other.stage_display_rules()['excluded_rows'] != ['智能香氛']
        finally:
            other.shutdown()
    finally:
        restarted.shutdown()


@pytest.mark.parametrize('invalid', ['智能香氛', {'excluded_rows': []}, None, [3], ['有效配置', None]])
def test_invalid_exclusion_input_preserves_last_saved_configuration(tmp_path, invalid):
    bridge = Bridge(str(tmp_path))
    try:
        assert bridge.save_stage_display_rules(['智能香氛'])['ok']
        saved = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*.json')}
        result = bridge.save_stage_display_rules(invalid)
        assert result['ok'] is False and result.get('error')
        assert bridge.stage_display_rules()['excluded_rows'] == ['智能香氛']
        assert {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*.json')} == saved
    finally:
        bridge.shutdown()


def test_preview_markdown_excel_share_full_data_and_saved_exclusions(tmp_path):
    bridge = Bridge(str(tmp_path / 'work'))
    bridge.stage_raw = raw_table([
        RawRow('智能香氛', [Cell(), Cell(dot='●')]),
        RawRow('屏幕刷新率(Hz)', [Cell(text='60'), Cell(text='120')]),
        RawRow('光感遮阳帘', [Cell(dot='●'), Cell()]),
        RawRow('自动遮阳帘', [Cell(), Cell(dot='○')]),
        RawRow('隐藏的额外功能', [Cell(), Cell(dot='●')]),
    ])
    bridge.save_file_dialog = lambda name, *_: str(tmp_path / name)
    try:
        assert bridge.save_stage_display_rules(['隐藏的额外功能'])['ok']
        preview = bridge.stage_preview(PLAN)
        markdown = bridge.stage_export(PLAN, choose_path=True)
        excel = bridge.export_excel('ladder', PLAN)
        assert preview['ok'] and markdown['ok'] and excel['ok']
        assert Path(markdown['path']).read_text(encoding='utf-8') == markdown['md']
        assert '隐藏的额外功能' not in markdown['md']
        for column in preview['columns']:
            assert not any('隐藏的额外功能' in value for value in column['items'])
            for value in column['items']:
                assert value in markdown['md']
            for value in column['options']:
                assert '> 选装：' + value in markdown['md']
        book = load_workbook(excel['path'])
        try:
            sheet = book['配置阶梯']
            for row, column in enumerate(preview['columns'], 2):
                assert (sheet.cell(row, 5).value or '') == '\n'.join(column['items'])
                assert (sheet.cell(row, 6).value or '') == '\n'.join(column['options'])
        finally:
            book.close()
    finally:
        bridge.shutdown()


def test_display_exclusions_do_not_change_mapping_or_competitive_valuation(tmp_path):
    bridge = Bridge(str(tmp_path))
    raw = raw_table([
        RawRow('AR-HUD增强现实抬头显示', [Cell(), Cell(dot='●')]),
        RawRow('智能香氛', [Cell(), Cell(dot='●')]),
    ])
    bridge.stage_raw = raw
    source = raw.to_json()
    def competition():
        rules = Rules()
        ladder = build_ladder(raw, rules)
        valuation = ValuationTable(items=[ValuationItem(**item) for item in default_valuation(rules)['items']])
        pairs = [{'self_trim': '升级', 'comp_trim': '基础'}]
        cells = diff(ladder, ladder, pairs, rules, valuation=valuation)
        groups = assemble_backup(cells, pairs, raw.model, raw.model, {'升级': 11}, {'基础': 10}, valuation)
        return map_raw_to_ladder(raw, rules), cells, groups
    try:
        before = competition()
        assert before[2][0]['valuation']['config_adv'] == 2000
        assert bridge.save_stage_display_rules(['AR-HUD增强现实抬头显示', '智能香氛'])['ok']
        assert bridge.stage_preview(PLAN)['columns'][1]['items'] == []
        assert competition() == before
        assert raw.to_json() == source
    finally:
        bridge.shutdown()
