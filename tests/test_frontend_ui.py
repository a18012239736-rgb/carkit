from test_frontend_comparison_state import run_node


BUTTON_HELPERS = r"""
const stageSelection=[];
context.stagePlan=()=>stageSelection;
context.$=selector=>{
  const el=node(selector);
  el.setAttribute=(name,value)=>el[name]=value;
  el.removeAttribute=name=>delete el[name];
  return el;
};
context.document={getElementById:id=>context.$('#'+id)};
ST.stage={trims:[],seriesId:'',model:''};ST.snapshot=null;ST.valuation=null;
load('function setActionBusy(', 'function invalidateDiff(');
"""


def test_action_buttons_follow_selected_trims_models_pairs_and_valid_results():
    run_node(BUTTON_HELPERS + r"""
context.syncActionButtons();
for(const id of ['btn-stage-preview','btn-stage-export','btn-stage-excel','btn-run-diff',
  'btn-export-result','btn-result-excel','diff-edit-self','review-competitor']) {
  assert.strictEqual(node('#'+id).disabled,true,id+' without inputs');
}
stageSelection.push({target:0,base:null});
ST.stage.trims=[{name:'基础'}];
node('#diff-mode').value='self';node('#diff-snapshot').value='self.json';
node('#diff-ladder').value='comp.json';ST.ladder={trims:[{name:'Comp'}]};
ST.ladderPath='阶梯/comp.json';pair();
context.syncActionButtons();
for(const id of ['btn-stage-preview','btn-stage-export','btn-stage-excel','btn-run-diff',
  'diff-edit-self','review-competitor']) {
  assert.strictEqual(node('#'+id).disabled,false,id+' with valid inputs');
}
assert.strictEqual(node('#btn-result-excel').disabled,true);
ST.diff={ok:true,md:'ready'};context.syncActionButtons();
assert.strictEqual(node('#btn-export-result').disabled,false);
assert.strictEqual(node('#btn-result-excel').disabled,false);
node('#pairs-editor').rows=[];context.invalidateDiff();
assert.strictEqual(node('#btn-run-diff').disabled,true);
assert.strictEqual(node('#btn-export-result').disabled,true);
assert.strictEqual(node('#btn-result-excel').disabled,true);
node('#diff-mode').value='competitor';node('#diff-left-vehicle').value='';
context.syncActionButtons();
assert.strictEqual(node('#diff-edit-self').disabled,true);
node('#diff-left-vehicle').value='left.json';pair();context.syncActionButtons();
assert.strictEqual(node('#btn-run-diff').disabled,false);
stageSelection.length=0;context.syncActionButtons();
assert.strictEqual(node('#btn-stage-export').disabled,true);
assert.strictEqual(node('#btn-stage-excel').disabled,true);
""")


def test_finishing_busy_export_does_not_reenable_invalidated_result():
    run_node(BUTTON_HELPERS + r"""
ST.diff={ok:true,md:'ready'};context.syncActionButtons();
const button=node('#btn-result-excel');
context.setActionBusy(button,true);
assert.strictEqual(button.disabled,true);
assert.strictEqual(button.dataset.busy,'1');
context.invalidateDiff();
context.setActionBusy(button,false);
assert.notStrictEqual(button.dataset.busy,'1');
assert.strictEqual(button.disabled,true);
ST.diff={ok:false};context.syncActionButtons();
assert.strictEqual(button.disabled,true);
ST.diff={ok:true};context.syncActionButtons();
assert.strictEqual(button.disabled,false);
""")


def test_excel_handler_finally_keeps_export_disabled_after_result_invalidation():
    run_node(BUTTON_HELPERS + r"""
for(const id of ['#btn-stage-export','#btn-export-result']) {
  node(id).before=()=>{};node(id).classList={remove(){},add(){}};
}
context.document.createElement=()=>{
  const el={dataset:{},append(){}};
  Object.defineProperty(el,'id',{set(id){nodes.set('#'+id,el);}});
  return el;
};
load("for(const [anchor,kind] of [['btn-stage-export'", "$('#page-diff .notice')");
const result={ok:true,md:'ready'};ST.diff=result;context.syncActionButtons();
let resolveExport,calls=0;
context.api=async(method,kind,payload)=>{
  assert.strictEqual(method,'export_excel');assert.strictEqual(kind,'diff');
  assert.strictEqual(payload,result);calls++;
  return new Promise(resolve=>resolveExport=resolve);
};
const button=node('#btn-result-excel'),exporting=button.onclick();
assert.strictEqual(button.dataset.busy,'1');
await button.onclick();assert.strictEqual(calls,1);
context.invalidateDiff();resolveExport({ok:true,cancelled:true});await exporting;
assert.notStrictEqual(button.dataset.busy,'1');assert.strictEqual(button.disabled,true);
await button.onclick();assert.strictEqual(calls,1);
""")


def test_running_comparison_ignores_double_click_and_restores_current_input_state():
    run_node(BUTTON_HELPERS + r"""
load('$("#btn-run-diff").addEventListener', 'function renderDiff(');
node('#diff-mode').value='self';node('#diff-snapshot').value='self.json';
node('#diff-ladder').value='comp.json';ST.ladder={trims:[{name:'Comp'}]};pair();
let count=0,resolveRun,markRun;
const started=new Promise(resolve=>markRun=resolve);
context.api=async(method,...args)=>{
  if(method==='workdir_path')return args.join('/');
  assert.strictEqual(method,'run_diff');count++;markRun();
  return new Promise(resolve=>resolveRun=resolve);
};
const button=node('#btn-run-diff');context.syncActionButtons();
const running=button.listeners.click[0]();
const duplicate=button.listeners.click[0]();
await started;
for(let i=0;i<5;i++)await Promise.resolve();
assert.strictEqual(count,1);
await duplicate;
assert.strictEqual(button.disabled,true);
node('#diff-snapshot').value='';context.invalidateDiff();
resolveRun({ok:true,missing_valuation:[],md_path:'stale.md'});
await running;
assert.notStrictEqual(button.dataset.busy,'1');
assert.strictEqual(button.disabled,true);
assert.strictEqual(node('#btn-result-excel').disabled,true);
assert.strictEqual(ST.diff,null);
""")


def test_results_show_plain_amounts_and_collapsed_calculation_details():
    run_node(BUTTON_HELPERS + r"""
load('function renderDiff(', '$("#btn-export-result").addEventListener');
assert.strictEqual(vm.runInContext('fmtP(10.9)',context),'指导价 10.90 万元');
assert.strictEqual(vm.runInContext('fmtMoney(null)',context),'待计算');
for(const [value,display] of [[1000.5,'1000.5'],[9663,'9663'],[-1000,'-1000']]) {
  assert.strictEqual(vm.runInContext(`fmtMoney(${value})`,context),display);
}
const result={ok:true,self_model:'本品',comp_model:'竞品',cells:[],groups:[{
  pair:{self_trim:'A',comp_trim:'B'},self_price:10.9,comp_price:11,
  more:['LED大灯'],less:['热泵'],valuation:{config_adv:1000.5,flat_adv:9663,overall:-1000,
    total_more:9663,total_less:1000,detail:[{side:'多',display:'LED大灯',rule:'固定',amount:1000.5},
      {side:'多',display:'辅助驾驶',rule:'固定',amount:9663},
      {side:'少',display:'热泵',rule:'固定',amount:-1000}]},
}]};
ST.diff=result;context.renderDiff(result);
const html=node('#backup-table').innerHTML;
const main=html.slice(0,html.indexOf('</table>'));
const details=html.slice(html.indexOf('<details>'));
assert(html.includes('10.90 万元'));
assert(/<th[^>]*>配置优势[^<]*元/.test(html));
assert(/<th[^>]*>拉平指导价优势[^<]*元/.test(html));
for(const display of ['1000.5','9663','-1000']) {
  assert(main.includes(`<td>${display}</td>`),'main table '+display);
  assert(details.includes(`<td>${display}</td>`),'calculation details '+display);
}
assert(!/\+\d|\d,\d/.test(html));
assert(details.includes('×10000'));
assert(/<details(?:\s[^>]*)?>/.test(html));
assert(!/<details\b[^>]*\bopen(?:\s|=|>)/.test(html));
assert.strictEqual(node('#diff-result').hidden,false);
""")


def test_valuation_editor_has_four_columns_and_preserves_notes_when_editing():
    run_node(r"""
let component;
context.Vue={ref:value=>({value}),computed:get=>({get value(){return get();}}),
  createApp:options=>{component=options;return {mount(){},unmount(){}};}};
vm.runInContext(fs.readFileSync('ui/valuation-editor.js','utf8'),context);
const item={no:40,rule:'flat',val:500,note:'原有备注',params:{per_unit:1}};
const model={items:[item]},root={classList:{add(){}}};
context.window.ValuationEditor.mount(root,model,{}, {40:'热泵'});
const header=component.template.match(/<thead>[\s\S]*?<\/thead>/)[0];
assert.strictEqual((header.match(/<th(?:\s[^>]*)?>/g)||[]).length,4);
assert(!header.includes('备注'));
assert(!/valuation-note|item\.note/.test(component.template));
const editor=component.setup();
editor.setFixed(item,'9663');editor.setParam(item,'per_unit','1000.5');
assert.strictEqual(model.items[0].val,9663);
assert.strictEqual(model.items[0].params.per_unit,1000.5);
assert.strictEqual(model.items[0].note,'原有备注');
""")


def test_rule_export_saves_the_edited_rules_before_creating_excel():
    run_node(r"""
load('$("#btn-make-template").addEventListener', '$("#btn-load-valuation").addEventListener');
ST.valuation={items:[{no:40,val:500}]};seedResult();
const saved={items:[{no:40,val:800}]}, calls=[];
context.api=async(method,...args)=>{
  calls.push(method);
  if(method==='save_current_valuation') {
    assert.strictEqual(args[0],ST.valuation);
    return {ok:true,valuation:saved};
  }
  assert.strictEqual(method,'make_valuation_template');
  assert.strictEqual(ST.valuation,saved);
  return {ok:true,path:'rules.xlsx'};
};
await node('#btn-make-template').listeners.click[0]();
assert.deepStrictEqual(calls,['save_current_valuation','make_valuation_template']);
assert.strictEqual(ST.diff,null);
""")


def test_rule_export_does_not_create_excel_after_a_failed_save():
    run_node(r"""
load('$("#btn-make-template").addEventListener', '$("#btn-load-valuation").addEventListener');
ST.valuation={items:[]};seedResult();
context.api=async method=>{
  assert.strictEqual(method,'save_current_valuation');
  return {ok:false,error:'保存失败'};
};
await node('#btn-make-template').listeners.click[0]();
assert.strictEqual(ST.diff.md,'old result');
""")
