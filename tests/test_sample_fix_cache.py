"""Sample fixes upgrade untouched source values, never a user's corrections."""
from copy import deepcopy
from engine.mapper import legacy_mapped_item, n_seat_func
from engine.models import Cell, Ladder, RawRow, RawTable, Trim
from api.bridge import Bridge


def test_sample_fixes_upgrade_in_place_keep_manual_cells_and_prices(tmp_path):
    raw = RawTable(model='样本修复缓存', trims=[Trim(i, name, price_guide=10+i) for i, name in enumerate(('A','B','C'))], rows=[
        RawRow('能源类型', [Cell(text='纯电动')]*3),
        RawRow('驾驶辅助影像', [Cell(dot='●',text='倒车影像',subs=[Cell(dot='○',text='360度全景影像(3000元)')])]*3),
        RawRow('中控屏幕尺寸', [Cell(dot='○',text='10.1英寸')]*3),
        RawRow('副驾娱乐屏尺寸', [Cell(dot='●',text='14.6英寸')]*3),
        RawRow('手机无线充电功能', [Cell(dot='●',text='前排',subs=[Cell(dot='●',text='后排')])]*3),
        RawRow('手机无线充电功率', [Cell(dot='●',text='15W')]*3),
        RawRow('主/副驾驶座电动调节', [Cell(dot='●',text='主●/副○ (2000元)')]*3),
        RawRow('主座椅调节方式', [Cell(dot='●',text='6向')]*3),
        RawRow('副座椅调节方式', [Cell(dot='●',text='4向')]*3),
        RawRow('前排座椅功能', [Cell(dot='●',text='头枕扬声器')]*3),
    ])
    bridge = Bridge(str(tmp_path))
    try:
        path = tmp_path/'raw'/'sample.json'
        raw.save(str(path))
        original = path.read_bytes()
        fresh = bridge.prepare_competitor(path.name)
        assert fresh['ok'], fresh
        cached = Ladder.from_dict(fresh['ladder'])
        updated = Ladder.from_dict(deepcopy(fresh['ladder']))
        affected = (7,21,22,33,35,36)
        for no in affected:
            item = cached.item(no)
            for i in range(3):
                if no == 36:
                    value, _, subs = n_seat_func(raw,i,{},assume_front=False)
                    for sub in item.subs:
                        sub['values'][i] = subs[sub['sub']]
                else:
                    value = legacy_mapped_item(raw,i,no)['value']
                item.values[i] = value
            item.values[1] = f'人工修正-{no}'
        cached.item(36).subs[0]['values'][2] = '[待定]人工分项'
        old_seat_value = cached.item(36).values[2]
        cached.trims[1]['price_guide'] = 19.98
        cached.trims.reverse()
        for item in cached.items:
            item.values.reverse()
            for sub in item.subs:
                sub['values'].reverse()
        cached.save(fresh['path'])
        actual = bridge.prepare_competitor(path.name)
        assert actual['ok'], actual
        result = Ladder.from_dict(actual['ladder'])
        assert result.trims == cached.trims
        for no in affected:
            assert result.item(no).values[2] == updated.item(no).values[0]
            assert result.item(no).values[1] == f'人工修正-{no}'
            assert result.item(no).values[0] == (old_seat_value if no==36 else updated.item(no).values[2])
        assert next(sub for sub in result.item(36).subs if sub['sub']==cached.item(36).subs[0]['sub'])['values'][0] == '[待定]人工分项'
        assert path.read_bytes() == original
        assert bridge.prepare_competitor(path.name)['ladder'] == actual['ladder']
    finally:
        bridge.shutdown()
