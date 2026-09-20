from engine.seat_functions import SUBS, from_text, normalize
from engine.differ import cmp_seat36
from engine.valuer import _default_rule_amount
from engine.models import Cell, Ladder, RawRow, RawTable, Trim
from engine.mapper import map_raw_to_ladder
from engine.rules import Rules


def test_seat_scope_and_independent_features():
    values = from_text('加热(仅驾驶位)通风(仅驾驶位)按摩(仅驾驶位)', '加热按摩', '副驾头枕音响')
    assert len(SUBS) == 12
    assert all(values['主驾'+f]=='●' for f in ('加热','通风','按摩'))
    assert all(values['副驾'+f]=='✕' for f in ('加热','通风','按摩'))
    assert values['副驾头枕音响']=='●'
    assert values['主驾头枕音响']=='✕'
    assert values['二排加热']==values['二排按摩']=='●'
    assert values['二排通风']=='✕'


def test_seat_comparison_prices_only_changed_positions():
    ours = from_text('主驾加热+副驾通风', '二排按摩')
    theirs = from_text('主驾加热+副驾通风+副驾按摩', '二排按摩')
    verdict, display, backup = cmp_seat36(ours, theirs)
    assert verdict == '少' and '副驾按摩' in display
    assert _default_rule_amount(36, backup, 'less') == 600
    ours['副驾按摩']='●'
    assert cmp_seat36(ours,theirs)[0]=='同'


def test_old_fields_and_competitor_source_are_expanded():
    old = normalize({'前加热通风':'●','前按摩':'✕','头枕音响':'●','二排':'✕'})
    assert old['主驾通风']==old['副驾加热']=='●'
    assert '[待定]' in old['主驾头枕音响']
    raw=RawTable(trims=[Trim(idx=0,short='测试')],rows=[
        RawRow(name='前排座椅功能',cells=[Cell(dot='●',text='按摩(仅驾驶位)')]),
        RawRow(name='第二排座椅功能',cells=[Cell(dot='●',text='通风加热')]),
    ])
    mapped=map_raw_to_ladder(raw,Rules())[36]
    values={row['sub']:row['values'][0] for row in mapped['subs']}
    assert values['主驾按摩']=='●' and values['副驾按摩']=='✕'
    assert values['二排通风']==values['二排加热']=='●'
    old_ladder = Ladder.from_dict({'items':[{'no':36,'name':'座椅功能',
        'values':['加热/通风/按摩(仅主驾)'],
        'subs':[{'sub':'头枕音响','values':['✕']},{'sub':'二排','values':['加热']}]}]})
    migrated={row['sub']:row['values'][0] for row in old_ladder.item(36).subs}
    assert migrated['主驾加热']==migrated['主驾通风']==migrated['主驾按摩']=='●'
    assert migrated['副驾加热']=='✕' and migrated['二排加热']=='●'
