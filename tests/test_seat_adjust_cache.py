"""Revisiting a real capture upgrades auto seat summaries, never hand edits."""
from copy import deepcopy
import hashlib
from pathlib import Path

from api.bridge import Bridge
from engine import rawschema
from engine.ladder import build_ladder
from engine.models import Ladder
from engine.seat_adjust import from_raw, legacy_summary


def test_q05_mixed_auto_generations_and_manual_seats_survive_reordered_cache(tmp_path):
    fixture = Path(__file__).parent / 'golden' / 'raw-Q05-汽车之家全表-2026-09-11.json'
    fixture_bytes = fixture.read_bytes()
    raw = rawschema.detect_and_load(str(fixture))
    assert [trim.short for trim in raw.trims] == [
        '405Air', '405Max', '506Pro+', '506Max', '506Max+', '405激光极智', '506激光极智',
    ]
    old_values = [
        '主驾6向手调+副驾4向手调',
        '主驾6向电调+副驾4向电调(主含腰撑4向)',
        '主驾6向电调+副驾4向电调(主含腰撑4向)',
        '主驾6向电调+副驾6向电调(主腰撑4向/副腿托+腰撑4向)',
        '主驾6向电调+副驾6向电调(主腰撑4向/副腿托+腰撑4向)',
        '主驾6向电调+副驾4向电调(主含腰撑4向)',
        '主驾6向电调+副驾6向电调(主腰撑4向/副腿托+腰撑4向)',
    ]
    # Freeze the previous strings independently of the migration helpers.
    # All three generations agree for Q05, which has no zero-gravity alias.
    for options in ({'legacy_display': True},
                    {'legacy_display': True, 'include_terms': False},
                    {'legacy_price_notes': True}):
        assert [from_raw(raw, i, **options) for i in range(7)] == old_values
    assert legacy_summary(raw, 5) == '主副电调(主含腰撑4向)'
    current_values = [
        '主驾6向手调+副驾4向手调',
        '主驾6向电调+副驾4向电调',
        '主驾6向电调+副驾4向电调',
        '主驾6向电调+副驾6向电调',
        '主驾6向电调+副驾6向电调',
        '主驾6向电调+副驾4向电调',
        '主驾6向电调+副驾6向电调',
    ]
    assert [from_raw(raw, i) for i in range(7)] == current_values

    bridge = Bridge(str(tmp_path))
    try:
        capture = tmp_path / 'raw' / 'capture.json'
        raw.save(str(capture))
        capture_bytes = capture.read_bytes()
        key = hashlib.sha256(capture_bytes + b'|cell-marker-v2').hexdigest()[:16]
        cache_path = tmp_path / '阶梯' / ('compare-' + key + '.json')
        cached = build_ladder(raw, bridge.rules)
        manual = {
            0: '主驾6向手调+副驾4向手调(主含腰撑2向)',
            4: '主驾8向电调+副驾6向电调(主腰撑2向/副腰撑4向)',
        }
        cached.item(35).values = [
            manual[0],
            from_raw(raw, 1, legacy_display=True),
            from_raw(raw, 2, legacy_display=True, include_terms=False),
            from_raw(raw, 3, legacy_price_notes=True),
            manual[4],
            legacy_summary(raw, 5),
            from_raw(raw, 6, legacy_display=True),
        ]
        cached.item(17).values = [f'人工灯光{i}' for i in range(7)]
        cached.trims[0]['price_guide'] = 7.88
        cached.trims[4]['price_guide'] = 11.28
        # Migration matches source trim names, not the cached column position.
        cached.trims.reverse()
        for item in cached.items:
            item.values.reverse()
            for sub in item.subs:
                sub['values'].reverse()
        cached.save(str(cache_path))
        expected = deepcopy(cached.to_dict())
        expected_seats = next(item for item in expected['items'] if item['no'] == 35)
        expected_seats['values'] = [manual.get(i, current_values[i]) for i in reversed(range(7))]

        opened = bridge.prepare_competitor('capture.json')
        assert opened['ok'], opened
        assert opened['path'] == str(cache_path)
        assert opened['ladder'] == expected
        assert Ladder.load(str(cache_path)).to_dict() == expected
        assert capture.read_bytes() == capture_bytes
        assert fixture.read_bytes() == fixture_bytes

        migrated_bytes = cache_path.read_bytes()
        again = bridge.prepare_competitor('capture.json')
        assert again == opened
        assert cache_path.read_bytes() == migrated_bytes
        assert capture.read_bytes() == capture_bytes
        assert fixture.read_bytes() == fixture_bytes
    finally:
        bridge.shutdown()
