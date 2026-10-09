import json
from pathlib import Path

from engine import rawschema, seat_adjust
from engine.mapper import map_raw_to_ladder
from engine.rules import Rules
from test_frontend_comparison_state import run_node


EDITOR_HARNESS = r"""
let definition,currentWatches=[];
context.Vue={ref:value=>({value}),computed:get=>({get value(){return get();}}),
  watch(get,callback,options={}) {
    const watcher={get,callback,last:get(),pending:Promise.resolve()};
    currentWatches.push(watcher);
    if(options.immediate)watcher.pending=Promise.resolve(callback(watcher.last));
  },
  createApp:options=>{definition=options;return {mount(){},unmount(){}};}};
vm.runInContext(fs.readFileSync('ui/config-editor.js','utf8'),context);
let changes=0;
function mountModel(model) {
  const root={classList:{add(){},remove(){}}};
  context.window.ConfigEditor.mount(root,{model,kind:'ladder',choices:()=>[],
    parseSeatAdjust:async value=>backend[value],cascade:(_,edited)=>edited,
    onChange:()=>changes++});
  return definition.setup();
}
mountModel({trims:[],items:[]});
const Cell=definition.components.ConfigCell;
function makeCell(value,no=35,parser=async value=>backend[value],onChange=()=>{}) {
  const watches=[];currentWatches=watches;
  const props={value,no,choices:[],parseSeatAdjust:parser},emitted=[];
  const cell=Cell.setup(props,{emit(event,value) {
    assert.strictEqual(event,'change');emitted.push(value);onChange(value);
  }});
  const settle=()=>Promise.all(watches.map(watcher=>watcher.pending));
  return {props,cell,emitted,settle,update(value) {
    props.value=value;
    for(const watcher of watches) {
      const next=watcher.get();
      if(next!==watcher.last) {
        const previous=watcher.last;watcher.last=next;
        watcher.pending=Promise.resolve(watcher.callback(next,previous));
      }
    }
    return settle();
  }};
}
"""


def run_editor(script, values=()):
    backend = {value: {'ok': True, **seat_adjust.parse(value)} for value in values}
    run_node('const values=' + json.dumps(list(values), ensure_ascii=False) +
             ',backend=' + json.dumps(backend, ensure_ascii=False) + ';\n' +
             EDITOR_HARNESS + script)


def q05_mapping():
    raw = rawschema.detect_and_load(str(
        Path(__file__).parent / 'golden' / 'raw-Q05-汽车之家全表-2026-09-11.json'))
    return map_raw_to_ladder(raw, Rules())


def test_q05_seven_trim_seat_controls_match_backend_without_changing_data():
    run_editor(r"""
assert.strictEqual(values.length,7);
const model={trims:values.map((_,i)=>({name:'版型'+i})),items:[{no:35,values:[...values]}]};
const original=JSON.stringify(model),editor=mountModel(model);
for(let i=0;i<values.length;i++) {
  const instance=makeCell(editor.get(model.items[0],i));await instance.settle();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(instance.cell.seats.value)),backend[values[i]].seats);
  assert.strictEqual(instance.cell.seatDetail.value.editable,true);
  assert.deepStrictEqual(instance.cell.seats.value.map(s=>s.count),[6,[4,4,4,6,6,4,6][i]]);
  assert.deepStrictEqual(instance.cell.seats.value.map(s=>s.mode),i===0?['手调','手调']:['电调','电调']);
  assert.deepStrictEqual(instance.emitted,[]);
}
assert.strictEqual(changes,0);assert.strictEqual(JSON.stringify(model),original);
""", q05_mapping()[35]['values'])


def test_manual_default_and_unknown_electric_counts_follow_shared_parser():
    run_editor(r"""
const manual=makeCell(values[0]);await manual.settle();
assert.deepStrictEqual(manual.cell.seats.value.map(s=>s.count),[6,4]);
assert.deepStrictEqual(manual.cell.seats.value.map(s=>s.mode),['手调','手调']);
const electric=makeCell(values[1]);await electric.settle();
assert.deepStrictEqual(electric.cell.seats.value.map(s=>s.count),[null,null]);
assert.deepStrictEqual(electric.cell.seats.value.map(s=>s.mode),['电调','电调']);
assert(electric.cell.seatDetail.value.hint.includes('未推定'));
assert.deepStrictEqual(manual.emitted,[]);assert.deepStrictEqual(electric.emitted,[]);
""", ['主副手调', '主副电调(主含腰撑4向)'])


def test_pending_optional_and_unknown_seats_never_become_manual():
    run_editor(r"""
for(const value of values) {
  const instance=makeCell(value);await instance.settle();
  assert.strictEqual(instance.cell.seatDetail.value.editable,false,value);
  assert(instance.cell.seatDetail.value.hint);
  assert(instance.cell.seats.value.every(s=>s.mode===null && s.count===null),value);
  instance.cell.seatChange(0,'mode','手调');
  assert.deepStrictEqual(instance.emitted,[]);
  assert.strictEqual(instance.cell.value.value,value);
}
""", ['[待定]主副手调', '[待pjy核]主副电调',
        '○主副电调(主含腰撑4向)', '未说明', '●', '主驾6向电调+副驾未知'])


def test_seat_edit_keeps_lumbar_leg_support_suffix_in_saved_model():
    run_editor(r"""
const model={trims:[{name:'A'}],items:[{no:35,values:[values[0]]}]};
const editor=mountModel(model),row=model.items[0];
const instance=makeCell(editor.get(row,0),35,undefined,value=>editor.change(row,0,'',value));
await instance.settle();instance.cell.seatChange(0,'count','12');
const expected='●主驾12向电调+副驾4向手调'+backend[values[0]].suffix;
assert.deepStrictEqual(instance.emitted,[expected]);assert.strictEqual(changes,1);
const saved=JSON.parse(JSON.stringify(model));
assert.strictEqual(saved.items[0].values[0],expected);
assert(saved.items[0].values[0].includes('腰撑4向'));
assert(saved.items[0].values[0].includes('腿托(2向)'));
""", ['●主驾10向电动（主含腰撑4向）+副驾4向手动(副含腿托(2向))'])


def test_old_async_seat_response_cannot_overwrite_newer_value():
    run_editor(r"""
const requests=new Map();
const instance=makeCell(values[0],35,value=>new Promise(resolve=>requests.set(value,resolve)));
const first=instance.settle();
assert(instance.cell.seats.value.every(s=>s.mode===null && s.count===null));
const latest=instance.update(values[1]);
requests.get(values[1])(backend[values[1]]);await latest;
assert.deepStrictEqual(instance.cell.seats.value.map(s=>s.mode),['电调','电调']);
requests.get(values[0])(backend[values[0]]);await first;
assert.deepStrictEqual(instance.cell.seats.value.map(s=>s.mode),['电调','电调']);
assert.deepStrictEqual(instance.cell.seats.value.map(s=>s.count),[null,null]);
assert.strictEqual(instance.cell.value.value,values[1]);assert.deepStrictEqual(instance.emitted,[]);
""", ['主副手调', '主副电调'])


def test_q05_screen_size_events_keep_optional_suffix_without_checking_optional_lcd():
    mapping = q05_mapping()
    instrument, center = mapping[29]['values'][3], mapping[21]['values'][3]
    run_editor(r"""
assert.strictEqual(values[0],'10.17寸仪表(○全液晶选装)');
assert.strictEqual(values[1],'14.6寸中控(○15.6选装)');
assert(Cell.template.includes(':checked="screen.lcd"'));
const input=Cell.template.match(/@input="(screenChange\('size',[^"]+)"/)[1];
const model={trims:[{name:'A'}],items:[{no:29,values:[values[0]]},{no:21,values:[values[1]]}]};
const editor=mountModel(model),original=JSON.stringify(model);
const instrument=makeCell(values[0],29,undefined,value=>editor.change(model.items[0],0,'',value));
const center=makeCell(values[1],21,undefined,value=>editor.change(model.items[1],0,'',value));
assert.strictEqual(instrument.cell.screen.value.lcd,false);
assert.strictEqual(instrument.cell.screen.value.size,'10.17');
assert.strictEqual(center.cell.screen.value.size,'14.6');
assert.strictEqual(instrument.cell.screen.value.state,'present');
assert.strictEqual(center.cell.screen.value.state,'present');
assert.strictEqual(JSON.stringify(model),original);assert.strictEqual(changes,0);
for(const [instance,size] of [[instrument,'12.3'],[center,'15']]) {
  vm.runInNewContext(input,{...instance.cell,$event:{target:{value:size}}});
}
const saved=JSON.parse(JSON.stringify(model));
assert.strictEqual(saved.items[0].values[0],'12.3寸仪表(○全液晶选装)');
assert.strictEqual(saved.items[1].values[0],'15寸中控屏(○15.6选装)');
assert.strictEqual(instrument.cell.screen.value.lcd,false);assert.strictEqual(changes,2);
""", [instrument, center])


def test_unclear_mirror_and_compound_count_fall_back_to_original_text():
    run_editor(r"""
assert(Cell.template.includes('no===20 && simpleMirror'));
assert(Cell.template.includes('[1,37].includes(no) && simpleCount'));
assert(Cell.template.includes('保留原文'));
for(const value of ['○','●','○电调+折叠','方式未说明','电调+加热+未知']) {
  const instance=makeCell(value,20);
  assert.strictEqual(instance.cell.simpleMirror.value,false,value);
  assert.strictEqual(instance.cell.value.value,value);
  assert.strictEqual(instance.cell.options.value[0],value);
  assert.deepStrictEqual(instance.emitted,[]);
}
for(const [no,value] of [[1,'620km/520km'],[1,'[待定]620km'],
  [37,'前排2个/后排1个'],[37,'8扬声器(○12扬声器选装)'],[37,'8+2扬声器']]) {
  const instance=makeCell(value,no);
  assert.strictEqual(instance.cell.simpleCount.value,false,value);
  assert.strictEqual(instance.cell.value.value,value);assert.deepStrictEqual(instance.emitted,[]);
}
for(const value of ['电调+折叠+加热','●电动调节+电动折叠+加热','✕']) {
  assert.strictEqual(makeCell(value,20).cell.simpleMirror.value,true,value);
}
for(const [no,value] of [[1,'620km'],[1,'●620km'],[37,'8'],[37,'12扬声器'],[37,'4喇叭']]) {
  assert.strictEqual(makeCell(value,no).cell.simpleCount.value,true,value);
}
""")
