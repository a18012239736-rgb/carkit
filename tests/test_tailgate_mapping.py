"""Only standard sensing on a powered tailgate reaches the priced value."""
import hashlib
from pathlib import Path

import pytest

from api.bridge import Bridge
from engine import ladder as ladder_mod
from engine.ladder import build_ladder, upgrade_ladder
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, Ladder, RawRow, RawTable, Trim
from engine.ppt_import import make_snapshot
from engine.rules import Rules


def raw_table(rows):
    count = len(next(iter(rows.values())))
    return RawTable(model='尾门识别测试',
                    trims=[Trim(i, f'版型{i}', price_guide=10+i) for i in range(count)],
                    rows=[RawRow(name, values) for name, values in rows.items()])


@pytest.mark.parametrize('powered_row', ['电动后备厢', '电动后备箱'])
@pytest.mark.parametrize('sensing_row', ['感应后备厢', '感应后备箱'])
def test_standard_sensing_and_position_memory_are_distinct_per_trim(powered_row, sensing_row):
    raw = raw_table({
        powered_row: [Cell(dot='●')] * 4,
        sensing_row: [Cell(dot='●'), Cell(dot='○'), Cell(), Cell()],
        '电动后备厢位置记忆': [Cell(dot='●'), Cell(dot='●'), Cell(dot='●'), Cell()],
    })
    before = raw.to_json()
    mapped = map_raw_to_ladder(raw, Rules())[13]
    assert mapped['values'] == ['感应电动后备箱(带位置记忆)', '●(带位置记忆)', '●(带位置记忆)', '●']
    assert mapped['row_absent'] is False
    assert build_ladder(raw, Rules()).item(13).values == mapped['values']
    assert raw.to_json() == before


def test_only_standard_tailgate_subitems_supply_sensing():
    raw = raw_table({'电动后备厢': [
        Cell(dot='●', text='感应式'),
        Cell(dot='●', text='位置记忆'),
        Cell(dot='●', subs=[Cell(dot='○', text='感应式')]),
        Cell(dot='○', text='感应式', subs=[Cell(dot='●', text='普通电动')]),
        Cell(dot='○', text='普通电动', subs=[Cell(dot='●', text='感应式')]),
    ]})
    assert map_raw_to_ladder(raw, Rules())[13]['values'] == [
        '感应电动后备箱', '●', '●', '●', '感应电动后备箱',
    ]


def test_sensing_or_memory_alone_never_implies_powered_tailgate():
    raw = raw_table({
        '电动后备厢': [Cell(), Cell(dot='○'), Cell()],
        '感应后备厢': [Cell(dot='●')] * 3,
        '电动后备厢位置记忆': [Cell(), Cell(), Cell(dot='●')],
    })
    assert map_raw_to_ladder(raw, Rules())[13]['values'] == ['✕', '○(选装)', '✕']
    sensor_only = raw_table({'感应后备箱': [Cell(dot='●')]})
    assert map_raw_to_ladder(sensor_only, Rules())[13]['values'] == ['✕']


def test_negative_pending_or_optional_sensing_is_not_standard_sensing():
    raw = raw_table({
        '电动后备厢': [Cell(dot='●')] * 5,
        '感应后备厢': [Cell(dot='●', text='无感应'), Cell(dot='●', text='[待定]'),
                       Cell(dot='●', text='?'), Cell(dot='○'), Cell(dot='●')],
    })
    assert map_raw_to_ladder(raw, Rules())[13]['values'] == ['●', '●', '●', '●', '感应电动后备箱']


def test_tailgate_and_memory_aliases_are_recorded_as_evidence_sources():
    raw = raw_table({
        '电动尾门': [Cell(dot='●')],
        '感应尾门': [Cell(dot='●')],
        '电动后备箱位置记忆': [Cell(dot='●')],
    })
    rules = Rules()
    assert map_raw_to_ladder(raw, rules)[13]['values'] == ['感应电动后备箱(带位置记忆)']
    assert all(rules.row_to_item[row.name] == 13 for row in raw.rows)
    assert all(row.name in rules.items_by_no[13]['source_rows'] for row in raw.rows)


@pytest.mark.parametrize('text,expected,rain', [
    ('感应电动后备箱', '感应电动后备箱', False),
    ('电动后备厢（感应式）', '感应电动后备箱', False),
    ('电动感应尾门', '感应电动后备箱', False),
    ('电动尾门+感应雨刮', '●', True),
    ('电动后备厢+雨量感应雨刷', '●', True),
    ('电动尾门+位置记忆', '●', False),
    ('感应后备厢\n电动尾门', '感应电动后备箱', False),
    ('感应后备箱', '✕', False),
])
def test_ppt_sensing_is_local_to_tailgate_and_requires_powered_equipment(text, expected, rain):
    snap = make_snapshot({'model': '尾门PPT测试', 'columns': [{'name': '基础型', 'text': text}]})
    cells = {cell['no']: cell['values']['基础型'] for cell in snap.cells}
    assert cells[13] == expected
    assert cells[44] == ('●' if rain else '✕')


def test_ppt_optional_sensing_and_inheritance_preserve_standard_tailgate():
    snap = make_snapshot({'model': '尾门继承测试', 'columns': [
        {'name': '基础型', 'text': '电动尾门'},
        {'name': '感应型', 'base': '基础型', 'text': '感应后备厢'},
        {'name': '确认型', 'base': '感应型', 'text': '电动尾门'},
        {'name': '选装型', 'base': '基础型', 'text': '电动尾门+选装感应电动尾门'},
    ]})
    assert next(cell for cell in snap.cells if cell['no'] == 13)['values'] == {
        '基础型': '●', '感应型': '感应电动后备箱', '确认型': '感应电动后备箱', '选装型': '●',
    }
    assert snap.options['选装型'] == ['感应电动尾门']


def legacy_ladder(raw, rules):
    saved = build_ladder(raw, rules)
    saved.item(13).values = ['●(带位置记忆)', '●', '[待定]人工确认感应', '✕']
    saved.trims[1]['price_guide'] = 19.98
    saved.trims.reverse()
    for item in saved.items:
        item.values.reverse()
        for sub in item.subs:
            sub['values'].reverse()
    return saved


@pytest.mark.parametrize('entry', ['prepare_competitor', 'load_ladder'])
def test_normal_history_upgrades_only_legacy_outputs_by_trim_name(tmp_path, entry):
    bridge = Bridge(str(tmp_path))
    try:
        raw = raw_table({
            '电动后备厢': [Cell(dot='●')] * 4,
            '感应后备厢': [Cell(dot='●')] * 4,
            '电动后备厢位置记忆': [Cell(dot='●')] * 4,
        })
        capture = tmp_path / 'raw' / 'capture.json'
        raw.save(capture)
        original_raw = capture.read_bytes()
        key = hashlib.sha256(original_raw + b'|cell-marker-v2').hexdigest()[:16]
        path = tmp_path / '阶梯' / f'compare-{key}.json'
        saved = legacy_ladder(raw, bridge.rules)
        saved.save(path)
        result = (bridge.prepare_competitor(capture.name) if entry == 'prepare_competitor'
                  else bridge.load_ladder(str(path)))
        assert result['ok'], result
        actual = Ladder.from_dict(result['ladder'])
        assert actual.item(13).values == ['✕', '[待定]人工确认感应', '●', '感应电动后备箱(带位置记忆)']
        assert actual.trims == saved.trims
        assert capture.read_bytes() == original_raw
        if entry == 'prepare_competitor':
            assert result['path'] == str(path)
            assert Ladder.load(path).item(13).values == actual.item(13).values
            migrated = path.read_bytes()
            assert bridge.prepare_competitor(capture.name) == result
            assert path.read_bytes() == migrated
    finally:
        bridge.shutdown()


def test_old_tailgate_without_raw_evidence_is_not_guessed():
    rules = Rules()
    saved = build_ladder(raw_table({'电动后备厢': [Cell(dot='●')]}), rules)
    saved.evidence = {}
    saved.item(13).values = ['●(带位置记忆)']
    assert upgrade_ladder(saved, rules).item(13).values == ['●(带位置记忆)']


def test_frozen_plan_does_not_upgrade_tailgate_sensing_on_load_or_recalculation(tmp_path, monkeypatch):
    bridge = Bridge(str(tmp_path))
    try:
        left = build_ladder(raw_table({'电动后备厢': [Cell(dot='●')]}), bridge.rules, model='本品')
        right = build_ladder(raw_table({
            '电动后备厢': [Cell(dot='●')], '感应后备厢': [Cell(dot='●')],
        }), bridge.rules, model='竞品')
        right.item(13).values = ['●']
        left_path, right_path = tmp_path / 'left.json', tmp_path / 'right.json'
        left.save(left_path)
        right.save(right_path)
        pairs = [{'self_trim': '版型0', 'comp_trim': '版型0'}]
        with monkeypatch.context() as previous_program:
            previous_program.setattr(ladder_mod, 'upgrade_ladder', lambda ladder, rules: ladder)
            report = bridge.run_diff(str(left_path), str(right_path), pairs, left_is_competitor=True)
        assert report['ok'], report
        record = bridge.save_comparison_plan('旧尾门方案', report['comparison_id'])
        assert record['ok'], record
        archive = Path(bridge.workdir) / '方案' / record['file']
        original_archive = archive.read_bytes()
        opened = bridge.open_comparison_plan(record['file'])
        assert opened['ok'], opened
        paths = opened['paths']
        original_work = Path(paths['right']).read_bytes()
        loaded = bridge.load_ladder(paths['right'])
        assert loaded['ok'], loaded
        assert Ladder.from_dict(loaded['ladder']).item(13).values == ['●']
        repeated = bridge.run_diff(paths['left'], paths['right'], pairs, paths['valuation'], True, opened['session'])
        assert repeated['ok'], repeated
        assert next(cell for cell in repeated['cells'] if cell['no'] == 13)['comp_val'] == '电动后备箱'
        assert repeated['groups'] == report['groups']
        assert Path(paths['right']).read_bytes() == original_work
        assert archive.read_bytes() == original_archive
    finally:
        bridge.shutdown()
