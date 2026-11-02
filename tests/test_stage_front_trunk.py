"""Front-trunk capacity and opening type share one ladder description."""
from pathlib import Path

from openpyxl import load_workbook
import pytest

from api.bridge import Bridge
from engine import stage_one
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, RawRow, RawTable, Trim
from engine.rules import Rules


VOLUME_ROWS = ('前备厢容积(L)', '前备厢容积（L）', '前备箱容积(L)', '前备箱容积（L）')


def table(rows):
    count = len(next(iter(rows.values())))
    return RawTable(model='前备箱阶梯测试',
                    trims=[Trim(i, f'版型{i}', price_guide=10+i) for i in range(count)],
                    rows=[RawRow(name, cells) for name, cells in rows.items()])


def items(raw, target=0, base=None, excluded=None):
    features = stage_one.features(raw, excluded_rows=excluded)
    return stage_one._compact_items(stage_one._change_items(features, target, base), base)


@pytest.mark.parametrize('volume_name', VOLUME_ROWS)
@pytest.mark.parametrize('reverse', [False, True])
def test_capacity_and_type_merge_even_when_capacity_is_hidden(volume_name, reverse):
    rows = {
        volume_name: [Cell(text='108'), Cell(text='108'), Cell(text='108'), Cell(), Cell(text='0')],
        '电动前备箱': [Cell(), Cell(dot='●'), Cell(dot='○'), Cell(), Cell()],
    }
    raw = table(dict(reversed(list(rows.items()))) if reverse else rows)
    original = raw.to_json()
    calculated = map_raw_to_ladder(raw, Rules())
    expected = [['108L手动前备箱'], ['108L电动前备箱'], ['108L手动前备箱'], [], []]
    for excluded in (None, [], [*stage_one.DEFAULT_EXCLUDED_ROWS, volume_name]):
        assert [items(raw, i, excluded=excluded) for i in range(5)] == expected
    assert raw.to_json() == original
    assert map_raw_to_ladder(raw, Rules()) == calculated


@pytest.mark.parametrize('volume_name', VOLUME_ROWS)
def test_capacity_alone_is_manual_and_does_not_require_an_electric_row(volume_name):
    raw = table({volume_name: [Cell(text='108'), Cell(text='108.5'), Cell(text='-'), Cell(text='0')]})
    assert [items(raw, i, excluded=[volume_name]) for i in range(4)] == [
        ['108L手动前备箱'], ['108.5L手动前备箱'], [], [],
    ]


def comparison_table():
    return table({
        '前备厢容积(L)': [Cell(), Cell(text='108'), Cell(text='108'), Cell(text='180'), Cell(text='108')],
        '电动前备箱': [Cell(), Cell(), Cell(dot='●'), Cell(), Cell()],
    })


def test_type_capacity_presence_and_selected_baseline_control_the_difference():
    raw = comparison_table()
    original = raw.to_json()
    assert items(raw, 1, 0) == ['108L手动前备箱']
    assert items(raw, 2, 1) == ['电动前备箱(手动前备箱)']
    assert items(raw, 3, 1) == ['180L手动前备箱(108L手动前备箱)']
    assert items(raw, 4, 1) == []
    assert items(raw, 0, 1) == ['无（108L手动前备箱）']
    assert raw.to_json() == original


def test_different_capacity_opening_type_switch_omits_capacity_in_both_directions():
    raw = table({
        '前备厢容积(L)': [Cell(text='108'), Cell(text='180')],
        '电动前备箱': [Cell(), Cell(dot='●')],
    })
    assert items(raw, 0) == ['108L手动前备箱']
    assert items(raw, 1) == ['180L电动前备箱']
    assert items(raw, 1, 0) == ['电动前备箱(手动前备箱)']
    assert items(raw, 0, 1) == ['手动前备箱(电动前备箱)']


@pytest.mark.parametrize('name', ['电动前备箱', '电动前备厢', '手动前备箱'])
def test_without_capacity_existing_functional_rows_still_display(name):
    raw = table({name: [Cell(dot='●'), Cell()]})
    assert items(raw) == [name]
    assert items(raw, 1) == []


def test_source_aliases_and_identical_specialty_rows_do_not_duplicate_the_summary():
    electric = table({
        '前备厢容积(L)': [Cell(text='108')],
        '电动前备箱': [Cell(dot='●')],
        '电动前备厢': [Cell(dot='●')],
        '前备箱': [Cell(dot='●', text='电动')],
    })
    assert items(electric) == ['108L电动前备箱']
    manual = table({
        '前备厢容积(L)': [Cell(text='108')],
        '电动前备箱': [Cell()],
        '108L手动前备箱': [Cell(dot='●')],
        '108L拍一拍干湿多用前备箱': [Cell(dot='●')],
        '拍一拍轻松开启前备箱': [Cell(dot='●')],
    })
    for row in manual.rows[2:]:
        row.group = '特色配置'
    result = items(manual)
    assert result.count('108L手动前备箱') == 1
    assert len(result) == len(set(result))


@pytest.mark.parametrize('volumes,electric,expected', [
    (['108', '108'], [True, False], '手动前备箱(电动前备箱)'),
    (['180', '108'], [False, False], '108L手动前备箱(180L手动前备箱)'),
])
def test_opening_type_or_capacity_downgrade_is_grouped_under_removals(tmp_path, volumes, electric, expected):
    raw = table({
        '前备厢容积(L)': [Cell(text=value) for value in volumes],
        '电动前备箱': [Cell(dot='●') if value else Cell() for value in electric],
    })
    bridge = Bridge(str(tmp_path / 'work'))
    bridge.stage_raw = raw
    try:
        preview = bridge.stage_preview([{'target': 0, 'base': None}, {'target': 1, 'base': 0}])
        assert preview['ok'], preview
        assert preview['columns'][1]['items'] == [expected]
        assert preview['columns'][1]['display_items'] == []
        assert preview['columns'][1]['removed_items'] == [expected]
    finally:
        bridge.shutdown()


def test_preview_markdown_excel_share_merged_labels_and_keep_raw_unchanged(tmp_path):
    raw = comparison_table()
    original = raw.to_json()
    calculated = map_raw_to_ladder(raw, Rules())
    # Use the manual trim as the primary baseline to include a loss as well.
    plan = [{'target': 1, 'base': None}, {'target': 2, 'base': 1},
            {'target': 3, 'base': 1}, {'target': 4, 'base': 1}, {'target': 0, 'base': 1}]
    expected = [['108L手动前备箱'], ['电动前备箱(手动前备箱)'],
                ['180L手动前备箱(108L手动前备箱)'], [], ['无（108L手动前备箱）']]
    bridge = Bridge(str(tmp_path / 'work'))
    bridge.stage_raw = raw
    bridge.save_file_dialog = lambda name, *_: str(tmp_path / name)
    try:
        assert bridge.save_stage_display_rules(list(VOLUME_ROWS))['ok']
        preview = bridge.stage_preview(plan)
        assert preview['ok'], preview
        assert [column['items'] for column in preview['columns']] == expected
        assert preview['columns'][-1]['display_items'] == []
        assert preview['columns'][-1]['removed_items'] == ['108L手动前备箱']
        markdown = bridge.stage_export(plan, choose_path=True)
        assert markdown['ok'], markdown
        assert Path(markdown['path']).read_text(encoding='utf-8') == markdown['md']
        for column in expected:
            for label in column:
                assert label + '  \n' in markdown['md']
        assert '前备厢容积' not in markdown['md']
        excel = bridge.export_excel('ladder', plan)
        assert excel['ok'], excel
        book = load_workbook(excel['path'])
        try:
            sheet = book['配置阶梯']
            for row, column in enumerate(preview['columns'], 2):
                assert (sheet.cell(row, 5).value or '') == '\n'.join(column['items'])
                assert (sheet.cell(row, 6).value or '') == '\n'.join(column['options'])
        finally:
            book.close()
        assert raw.to_json() == original
        assert map_raw_to_ladder(raw, Rules()) == calculated
    finally:
        bridge.shutdown()
