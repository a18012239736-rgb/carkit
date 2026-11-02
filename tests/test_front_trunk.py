import hashlib
from pathlib import Path

import pytest

from api.bridge import Bridge
from engine import ladder as ladder_mod, rawschema
from engine.differ import diff
from engine.ladder import build_ladder
from engine.mapper import map_raw_to_ladder
from engine.models import Ladder, LadderItem
from engine.rules import Rules
from engine.valuer import _default_rule_amount


def test_front_trunk_tiers_in_both_directions():
    for left, right, verdict, amount in [
        ('手动前备箱', '✕', '多', 500),
        ('电动前备箱', '✕', '多', 1000),
        ('电动前备箱', '手动前备箱', '多', 500),
        ('手动前备箱', '电动前备箱', '少', 500),
        ('手动前备箱', '手动前备箱', '同', 0),
    ]:
        def ladder(v):
            return Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=12, name='前备箱', values=[v])])
        cell = next(c for c in diff(ladder(left), ladder(right), [{'self_trim':'A','comp_trim':'A'}], Rules()) if c['no']==12)
        assert cell['verdict'] == verdict
        assert _default_rule_amount(12, cell['backup_more'] or cell['backup_less'], 'more') == amount


def _raw(rows):
    count = len(next(iter(rows.values())))
    return rawschema.from_compact({
        'headers': [f'前备箱回归 2026款 版型{i}' for i in range(count)],
        'rows': [
            {'n': '能源类型', 'v': ['纯电动'] * count},
            {'n': '厂商指导价(元)', 'v': ['10万'] * count},
            *({'n': name, 'v': values} for name, values in rows.items()),
        ],
    })


@pytest.mark.parametrize('volume_name', [
    '前备厢容积(L)', '前备厢容积（L）', '前备箱容积(L)', '前备箱容积（L）',
])
def test_a06_volume_and_electric_equipment_are_resolved_per_trim(volume_name):
    # Synthetic five-column reduction of the A06 shapes: electric, manual,
    # optional electric, no capacity, and zero capacity.
    raw = _raw({
        '电动前备箱': ['●', '-', '○', '-', '-'],
        volume_name: ['108', '108', '108', '-', '0'],
    })
    mapped = map_raw_to_ladder(raw, Rules())[12]
    assert mapped['values'] == ['电动前备箱', '手动前备箱', '手动前备箱', '✕', '✕']
    assert mapped['row_absent'] is False
    assert build_ladder(raw, Rules()).item(12).values == mapped['values']


@pytest.mark.parametrize('volume_name', [
    '前备厢容积(L)', '前备厢容积（L）', '前备箱容积(L)', '前备箱容积（L）',
])
def test_positive_capacity_without_an_electric_row_is_manual(volume_name):
    mapped = map_raw_to_ladder(_raw({volume_name: ['0.5', '108', '0', '-']}), Rules())[12]
    assert mapped['values'] == ['手动前备箱', '手动前备箱', '✕', '✕']
    assert mapped['row_absent'] is False


def test_absent_capacity_does_not_turn_absent_or_optional_electric_trunk_into_manual():
    mapped = map_raw_to_ladder(_raw({'电动前备箱': ['-', '○', '●']}), Rules())[12]
    assert mapped['values'] == ['✕', '○(选装)', '电动前备箱']
    absent = map_raw_to_ladder(_raw({'后备厢容积(L)': ['108']}), Rules())[12]
    assert absent['values'] == ['✕']
    assert absent['row_absent'] is True


@pytest.mark.parametrize('row,value,expected', [
    ('电动前备箱', '●', '电动前备箱'),
    ('电动前备厢', '●', '电动前备箱'),
    ('前备箱', '●手动', '手动前备箱'),
    ('前备厢', '●电动', '电动前备箱'),
])
def test_explicit_front_trunk_equipment_keeps_existing_interpretation(row, value, expected):
    raw = _raw({row: [value], '前备厢容积(L)': ['0']})
    assert map_raw_to_ladder(raw, Rules())[12]['values'] == [expected]


def _legacy_ladder(raw, rules):
    saved = build_ladder(raw, rules)
    saved.item(12).values = ['✕', '电动前备箱', '[待定]人工核实开启方式']
    saved.item(12).row_absent = True
    saved.trims[1]['price_guide'] = 12.34
    saved.trims.reverse()
    for item in saved.items:
        item.values.reverse()
        for sub in item.subs:
            sub['values'].reverse()
    return saved


def test_prepare_competitor_upgrades_old_absence_in_place_and_preserves_manual_values(tmp_path):
    bridge = Bridge(str(tmp_path))
    try:
        raw = _raw({'前备厢容积(L)': ['108', '80', '60']})
        capture = tmp_path / 'raw' / 'capture.json'
        raw.save(capture)
        original = capture.read_bytes()
        key = hashlib.sha256(original + b'|cell-marker-v2').hexdigest()[:16]
        path = tmp_path / '阶梯' / f'compare-{key}.json'
        cached = _legacy_ladder(raw, bridge.rules)
        cached.save(path)

        result = bridge.prepare_competitor(capture.name)
        assert result['ok'], result
        assert result['path'] == str(path)
        actual = Ladder.from_dict(result['ladder'])
        assert actual.item(12).values == ['[待定]人工核实开启方式', '电动前备箱', '手动前备箱']
        assert actual.item(12).row_absent is False
        assert actual.trims == cached.trims
        assert Ladder.load(path).to_dict() == actual.to_dict()
        assert capture.read_bytes() == original
        migrated = path.read_bytes()
        assert bridge.prepare_competitor(capture.name) == result
        assert path.read_bytes() == migrated
    finally:
        bridge.shutdown()


def test_load_ladder_upgrades_source_backed_absence_and_keeps_manual_values(tmp_path):
    bridge = Bridge(str(tmp_path))
    try:
        raw = _raw({'前备箱容积（L）': ['108', '80', '60']})
        saved = _legacy_ladder(raw, bridge.rules)
        path = tmp_path / 'old-ladder.json'
        saved.save(path)
        result = bridge.load_ladder(str(path))
        assert result['ok'], result
        actual = Ladder.from_dict(result['ladder'])
        assert actual.item(12).values == ['[待定]人工核实开启方式', '电动前备箱', '手动前备箱']
        assert actual.item(12).row_absent is False
        assert actual.trims == saved.trims
    finally:
        bridge.shutdown()


def test_frozen_plan_load_and_recalculation_do_not_upgrade_old_front_trunk_values(tmp_path, monkeypatch):
    bridge = Bridge(str(tmp_path))
    try:
        left = build_ladder(_raw({'电动前备箱': ['-']}), bridge.rules, model='本品')
        right = build_ladder(_raw({'前备厢容积(L)': ['108']}), bridge.rules, model='竞品')
        right.item(12).values = ['✕']
        right.item(12).row_absent = True
        left_path, right_path = tmp_path / 'left.json', tmp_path / 'right.json'
        left.save(left_path)
        right.save(right_path)
        pair = [{'self_trim': '版型0', 'comp_trim': '版型0'}]
        # Save the same inputs a pre-fix program would have archived.
        with monkeypatch.context() as old_program:
            old_program.setattr(ladder_mod, 'upgrade_ladder', lambda ladder, rules: ladder)
            report = bridge.run_diff(str(left_path), str(right_path), pair, left_is_competitor=True)
        assert report['ok'], report
        saved = bridge.save_comparison_plan('前备箱旧规则方案', report['comparison_id'])
        assert saved['ok'], saved
        archive = Path(bridge.workdir) / '方案' / saved['file']
        original_archive = archive.read_bytes()
        opened = bridge.open_comparison_plan(saved['file'])
        assert opened['ok'], opened
        paths = opened['paths']
        work_copy = Path(paths['right']).read_bytes()

        loaded = bridge.load_ladder(paths['right'])
        assert loaded['ok'], loaded
        assert Ladder.from_dict(loaded['ladder']).item(12).values == ['✕']
        assert Path(paths['right']).read_bytes() == work_copy
        repeated = bridge.run_diff(paths['left'], paths['right'], pair, paths['valuation'], True, opened['session'])
        assert repeated['ok'], repeated
        assert next(cell for cell in repeated['cells'] if cell['no'] == 12)['comp_val'] == '✕'
        assert repeated['groups'] == report['groups']
        assert archive.read_bytes() == original_archive
    finally:
        bridge.shutdown()
