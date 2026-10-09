import copy
from pathlib import Path

from api.bridge import Bridge
from engine import rawschema
from engine.models import Ladder
from engine.seat_adjust import legacy_summary, parse


def test_q05_old_cache_recovers_directions_without_overwriting_manual_edits(tmp_path):
    raw = rawschema.detect_and_load(str(Path(__file__).parent / 'golden' / 'raw-Q05-汽车之家全表-2026-09-11.json'))
    bridge = Bridge(str(tmp_path))
    try:
        source = tmp_path / 'raw' / 'Q05.json'
        raw.save(source)
        first = bridge.prepare_competitor(source.name)
        assert first['ok'], first
        cached = Ladder.from_dict(first['ladder'])
        seat = cached.item(35)
        seat.values = [legacy_summary(raw, i) for i in range(len(raw.trims))]
        manual = '主驾8向电调+副驾4向手调(人工确认)'
        seat.values[1] = manual
        cached.save(first['path'])
        before = copy.deepcopy(cached.to_dict())

        refreshed = bridge.prepare_competitor(source.name)
        assert refreshed['ok'], refreshed
        updated = Ladder.from_dict(refreshed['ladder'])
        assert updated.item(35).values[1] == manual
        assert [s['count'] for s in parse(updated.item(35).values[0])['seats']] == [6, 4]
        assert [s['count'] for s in parse(updated.item(35).values[3])['seats']] == [6, 6]
        assert [s['mode'] for s in parse(updated.item(35).values[3])['seats']] == ['电调', '电调']
        assert updated.trims == before['trims']
        for previous in before['items']:
            if previous['no'] != 35:
                assert updated.item(previous['no']).__dict__ == previous

        # A plain editor load/save must not reinterpret or drop the original text.
        loaded = bridge.load_ladder(first['path'])
        assert loaded['ok']
        assert bridge.save_ladder_edit(first['path'], loaded['ladder'])['ok']
        assert Ladder.load(first['path']).to_dict() == updated.to_dict()
        assert bridge.seat_adjust_details(manual) == {'ok': True, **parse(manual)}
    finally:
        bridge.shutdown()


def test_legacy_seat_functions_without_subrows_show_known_and_unknown_values():
    original = ['加热/通风/按摩(仅主驾)', '[待定]前排通风待核', '○前排座椅加热', '舒适座椅包', '✕']
    ladder = Ladder.from_dict({'items': [{'no': 36, 'name': '座椅功能', 'values': original}]})
    seat = ladder.item(36)
    expanded = {row['sub']: row['values'] for row in seat.subs}
    assert seat.values == original
    assert expanded['主驾通风'][0] == '●'
    assert expanded['副驾通风'][0] == '✕'
    assert all('[待定]' in values[1] for values in expanded.values())
    assert all('○前排座椅加热' in values[2] for values in expanded.values())
    assert all('舒适座椅包' in values[3] for values in expanded.values())
    assert all(values[4] == '✕' for values in expanded.values())
    assert Ladder.from_dict(ladder.to_dict()).to_dict() == ladder.to_dict()
