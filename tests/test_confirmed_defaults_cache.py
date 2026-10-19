from copy import deepcopy
import json

from api.bridge import Bridge
from engine.mapper import legacy_mapped_item
from engine.models import Cell, Ladder, RawRow, RawTable, Trim


def test_latest_mapping_cache_updates_untouched_cells_preserves_manual_changes(tmp_path):
    raw = RawTable(model='口径缓存',trims=[Trim(0,'A',price_guide=10),Trim(1,'B',price_guide=11)],rows=[
        RawRow('能源类型',[Cell(text='纯电动')]*2),
        RawRow('前/后排侧气囊',[Cell(dot='●',text='前●/后○ (3300元)')]*2),
        RawRow('可变悬架功能',[Cell(dot='●',text='软硬调节',subs=[Cell(dot='●',text='高低调节')])]*2),
        RawRow('车内环境氛围灯',[Cell(dot='●',text='1680万色')]*2),
    ])
    bridge = Bridge(str(tmp_path))
    try:
        path=tmp_path/'raw'/'source.json'; raw.save(str(path))
        original=path.read_bytes()
        fresh=bridge.prepare_competitor(path.name)
        assert fresh['ok'], fresh
        expected=Ladder.from_dict(deepcopy(fresh['ladder']))
        cached=Ladder.from_dict(fresh['ladder'])
        for no in (5,6,39):
            cached.item(no).values[0]=legacy_mapped_item(raw,0,no)['value']
            cached.item(no).values[1]='人工改值-'+str(no)
        cached.trims[1]['price_guide']=19.98
        cached.save(fresh['path'])
        updated=bridge.prepare_competitor(path.name)
        assert updated['ok'],updated
        actual=Ladder.from_dict(updated['ladder'])
        for no in (5,6,39):
            assert actual.item(no).values[0]==expected.item(no).values[0]
            assert actual.item(no).values[1]=='人工改值-'+str(no)
        assert actual.trims[1]['price_guide']==19.98
        assert path.read_bytes()==original
        assert bridge.prepare_competitor(path.name)['ladder']==updated['ladder']
    finally:
        bridge.shutdown()


def test_old_display_list_keeps_defaults_until_user_restores_them(tmp_path):
    from engine import stage_one
    path=tmp_path/'阶梯展示排除清单.json'
    path.write_text(json.dumps(['个人隐藏项']),encoding='utf-8')
    bridge=Bridge(str(tmp_path))
    try:
        migrated=bridge.stage_display_rules()['excluded_rows']
        defaults=list(dict.fromkeys(stage_one.DEFAULT_EXCLUDED_ROWS))
        assert migrated==[*defaults,'个人隐藏项']
        data=json.loads(path.read_text(encoding='utf-8'))
        assert data=={'schema':'carkit.stage-display/v5','excluded_rows':['个人隐藏项'],'included_rows':[]}
        saved=path.read_bytes()
        assert bridge.stage_display_rules()['excluded_rows']==migrated
        assert path.read_bytes()==saved
        assert bridge.save_stage_display_rules([])['excluded_rows']==[]
        assert bridge.stage_display_rules()['excluded_rows']==[]
    finally:
        bridge.shutdown()
    restarted=Bridge(str(tmp_path))
    try:
        assert restarted.stage_display_rules()['excluded_rows']==[]
    finally:
        restarted.shutdown()
