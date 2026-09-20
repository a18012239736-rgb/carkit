from engine.models import Cell, RawRow, RawTable, Trim, Snapshot, Ladder
from engine.mapper import n_airbag
from engine.ppt_import import _apply


def test_central_one_curtains_two_and_aliases_not_double_counted():
    raw = RawTable(trims=[Trim(idx=0, short='基础')], rows=[
        RawRow(name='主/副驾驶座安全气囊',cells=[Cell(dot='●',text='主/副')]),
        RawRow(name='前/后排侧气囊',cells=[Cell(dot='●',text='前/后-')]),
        RawRow(name='前/后排头部气囊(气帘)',cells=[Cell(dot='●',text='前/后')]),
        RawRow(name='中央安全气囊',cells=[Cell(dot='●')]),
        RawRow(name='前排中央安全气囊',cells=[Cell(dot='●')]),
    ])
    assert n_airbag(raw,0,{})[0] == 7
    values, evidence, unknown = {5:'4气囊'}, {}, []
    _apply('侧气帘+中央安全气囊',values,evidence,unknown)
    assert values[5]=='7气囊'
    _apply('中央安全气囊',values,evidence,unknown)
    assert values[5]=='7气囊'
    assert 42 not in values
    _apply('7气囊（含中央安全气囊）',values,evidence,unknown)
    assert values[5]=='7气囊'


def test_old_files_merge_once_without_mutating_input():
    data={'cells':[{'no':5,'values':{'基础':'6气囊'}},
                   {'no':42,'values':{'基础':'●'}}]}
    snap=Snapshot.from_dict(data)
    assert snap.cells[0]['values']['基础']=='7气囊'
    assert len(data['cells'])==2
    import json
    assert Snapshot.from_dict(json.loads(snap.to_json())).cells==snap.cells
    ladder=Ladder.from_dict({'items':[
        {'no':5,'name':'气囊数量','values':['6(主副+前侧+前气帘)']},
        {'no':42,'name':'中央安全气囊','values':['●']}]})
    assert ladder.item(5).values==['7气囊']
    assert ladder.item(42) is None
    assert Ladder.from_dict(ladder.to_dict()).item(5).values==['7气囊']
