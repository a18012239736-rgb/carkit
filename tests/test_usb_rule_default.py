"""Implicit USB counts use the active rule; stored explicit counts never change."""
from copy import deepcopy
from dataclasses import asdict

import pytest

from api.bridge import Bridge
from engine.differ import diff
from engine.mapper import map_raw_to_ladder
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Snapshot, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.snapshot import prepare_snapshot, resolve
from engine.usb import usb_label, usb_total
from engine.valuer import _default_rule_amount, default_valuation, dynamic_delta, value_pair


@pytest.mark.parametrize('base,right,expected', [(3, '✕', 50), (2, '✕', 100), (0, '✕', 200),
    (2.5, '✕', 75), (2, 'USB/Type-C 3个', 50), (2, 'USB/Type-C 0个', 200)])
def test_implicit_usb_default_is_consistent_in_direct_and_full_calculation(base, right, expected):
    rules = Rules()
    data = default_valuation(rules)
    next(item for item in data['items'] if item['no'] == 32)['params'].update(base_count=base)
    valuation = ValuationTable(items=[ValuationItem(**item) for item in data['items']])
    params = {'base_count': base, 'per_port': 50}
    left = 'USB/Type-C 4个'
    assert dynamic_delta(32, left, right, params) == expected
    assert dynamic_delta(32, right, left, params) == -expected
    assert _default_rule_amount(32, '', 'more', params, values=(left, right)) == expected
    for ours, theirs, amount in [(left, right, expected), (right, left, -expected), (right, right, 0)]:
        a = Ladder.from_dict({'trims': [{'name': 'A'}], 'items': [{'no': 32, 'name': 'USB', 'values': [ours]}]})
        b = Ladder.from_dict({'trims': [{'name': 'B'}], 'items': [{'no': 32, 'name': 'USB', 'values': [theirs]}]})
        cells = [cell for cell in diff(a, b, [{'self_trim': 'A', 'comp_trim': 'B'}], rules, valuation) if cell['no'] == 32]
        assert value_pair({}, {}, 10, 10, valuation, cells=cells)['config_adv'] == amount


def test_save_and_capture_preserve_unspecified_and_explicit_counts(tmp_path):
    assert usb_total('✕', default=2) == 2
    assert usb_label('✕', default=2) == 'USB/Type-C 2个'
    assert usb_label('✕', preserve_default=True) == '✕'
    snap = prepare_snapshot(Snapshot(trims=[{'name': 'A'}, {'name': 'B'}],
        cells=[{'no': 32, 'values': {'A': '✕', 'B': 'USB/Type-C 3个'}}]))
    path = tmp_path/'snapshot.json'
    snap.save(path)
    reloaded = resolve(Snapshot.load(path))
    assert next(cell for cell in reloaded.cells if cell['no'] == 32)['values'] == {'A': '✕', 'B': 'USB/Type-C 3个'}
    ladder = Ladder.from_dict(reloaded.to_ladder(Rules().items).to_dict())
    assert ladder.item(32).values == ['✕', 'USB/Type-C 3个']
    empty = RawTable(trims=[Trim(0, 'A')], rows=[])
    assert map_raw_to_ladder(empty, Rules())[32]['values'] == ['✕']
    explicit = RawTable(trims=[Trim(0, 'A')], rows=[RawRow('USB/Type-C接口数量', [Cell(dot='●', text='前排2个/后排1个')])])
    assert map_raw_to_ladder(explicit, Rules())[32]['values'] == ['USB/Type-C 3个']


@pytest.mark.parametrize('left_is_competitor', [False, True])
def test_bridge_saved_rule_changes_default_without_rewriting_explicit_counts(tmp_path, left_is_competitor):
    bridge = Bridge(str(tmp_path))
    try:
        rules = bridge.rules
        right = Ladder(model='右侧', trims=[{'name': 'B', 'price_guide': 10}], items=[
            LadderItem(no=item['no'], name=item['name'], values=['USB/Type-C 4个' if item['no'] == 32 else '✕'])
            for item in rules.items])
        right_path = tmp_path/'right.json'
        right.save(right_path)
        if left_is_competitor:
            left = deepcopy(right)
            left.model = '左侧'; left.trims = [{'name': 'A', 'price_guide': 10}]
            left.item(32).values = ['✕']
            left_path = tmp_path/'left-ladder.json'
            assert bridge.save_ladder_edit(str(left_path), left.to_dict())['ok']
        else:
            left_path = tmp_path/'left-snapshot.json'
            left = Snapshot(model='左侧', trims=[{'name': 'A', 'price_guide': 10}], cells=[
                {'no': item['no'], 'values': {'A': '✕'}} for item in rules.items])
            assert bridge.save_snapshot(str(left_path), asdict(left))['ok']
        original = left_path.read_bytes()
        for base, amount in [(2, -100), (3, -50), (0, -200)]:
            data = default_valuation(rules)
            next(item for item in data['items'] if item['no'] == 32)['params']['base_count'] = base
            assert bridge.save_current_valuation(data)['ok']
            result = bridge.run_diff(str(left_path), str(right_path), [{'self_trim': 'A', 'comp_trim': 'B'}],
                                     left_is_competitor=left_is_competitor)
            assert result['ok'], result
            detail = [item for item in result['groups'][0]['valuation']['detail'] if item['no'] == 32]
            assert detail[0]['amount'] == amount
            assert left_path.read_bytes() == original
    finally:
        bridge.shutdown()


def test_usb_pending_and_not_applicable_still_skip_calculation():
    rules = Rules()
    data = default_valuation(rules)
    next(item for item in data['items'] if item['no'] == 32)['params']['base_count'] = 2
    valuation = ValuationTable(items=[ValuationItem(**item) for item in data['items']])
    for state in ('[待定]', '不适用'):
        a = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=32, name='USB', values=[state])])
        b = Ladder(trims=[{'name': 'B'}], items=[LadderItem(no=32, name='USB', values=['USB/Type-C 4个'])])
        cells = [cell for cell in diff(a, b, [{'self_trim': 'A', 'comp_trim': 'B'}], rules, valuation) if cell['no'] == 32]
        assert cells[0]['verdict'] == '不计'
        assert value_pair({}, {}, 10, 10, valuation, cells=cells)['config_adv'] == 0
