import json
import subprocess
from pathlib import Path

from engine.ppt_import import make_snapshot
from engine.snapshot import BASE_CONFIG, prepare_snapshot
from engine.models import Snapshot


def _draft():
    return {'model':'测试', 'columns':[
        {'name':'基础','base':None,'text':''},
        {'name':'舒适','base':'基础','text':''},
        {'name':'豪华','base':'舒适','text':''},
        {'name':'独立分支','base':None,'text':''},
        {'name':'明确400V','base':'基础','text':'400V平台'},
    ]}


def test_zero_price_defaults_and_explicit_values():
    draft=_draft()
    draft['columns'][1]['text']='LED大灯\n真皮座椅'
    snap=make_snapshot(draft)
    cells={c['no']:c for c in snap.cells}
    assert all(cells[no]['values']['基础']==value for no,value in BASE_CONFIG.items())
    assert cells[34]['values']['舒适']=='真皮'
    assert cells[17]['values']['舒适']=='LED大灯'
    assert cells[3]['values']['基础']=='✕'  # Not every absent item is a zero-price tier.
    assert 42 not in cells
    assert '舒适' not in cells[17]['links']
    assert cells[17]['links']['豪华']=='舒适'


def test_linkage_through_branches_manual_overrides_and_reload():
    snap=make_snapshot(_draft())
    # Run the exact function used by both editors, not a Python reimplementation.
    script="""
const fs=require('fs'), vm=require('vm');
const source=fs.readFileSync('ui/app.js','utf8');
const context={};vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function updateSnapshotValue('),source.indexOf('function bindSnapshotEditor(')),context);
const snap=JSON.parse(fs.readFileSync(0,'utf8'));
context.updateSnapshotValue(snap,3,'基础','800V');
const first=JSON.parse(JSON.stringify(snap));
context.updateSnapshotValue(snap,3,'舒适','400V');
context.updateSnapshotValue(snap,3,'基础','900V');
console.log(JSON.stringify({first,final:snap}));
"""
    result=json.loads(subprocess.run(['node','-e',script],input=snap.to_json(),text=True,encoding='utf-8',capture_output=True,
                                    cwd=Path(__file__).resolve().parents[1],check=True).stdout)
    first=next(c for c in result['first']['cells'] if c['no']==3)
    assert first['values']=={'基础':'800V','舒适':'800V','豪华':'800V','独立分支':'✕','明确400V':'400V'}
    saved=prepare_snapshot(Snapshot.from_dict(result['final']))
    final=next(c for c in saved.cells if c['no']==3)
    assert final['values']['基础']=='900V'
    assert final['values']['舒适']==final['values']['豪华']=='400V'
    assert '舒适' not in final['links']


def test_competitor_ladder_edit_cascades_only_through_inherited_values():
    script="""
const fs=require('fs'), vm=require('vm');
const source=fs.readFileSync('ui/app.js','utf8'), context={};vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function cascadeLadderValues('),source.indexOf('function mirrorParts(')),context);
console.log(JSON.stringify(context.cascadeLadderValues(['A','A','A','B'],['C','A','D','B'])));
"""
    result=json.loads(subprocess.run(['node','-e',script],text=True,encoding='utf-8',capture_output=True,
                                    cwd=Path(__file__).resolve().parents[1],check=True).stdout)
    assert result == ['C','C','D','B']


def test_seat_summary_has_no_redundant_prefix_or_price():
    from engine.differ import cmp_seat36
    verdict, _, backup = cmp_seat36({'主驾通风':'●','副驾通风':'●'}, {})
    assert verdict == '多'
    assert backup == '前排座椅通风'


def test_zero_tier_differences_are_priced_both_ways():
    from engine.differ import diff
    from engine.models import Ladder, LadderItem, ValuationItem, ValuationTable
    from engine.rules import Rules
    from engine.valuer import default_valuation, value_pair
    rules=Rules()
    valuation=ValuationTable(items=[ValuationItem(**i) for i in default_valuation(rules)['items']])
    for no,base,upgrade,price in [(17,'卤素大灯','LED大灯',1000),(25,'塑料','真皮',500),(34,'织物','仿皮',1500)]:
        for left,right,sign in [(base,upgrade,-1),(upgrade,base,1)]:
            a=Ladder(trims=[{'name':'A'}],items=[LadderItem(no=no,name='测试',values=[left])])
            b=Ladder(trims=[{'name':'B'}],items=[LadderItem(no=no,name='测试',values=[right])])
            c=next(c for c in diff(a,b,[{'self_trim':'A','comp_trim':'B'}],rules) if c['no']==no)
            result=value_pair({no:c['backup_more']} if sign==1 else {},{no:c['backup_less']} if sign==-1 else {},10,10,valuation)
            assert result['config_adv']==sign*price
