"""Grouped pricing uses the configuration categories without cloning rule items."""
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_valuation_groups_match_configuration_and_edit_original_rules():
    script = r"""
const assert=require('assert'),fs=require('fs'),vm=require('vm');
let component;
const context={window:{},Vue:{ref:value=>({value}),computed:fn=>({get value(){return fn();}}),watch(){},
  createApp:definition=>{component=definition;return {mount(){},unmount(){}};}}};
vm.createContext(context);
for(const file of ['config-editor.js','valuation-editor.js'])
  vm.runInContext(fs.readFileSync('ui/'+file,'utf8'),context);
const root=()=>({classList:{add(){},remove(){}}});
const items=[40,2,36,13,999,1,3].map(no=>({no,rule:no===2?'excluded':'flat',
  val:no,note:'保留备注 '+no,params:{per_unit:5}}));
const model={items},originalOrder=items.map(item=>item.no);
const names=Object.fromEntries(items.map(item=>[item.no,'配置 '+item.no]));
context.window.ValuationEditor.mount(root(),model,{},names);
const valuation=component.setup(),groups=valuation.groups.value;
const plain=value=>JSON.parse(JSON.stringify(value));
assert.deepStrictEqual(plain(groups.map(group=>group.name)),
  ['基本参数','电池/充电','外观/防盗','座椅配置','空调/冰箱','其他配置']);
assert.deepStrictEqual(plain(groups.map(group=>group.rows.map(item=>item.no))),
  [[1],[2,3],[13],[36],[40],[999]]);
assert.deepStrictEqual(plain(groups.map(group=>group.start)),[0,1,3,4,5,6]);
assert.deepStrictEqual(items.map(item=>item.no),originalOrder);
assert.strictEqual(groups[1].rows[0],items[1]);
assert.strictEqual(groups[1].rows[0].rule,'excluded');
assert.strictEqual(groups.at(-1).rows[0],items[4]);
const tailgate=groups[2].rows[0];
valuation.setFixed(tailgate,'1250');
valuation.setParam(tailgate,'per_unit','400');
assert.strictEqual(items[3].val,1250);
assert.strictEqual(items[3].params.per_unit,400);
assert.strictEqual(items[3].note,'保留备注 13');
assert.deepStrictEqual(items.map(item=>item.no),originalOrder);
assert(!items.some(item=>'serial' in item || 'start' in item));
assert.strictEqual((component.template.match(/class="valuation-group-row"/g)||[]).length,1);
assert(component.template.includes('colspan="4"'));
assert(component.template.includes('group.start+index+1'));
context.window.ConfigEditor.mount(root(),{kind:'ladder',names,
  model:{trims:[],items:items.map(item=>({no:item.no,values:[]}))},
  choices:()=>[],parseSeatAdjust:async()=>({ok:true}),cascade:(_,values)=>values,onChange(){}});
const configuration=component.setup();
assert.deepStrictEqual(plain(configuration.groups.value.map(group=>group.name)),
  plain(groups.map(group=>group.name)));
"""
    result = subprocess.run(
        ['node', '-e', script], cwd=ROOT,
        capture_output=True, text=True, encoding='utf-8',
    )
    assert result.returncode == 0, result.stderr
