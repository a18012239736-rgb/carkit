"""The two historical automatic counts upgrade without discarding manual work."""
from copy import deepcopy

import pytest

from api.bridge import Bridge
from engine.airbags import SOURCE_ROWS
from engine.mapper import legacy_mapped_item
from engine.models import Cell, Ladder, RawRow, RawTable, Trim
from engine.rules import Rules


@pytest.mark.parametrize('legacy_side', [True, False])
def test_airbag_cache_upgrade_keeps_manual_counts_order_prices_and_raw(tmp_path, legacy_side):
    raw = RawTable(model='气囊缓存', trims=[Trim(i, name, price_guide=10+i) for i, name in enumerate('ABC')], rows=[
        RawRow('主/副驾驶座安全气囊', [Cell(dot='●', text='主●/副-'), Cell(dot='●', text='主●/副●'), Cell(dot='●', text='主●/副●')]),
        RawRow('前/后排侧气囊', [Cell(), Cell(dot='●', text='前●/后○'), Cell(dot='●', text='前●/后●')]),
        RawRow('前/后排头部气囊(气帘)', [Cell(dot='●', text='前●/后-'), Cell(dot='●', text='前●/后●'), Cell(dot='●', text='前●/后●')]),
        RawRow('前排中间气囊', [Cell(dot='●')]*3),
        RawRow('膝部气囊', [Cell(dot='●', text='主驾膝部气囊', subs=[Cell(dot='●', text='副驾膝部气囊')]), Cell(), Cell(dot='●', text='主驾膝部气囊')]),
    ])
    bridge = Bridge(str(tmp_path))
    try:
        capture = tmp_path/'raw'/'airbag.json'
        raw.save(str(capture))
        original = capture.read_bytes()
        fresh = bridge.prepare_competitor(capture.name)
        assert fresh['ok'], fresh
        expected = Ladder.from_dict(deepcopy(fresh['ladder']))
        cached = Ladder.from_dict(fresh['ladder'])
        cached.item(5).values = [legacy_mapped_item(raw, i, 5, legacy_side=legacy_side)['value'] for i in range(3)]
        cached.item(5).values[1] = '13气囊（人工核对）'
        cached.trims[1]['price_guide'] = 19.98
        cached.trims.reverse()
        for item in cached.items:
            item.values.reverse()
            for sub in item.subs:
                sub['values'].reverse()
        cached.save(fresh['path'])
        updated = bridge.prepare_competitor(capture.name)
        assert updated['ok'], updated
        actual = Ladder.from_dict(updated['ladder'])
        assert actual.trims == cached.trims
        assert actual.item(5).values == [expected.item(5).values[2], '13气囊（人工核对）', expected.item(5).values[0]]
        assert not actual.item(5).row_absent
        assert capture.read_bytes() == original
        assert bridge.prepare_competitor(capture.name)['ladder'] == updated['ladder']
    finally:
        bridge.shutdown()


def test_new_airbag_source_presence_updates_even_when_all_counts_are_manual(tmp_path):
    bridge = Bridge(str(tmp_path))
    try:
        capture = tmp_path/'raw'/'middle.json'
        RawTable(trims=[Trim(0, 'A', price_guide=10)], rows=[RawRow('前排中间气囊', [Cell(dot='●')])]).save(str(capture))
        fresh = bridge.prepare_competitor(capture.name)
        cached = Ladder.from_dict(fresh['ladder'])
        cached.item(5).values = ['9气囊（人工核对）']
        cached.item(5).row_absent = True  # Old checklist did not recognize this source row.
        cached.save(fresh['path'])
        updated = bridge.prepare_competitor(capture.name)
        actual = Ladder.from_dict(updated['ladder'])
        assert actual.item(5).values == cached.item(5).values
        assert not actual.item(5).row_absent
    finally:
        bridge.shutdown()


def test_airbag_source_rows_and_aliases_are_in_sync():
    rules = Rules()
    assert set(rules.items_by_no[5]['source_rows']) == set(SOURCE_ROWS)
    assert all(rules.row_to_item[name] == 5 for name in SOURCE_ROWS)


def test_middle_explicit_optional_text_overrides_an_inconsistent_parent_marker():
    from engine.mapper import n_airbag
    raw = RawTable(trims=[Trim(0, 'A')], rows=[RawRow('前排中间气囊', [Cell(dot='●', text='○选装')])])
    assert n_airbag(raw, 0, {}) == (0, [])
