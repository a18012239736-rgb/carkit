"""Ordering and ownership guarantees for report-local indexes and shared styles."""
from copy import deepcopy

from openpyxl import load_workbook

from engine.comparison_review import build_review
from engine.excel_export import export_report
from engine.ladder import build_ladder
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim
from engine.render_5c import render_md as render_5c
from engine.render_backup import render_md as render_backup
from engine.rules import Rules


def test_5c_keeps_original_columns_and_first_optional_occurrence():
    raw = RawTable(model='测试车', trims=[Trim(2, '高配', price_guide=12),
                                       Trim(0, '基础', price_guide=10), Trim(1, '待价')],
                   rows=[RawRow('功能', [Cell('●', '基础值'), Cell(), Cell('●', '升级值')]),
                         RawRow('选装项', [Cell('○', '选装包'), Cell(), Cell('○', '选装包')]),
                         RawRow('选装项', [Cell('○', '选装包')]),
                         RawRow('短行', [Cell('●')])])
    before = deepcopy(raw)
    text = render_5c(raw, date='2026-10-21')
    assert '| 版型 | 基础 | 高配 | 待价 |' in text
    assert '功能：基础值 → 升级值' in text
    assert '减：短行' in text
    assert '减：功能（升级值）' in text
    assert '> 选装：选装项：选装包（基础）；选装项：选装包（高配）' in text
    assert raw == before


def test_backup_grouping_keeps_stable_pair_order_and_last_item_name():
    groups = [{'pair': {'self_trim': '甲', 'comp_trim': '乙'}, 'self_price': 10,
               'comp_price': 11, 'more': [], 'less': [], 'valuation': {}}] * 2
    cells = [{'no': 45, 'pair': 1, 'name': '旧名', 'display': '多 右一'},
             {'no': 37, 'pair': 0, 'name': '扬声器', 'display': '同'},
             {'no': 45, 'pair': 0, 'name': '新名', 'display': '少 左一'},
             {'no': 45, 'pair': 1, 'name': '最终名称', 'display': '多 右二'}]
    before = deepcopy(cells)
    text = render_backup('本品', '竞品', groups, cells, date='2026-10-21')
    assert '| 1 | 最终名称 | **少** 左一 | **多** 右一 | **多** 右二 |' in text
    assert text.index('| 1 | 最终名称') < text.index('| 2 | 扬声器')
    assert cells == before


def test_review_indexes_keep_duplicate_evidence_and_independent_copies():
    rules = Rules()
    rules.items_by_no[14]['source_rows'].append('共用来源')
    rules.row_to_item['共用来源'] = 11
    raw = RawTable(model='竞品', trims=[Trim(0, '右版')], rows=[
        RawRow('车顶行李架', [Cell('●', '第一次')], '外部配置'),
        RawRow('共用来源', [Cell('●', '共用')], '扩展配置'),
        RawRow('车顶行李架', [Cell('○', '第二次')], '其他配置')])
    right = build_ladder(raw, rules)
    left = Ladder(side='self', model='本品', trims=[{'name': '左版'}], items=[
        LadderItem(14, '行李架', ['●'], note='第一条'),
        LadderItem(14, '重复项', ['✕'], note='第二条')])
    pairs = [{'self_trim': '左版', 'comp_trim': '右版'}] * 2
    cells = [{'pair': pair, 'no': no, 'self_config': '●', 'comp_config': '●'}
             for pair, no in ((0, 14), (0, 11), (1, 14))]
    groups = [{'valuation': {'detail': [{'no': 14, 'amount': 300}, {'no': 14, 'amount': 999}]}}] * 2
    before = deepcopy((left, right, cells, groups))
    result = build_review(left, right, pairs, rules, None, cells, groups)
    evidence = result['evidence']
    assert evidence[0]['amount'] == 300
    assert evidence[0]['left']['notes'] == ['输入依据：第一条']
    assert [row['name'] for row in evidence[0]['right']['rows']] == ['车顶行李架', '共用来源', '车顶行李架']
    assert [row['name'] for row in evidence[1]['right']['rows']] == ['共用来源']
    evidence[0]['right']['rows'][0]['cell']['text'] = '修改副本'
    assert evidence[2]['right']['rows'][0]['cell']['text'] == '第一次'
    assert (left, right, cells, groups) == before


def test_excel_styles_preserve_summary_and_literal_text(tmp_path):
    group = {'pair': {'self_trim': '=1+1', 'comp_trim': '右版'}, 'self_price': 10,
             'comp_price': 11, 'more': ['800V'], 'less': [],
             'valuation': {'config_adv': 2000, 'flat_adv': 12000, 'overall': None, 'detail': []}}
    path = tmp_path / 'report.xlsx'
    export_report(path, 'diff', {'groups': [group, deepcopy(group)], 'cells': []})
    book = load_workbook(path)
    try:
        summary = book['对比汇总']
        assert summary['A2'].font.bold and summary['B2'].font.bold
        assert summary['B3'].fill.fgColor.rgb == '00EFF8F1'
        assert summary['B4'].fill.fgColor.rgb == '00FFF2F1'
        assert summary['B5'].number_format == '0.##;[Red]-0.##'
        assert summary['B5'].font.color.rgb == '00243444'
        assert summary['B5'].border.left.style == 'thin'
        assert summary['B2'].alignment.horizontal == 'center'
        assert summary['B3'].alignment.vertical == 'top'
        assert summary['B5'].style_id == summary['C5'].style_id
        assert book['价格计算']['A2'].value == '=1+1'
        assert book['价格计算']['A2'].data_type == 's'
    finally:
        book.close()
