"""Keep local calculation indexes fresh and preserve first-match semantics."""
from types import SimpleNamespace

import pytest

from engine import airbags, differ, seat_adjust, valuer
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim, ValuationTable


def test_diff_indexes_keep_first_items_and_trim_aliases_without_stale_state(monkeypatch):
    left = Ladder(trims=[{'name': '基础'}, {'name': '基础'}, {'name': '旗舰版'}], items=[
        LadderItem(11, '电动吸合门', ['●', '✕', '●']),
        LadderItem(11, '重复来源', ['✕', '✕', '✕']),
    ])
    right = Ladder(trims=[{'name': '竞品版'}], items=[LadderItem(11, '电动吸合门', ['✕'])])
    rules = SimpleNamespace(items=[{'no': 11, 'name': '电动吸合门', 'value_type': 'bool'}],
                            range_bands=lambda: [])
    pairs = [{'self_trim': '基础', 'comp_trim': '竞品'},
             {'self_trim': '旗舰', 'comp_trim': '竞品版'}]

    def unexpected_scan(no):
        raise AssertionError('The diff should reuse its item index')

    monkeypatch.setattr(left, 'item', unexpected_scan)
    monkeypatch.setattr(right, 'item', unexpected_scan)
    assert [cell['verdict'] for cell in differ.diff(left, right, pairs, rules)] == ['多', '多']
    left.items[0].values[0] = '✕'
    assert [cell['verdict'] for cell in differ.diff(left, right, pairs, rules)] == ['同', '多']


def test_backup_partitions_cells_once_and_keeps_pair_and_item_order():
    class Cells(list):
        scans = 0

        def __iter__(self):
            self.scans += 1
            return super().__iter__()

    cells = Cells([
        {'pair': 1, 'no': 38, 'verdict': '少', 'backup_more': '', 'backup_less': '后扬声器'},
        {'pair': 0, 'no': 27, 'verdict': '多', 'backup_more': '方向盘加热', 'backup_less': ''},
        {'pair': 1, 'no': 5, 'verdict': '少', 'backup_more': '', 'backup_less': '气囊'},
        {'pair': 0, 'no': 27, 'verdict': '多', 'backup_more': '更新的方向盘加热', 'backup_less': ''},
    ])
    pairs = [{'self_trim': '左', 'comp_trim': '右'} for _ in range(2)]
    groups = differ.assemble_backup(cells, pairs, '左车型', '右车型', {'左': 10}, {'右': 11})
    assert cells.scans == 1
    assert groups[0]['more'] == ['更新的方向盘加热']
    assert groups[1]['less'] == ['气囊', '后扬声器']
    assert groups[1]['less_items'] == [38, 5]
    assert all('self_floor_price' not in pair for pair in pairs)


@pytest.mark.parametrize('use_cells', [False, True])
def test_value_pair_reuses_loaded_item_for_amount_name_and_rule(monkeypatch, use_cells):
    table = ValuationTable(items=[{'no': 11, 'name': '电动吸合门', 'rule': 'flat',
                                  'pricing': 'flat', 'val': 2000, 'note': '确认金额'}])
    calls = []
    original = table.item

    def record(no):
        calls.append(no)
        return original(no)

    monkeypatch.setattr(table, 'item', record)
    cells = [{'no': 11, 'verdict': '多', 'self_config': '●', 'comp_config': '✕',
              'display': '多 电动吸合门'}] if use_cells else None
    result = valuer.value_pair({11: '电动吸合门'}, {}, 10, 11, table, cells=cells)
    assert calls == [11]
    assert result['config_adv'] == 2000
    assert result['detail'][0]['name'] == '电动吸合门'
    assert result['detail'][0]['rule'] == 'flat：2000 元；确认金额'


def test_rule_text_formats_selected_parameters_and_memory_total():
    table = ValuationTable(items=[
        {'no': 23, 'rule': 'dynamic', 'params': {'4g': 1200, '5g': 2400}},
        {'no': 45, 'rule': 'dynamic', 'params': {'per_seat': 150}},
        {'no': 999, 'rule': 'dynamic'},
    ])
    assert valuer.explain_rule(table, 23) == '4G车联网1200元，5G车联网2400元，无配置0元；按双方配置价值之差计价'
    assert valuer.explain_rule(table, 45) == '座椅记忆每座150元，前排主副驾合计300元；按双方配置价值之差计价'
    assert valuer.explain_rule(table, 999) == '未配置规则说明；按双方配置价值之差计价'
    assert table.items[1]['params'] == {'per_seat': 150}


@pytest.mark.parametrize('options', [{}, {'legacy_display': True}, {'legacy_price_notes': True}])
def test_seat_summary_reads_each_adjustment_row_once(monkeypatch, options):
    names = ('主/副驾驶座电动调节', '主座椅调节方式', '副座椅调节方式')
    raw = RawTable(trims=[Trim(0, '版型')], rows=[
        RawRow(names[0], [Cell(text='主驾●/副驾-')]),
        RawRow(names[1], [Cell(text='6向电动调节')]),
        RawRow(names[2], [Cell(text='4向手动调节')]),
    ])
    calls = []
    original = raw.row

    def record(*candidates):
        calls.extend(candidates)
        return original(*candidates)

    monkeypatch.setattr(raw, 'row', record)
    assert seat_adjust.from_raw(raw, 0, **options) == '主驾6向电调+副驾4向手调'
    assert [calls.count(name) for name in names] == [1, 1, 1]


def test_airbag_count_scans_source_rows_once_and_deduplicates_positions():
    class Rows(list):
        scans = 0

        def __iter__(self):
            self.scans += 1
            return super().__iter__()

    rows = Rows([
        RawRow('主/副驾驶座安全气囊', [Cell(dot='●', text='主/副')]),
        RawRow('前/后排侧气囊', [Cell(dot='●', text='前/后-')]),
        RawRow('前排中央气囊', [Cell(dot='●')]),
        RawRow('中央安全气囊', [Cell(dot='●')]),
        RawRow('膝部气囊', [Cell(dot='●', text='主驾●/副驾○')]),
        RawRow('主驾膝部气囊', [Cell(dot='●')]),
    ])
    raw = RawTable(trims=[Trim(0, '版型')], rows=rows)
    assert airbags.from_raw(raw, 0) == (6, ['主副', '前侧', '中央气囊', '主驾膝部气囊'])
    assert rows.scans == 1
