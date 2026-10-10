import hashlib

import pytest

from api.bridge import Bridge
from engine.ladder import build_ladder
from engine.mapper import n_high_voltage, n_seat_memory, n_sunroof
from engine.models import Cell, Ladder, RawRow, RawTable, Trim
from engine.seat_adjust import from_raw, legacy_summary


def _raw(voltage_name='高压平台（V）'):
    # Synthetic software fixtures, not additional vehicle configuration claims.
    return RawTable(model='MG 07', series_id='8563', trims=[
        Trim(idx=i, short=name, price_guide=10+i) for i, name in enumerate(('A', 'B', 'C'))
    ], rows=[
        RawRow(name='能源类型', cells=[Cell(text='纯电动') for _ in range(3)]),
        RawRow(name='天窗类型', cells=[Cell(dot='●', text='不可开启全景天窗') for _ in range(3)]),
        RawRow(name='光感天幕', cells=[Cell(dot='●') for _ in range(3)]),
        RawRow(name='主座椅调节方式', cells=[Cell(dot='●', text='6向电动') for _ in range(3)]),
        RawRow(name='副座椅调节方式', cells=[Cell(dot='●', text='10向电动') for _ in range(3)]),
        RawRow(name='主/副驾驶座电动调节', cells=[Cell(dot='●', text='主/副') for _ in range(3)]),
        RawRow(name='零重力座椅', cells=[Cell(dot='●', text='副驾驶') for _ in range(3)]),
        RawRow(name=voltage_name, cells=[Cell(text=str(700+i*100)) for i in range(3)]),
        RawRow(name='电动座椅记忆功能', cells=[
            Cell(dot='●', text='驾驶位'),
            Cell(dot='●', text='驾驶位', subs=[Cell(dot='●', text='副驾驶位')]),
            Cell(dot='●', text='驾驶位', subs=[Cell(dot='●', text='副驾驶位')]),
        ]),
    ])


def _seed_cache(tmp_path, raw):
    bridge = Bridge(str(tmp_path))
    capture = tmp_path/'raw'/'capture.json'
    raw.save(str(capture))
    key = hashlib.sha256(capture.read_bytes()+b'|cell-marker-v2').hexdigest()[:16]
    path = tmp_path/'阶梯'/('compare-'+key+'.json')
    cached = build_ladder(raw, bridge.rules)
    cached.item(18).values = [n_sunroof(raw, i, {}, include_terms=False) for i in range(3)]
    cached.item(35).values = [from_raw(raw, i, include_terms=False) for i in range(3)]
    # Freeze the actual pre-alias state: the old mapper did not see this row.
    # Calling the new high-voltage mapper here would hide a migration regression.
    cached.item(3).values = ['✕']*3
    cached.item(3).row_absent = True
    cached.item(45).values = ['✕']*3
    cached.item(45).row_absent = True
    cached.save(str(path))
    return bridge, path, cached


@pytest.mark.parametrize('voltage_name', ['高压平台（V）', '高压平台(V)'])
def test_cache_upgrades_untouched_terms_and_legacy_seats_without_losing_edits(tmp_path, voltage_name):
    raw = _raw(voltage_name)
    bridge, path, cached = _seed_cache(tmp_path, raw)
    capture_bytes = (tmp_path/'raw'/'capture.json').read_bytes()
    cached.item(18).values[1] = '○电动天窗（人工修正）'
    cached.item(35).values[1] = '主驾8向手调+副驾4向手调（人工修正）'
    cached.item(35).values[2] = legacy_summary(raw, 2)
    cached.item(3).values[1] = '●400V（人工修正）'
    cached.item(45).values[1] = '副驾座椅记忆（人工修正）'
    cached.item(17).values = ['A人工灯光', 'B人工灯光', 'C人工灯光']
    cached.trims[1]['price_guide'] = 17.68
    # A cached trim order may differ; migration must match names, not positions.
    cached.trims.reverse()
    for item in cached.items:
        item.values.reverse()
        for sub in item.subs:
            sub['values'].reverse()
    cached.save(str(path))
    original_trims = [dict(trim) for trim in cached.trims]

    result = bridge.prepare_competitor('capture.json')
    assert result['ok'], result
    assert result['path'] == str(path)
    migrated = Ladder.from_dict(result['ladder'])
    configs = {item['no']: item for item in bridge.rules.items}
    for i, source_i in enumerate((2, 1, 0)):
        if source_i == 1:
            assert migrated.item(18).values[i] == '○电动天窗（人工修正）'
            assert migrated.item(35).values[i] == '主驾8向手调+副驾4向手调（人工修正）'
            assert migrated.item(3).values[i] == '●400V（人工修正）'
            assert migrated.item(45).values[i] == '副驾座椅记忆（人工修正）'
        else:
            assert migrated.item(18).values[i] == n_sunroof(raw, source_i, configs[18])
            assert '光感天幕' in migrated.item(18).values[i]
            assert migrated.item(35).values[i] == from_raw(raw, source_i)
            assert '零重力' in migrated.item(35).values[i]
            assert migrated.item(3).values[i] == n_high_voltage(raw, source_i, configs[3])
            assert migrated.item(3).values[i] == f'●{700+source_i*100}V'
            assert migrated.item(45).values[i] == n_seat_memory(raw, source_i, configs[45])
            assert migrated.item(45).values[i] == ('主驾座椅记忆' if source_i == 0 else '前排座椅记忆')
    assert migrated.trims == original_trims
    assert migrated.item(17).values == ['C人工灯光', 'B人工灯光', 'A人工灯光']
    assert not migrated.item(3).row_absent
    assert not migrated.item(45).row_absent
    assert (tmp_path/'raw'/'capture.json').read_bytes() == capture_bytes
    migrated_bytes = path.read_bytes()
    again = bridge.prepare_competitor('capture.json')
    assert again['ok'] and again['path'] == str(path)
    assert again['ladder'] == result['ladder']
    assert path.read_bytes() == migrated_bytes


@pytest.mark.parametrize('no,alias,manual_value', [
    (3, '高压平台（V）', '●400V（人工修正）'),
    (45, '电动座椅记忆功能', '副驾座椅记忆（人工修正）'),
])
@pytest.mark.parametrize('row_absent,edited,has_alias,expected_absent', [
    (False, False, True, False),
    (True, True, True, False),
    (True, False, False, True),
])
def test_source_alias_migration_requires_old_absence_and_unedited_value(tmp_path, no, alias, manual_value, row_absent, edited, has_alias, expected_absent):
    raw = _raw()
    if not has_alias:
        raw.rows = [row for row in raw.rows if row.name != alias]
    bridge, path, cached = _seed_cache(tmp_path, raw)
    value = manual_value if edited else '✕'
    cached.item(no).row_absent = row_absent
    cached.item(no).values = [value]*3
    cached.save(str(path))
    result = bridge.prepare_competitor('capture.json')
    assert result['ok'], result
    item = Ladder.from_dict(result['ladder']).item(no)
    assert item.values == [value]*3
    assert item.row_absent == expected_absent


def test_new_term_source_rows_refresh_absence_without_replacing_manual_seats(tmp_path):
    raw = _raw()
    raw.rows = [row for row in raw.rows if row.name not in {
        '天窗类型', '主座椅调节方式', '副座椅调节方式', '主/副驾驶座电动调节',
    }]
    bridge, path, cached = _seed_cache(tmp_path, raw)
    for no in (18, 35):
        cached.item(no).row_absent = True
    # With no old adjustment rows, legacy_summary's default is not source evidence.
    cached.item(35).values[1] = '主副手调'
    cached.save(str(path))
    result = bridge.prepare_competitor('capture.json')
    assert result['ok'], result
    migrated = Ladder.from_dict(result['ladder'])
    assert not migrated.item(18).row_absent
    assert not migrated.item(35).row_absent
    assert migrated.item(18).values[0] == n_sunroof(raw, 0, {})
    assert '光感天幕' in migrated.item(18).values[0]
    assert migrated.item(35).values[0] == from_raw(raw, 0)
    assert migrated.item(35).values[1] == '主副手调'
