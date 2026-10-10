"""Old automatic mistakes upgrade; explicit corrections keep their authority."""
import hashlib

from api.bridge import Bridge
from engine.ladder import build_ladder
from engine.mapper import legacy_mapped_item, map_raw_to_ladder
from engine.models import Cell, Ladder, RawRow, RawTable, Trim


def test_source_cache_upgrade_preserves_manual_values_subs_prices_and_order(tmp_path):
    # Synthetic mixed cells reproduce the shapes in the saved public captures.
    trims = [Trim(i, name, price_guide=10+i) for i, name in enumerate(('A','B','C'))]
    rows = {
        '能源类型': Cell(text='纯电动'),
        '辅助驾驶路段': Cell(dot='○', text='城市路段', subs=[Cell(dot='●', text='高速路段')]),
        '辅助驾驶等级': Cell(dot='●', text='L2'),
        '方向盘材质': Cell(dot='○', text='真皮', subs=[Cell(dot='●', text='仿皮')]),
        '座椅材质': Cell(dot='○', text='真皮', subs=[Cell(dot='●', text='仿皮')]),
        '液晶仪表尺寸': Cell(dot='○', text='8英寸', subs=[Cell(dot='●', text='10.2英寸')]),
        '全液晶仪表盘': Cell(dot='●'),
        '内后视镜功能': Cell(dot='●', text='自动防眩目', subs=[Cell(dot='○', text='流媒体')]),
        '前排座椅功能': Cell(dot='●', text='加热', subs=[Cell(dot='●', text='通风'), Cell(dot='●', text='头枕扬声器(仅驾驶位)')]),
    }
    raw = RawTable(model='缓存测试', trims=trims, rows=[RawRow(name=n, cells=[c]*3) for n,c in rows.items()])
    bridge = Bridge(str(tmp_path))
    capture = tmp_path/'raw'/'capture.json'
    raw.save(str(capture))
    original_raw = capture.read_bytes()
    key = hashlib.sha256(original_raw+b'|cell-marker-v2').hexdigest()[:16]
    path = tmp_path/'阶梯'/('compare-'+key+'.json')
    cached = build_ladder(raw, bridge.rules)
    affected = (9,25,29,31,34,36)
    for no in affected:
        item = cached.item(no)
        old = [legacy_mapped_item(raw, i, no) for i in range(3)]
        item.values = [v['value'] for v in old]
        if no == 36:
            for sub in item.subs:
                sub['values'] = [v['subs'][sub['sub']] for v in old]
        item.values[1] = '人工修正-'+str(no)
    # An explicit structured seat correction protects the complete C seat cell.
    cached.item(36).subs[0]['values'][2] = '[待定]人工座椅修正'
    c_seat = {sub['sub']:sub['values'][2] for sub in cached.item(36).subs}
    c_summary = cached.item(36).values[2]
    cached.trims[1]['price_guide'] = 19.98
    cached.trims.reverse()
    for item in cached.items:
        item.values.reverse()
        for sub in item.subs:
            sub['values'].reverse()
    cached.save(str(path))
    fresh = map_raw_to_ladder(raw, bridge.rules)
    result = bridge.prepare_competitor('capture.json')
    assert result['ok'], result
    actual = Ladder.from_dict(result['ladder'])
    assert result['path'] == str(path)
    assert actual.trims == cached.trims
    for no in affected:
        assert actual.item(no).values[2] == fresh[no]['values'][0]
        assert actual.item(no).values[1] == '人工修正-'+str(no)
        assert actual.item(no).values[0] == (c_summary if no == 36 else fresh[no]['values'][2])
    assert {sub['sub']:sub['values'][0] for sub in actual.item(36).subs} == c_seat
    assert {sub['sub']:sub['values'][2] for sub in actual.item(36).subs} == {
        sub['sub']:sub['values'][0] for sub in fresh[36]['subs']}
    assert capture.read_bytes() == original_raw
    saved = path.read_bytes()
    assert bridge.prepare_competitor('capture.json')['ladder'] == result['ladder']
    assert path.read_bytes() == saved


def test_reordered_mixed_powertrain_cache_matches_energy_and_missing_items_by_trim_name(tmp_path):
    raw = RawTable(model='缓存能源回归', trims=[Trim(0,'纯电版'),Trim(1,'燃油版')], rows=[
        RawRow(name='能源类型',cells=[Cell(text='纯电动'),Cell(text='汽油')]),
        RawRow(name='CLTC纯电续航里程(km)',cells=[Cell(text='500'),Cell()]),
        RawRow(name='电动座椅记忆功能',cells=[Cell(dot='●',text='驾驶位'),Cell()]),
        RawRow(name='前排座椅功能',cells=[Cell(dot='●',text='加热'),Cell()]),
    ])
    bridge = Bridge(str(tmp_path))
    try:
        capture = tmp_path/'raw'/'capture.json'
        raw.save(str(capture))
        original = capture.read_bytes()
        prepared = bridge.prepare_competitor(capture.name)
        cached = Ladder.from_dict(prepared['ladder'])
        cached.trims.reverse()
        for item in cached.items:
            item.values.reverse()
            for sub in item.subs:
                sub['values'].reverse()
        cached.items = [item for item in cached.items if item.no not in (36,45)]
        # A renamed unmatched trim must keep its manual energy and range.
        cached.trims.append({'name':'人工版型','energy_type':'纯电动','price_guide':19})
        for item in cached.items:
            item.values.append('600km' if item.no==1 else '人工配置')
            for sub in item.subs:
                sub['values'].append('●')
        cached.save(prepared['path'])
        result = bridge.prepare_competitor(capture.name)
        assert result['ok'], result
        actual = Ladder.from_dict(result['ladder'])
        assert [trim['energy_type'] for trim in actual.trims] == ['汽油','纯电动','纯电动']
        assert actual.item(1).values == ['不适用','500km','600km']
        assert actual.item(45).values == ['✕','主驾座椅记忆','[待定]原始版型未匹配']
        heating = next(sub for sub in actual.item(36).subs if sub['sub']=='主驾加热')
        assert heating['values'] == ['✕','●','[待定]原始版型未匹配']
        assert capture.read_bytes() == original
        assert bridge.prepare_competitor(capture.name)['ladder'] == result['ladder']
    finally:
        bridge.shutdown()
