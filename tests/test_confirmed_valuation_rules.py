from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.mapper import map_raw_to_ladder
from engine.differ import diff
from engine.valuer import default_valuation, value_pair


def _amount(no, value):
    items = [ValuationItem(**item) for item in default_valuation(Rules())['items']]
    return value_pair({no: value}, {}, 10, 10, ValuationTable(items=items))['config_adv']


def test_confirmed_prices_and_front_seat_scope():
    for no, value, expected in [
        (13, '电动后备箱', 800), (21, '15.6中控(12.6)', 500),
        (21, '15.6中控(12.8)', 0), (30, 'P-HUD', 3000),
        (30, 'P-HUD(AR-HUD)', 1000), (36, '前排座椅按摩', 1200),
        (36, '前排座椅通风加热', 1300), (36, '主驾座椅按摩', 600),
        (5, '7气囊(6)', 350), (43, '车载冰箱', 1000),
        (44, '感应雨刮', 100), (45, '前排座椅记忆', 200),
        (45, '主驾座椅记忆', 100),
    ]:
        assert _amount(no, value) == expected, (no, value)


def test_new_rows_are_mapped_and_compared():
    raw = RawTable(trims=[Trim(idx=0, short='基础版')], rows=[
        RawRow(name='HUD抬头数字显示', cells=[Cell(dot='●', text='P-HUD')]),
        RawRow(name='中央安全气囊', cells=[Cell(dot='●')]),
        RawRow(name='车载冰箱', cells=[Cell(dot='●')]),
        RawRow(name='感应雨刷功能', cells=[Cell(dot='●')]),
        RawRow(name='电动座椅记忆', cells=[Cell(dot='●', text='前排')]),
    ])
    mapped = map_raw_to_ladder(raw, Rules())
    assert 42 not in mapped
    assert {no: mapped[no]['values'][0] for no in (5,30,43,44,45)} == {
        5: 1, 30: '●P-HUD', 43: '●', 44: '●', 45: '前排座椅记忆'}
    left = Ladder(trims=[{'name':'本品'}], items=[])
    right = Ladder(trims=[{'name':'竞品'}], items=[LadderItem(no=no,name='配置',values=data['values'])
                                                 for no,data in mapped.items()])
    cells = diff(left,right,[{'self_trim':'本品','comp_trim':'竞品'}],Rules())
    assert {c['no'] for c in cells if c['verdict']=='少'} >= {30,43,44,45}


def test_old_competitor_cache_gains_new_items_without_losing_edits(tmp_path):
    from api.bridge import Bridge
    bridge = Bridge(str(tmp_path))
    raw = RawTable(model='测试', trims=[Trim(idx=0,short='基础版')],
                   rows=[RawRow(name='感应雨刷功能',cells=[Cell(dot='●')])])
    raw.save(str(tmp_path/'raw'/'capture.json'))
    first = bridge.prepare_competitor('capture.json')
    assert first['ok']
    from engine.models import Ladder as SavedLadder
    cached = SavedLadder.load(first['path'])
    cached.items = [it for it in cached.items if it.no <= 41]
    cached.item(13).values[0] = '人工修正'
    cached.save(first['path'])
    refreshed = bridge.prepare_competitor('capture.json')
    assert refreshed['ok']
    result = SavedLadder.load(first['path'])
    assert result.item(13).values[0] == '人工修正'
    assert result.item(44).values[0] == '●'
    assert result.item(45) is not None
