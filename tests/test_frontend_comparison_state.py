import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    # Run the production handlers with a small DOM/API adapter; no browser dependency.
    harness = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('ui/app.js', 'utf8');
const nodes = new Map();
const selectIds = new Set(['#diff-snapshot','#diff-left-vehicle','#diff-vehicle','#diff-ladder','#diff-valuation']);
function node(id) {
  if (!nodes.has(id)) {
    const el = {value:'', hidden:false, dataset:{}, options:[], rows:[], listeners:{},
      addEventListener(event, handler) {(this.listeners[event] ||= []).push(handler);},
      querySelectorAll() {return this.rows;}};
    let html = '';
    Object.defineProperty(el, 'innerHTML', {get(){return html;},set(value){
      html=value;
      if (selectIds.has(id)) {
        this.options=[...value.matchAll(/<option(?: value="([^"]*)")?[^>]*>(.*?)<\/option>/g)].map(m=>({value:m[1]??m[2]}));
        this.value=this.options[0]?.value || '';
      }
    }});
    nodes.set(id,el);
  }
  return nodes.get(id);
}
function pair(self='Self',comp='Comp') {
  const row={querySelector:selector=>({value:selector==='.pair-self'?self:comp}),
    remove(){node('#pairs-editor').rows=node('#pairs-editor').rows.filter(r=>r!==row);}};
  node('#pairs-editor').rows.push(row);
  return row;
}
const ST={diff:null,diffRevision:0,pairsRevision:0,competitorRevision:0,selfEditorRevision:0,competitorFile:'',ladder:null,ladderPath:'',leftLadder:null,leftLadderPath:''};
const context={ST,$:node,$$:()=>node('#pairs-editor').rows,
  ConfigEditor:{unmount(root){delete root.model;},isMounted:root=>!!root.model,validate:()=>true},
  esc:String,toast(){},window:{confirm:()=>true},
  syncActionButtons(){},setActionBusy(button,busy){if(busy)button.dataset.busy='1';else delete button.dataset.busy;},
  api:async()=>{throw new Error('unexpected API call');},renderDiff(){node('#diff-result').hidden=false;},
  collectValuationEdits:()=>true,renderValuation:async()=>{},
  addPairRow:(self,comp)=>pair(self[0],comp[0])};
vm.createContext(context);
vm.runInContext('let comparisonSelf=null, comparisonSelfPath="", valuationEditorSchema={};',context);
function load(start,end) {
  const from=source.indexOf(start), to=source.indexOf(end,from);
  assert(from>=0 && to>from, 'production source boundaries');
  vm.runInContext(source.slice(from,to),context);
}
load('function invalidateDiff()', 'function configurationChoices(');
load('function clearComparisonSelf()', "$('#delete-self-file')");
load('async function rebuildPairs()', '$("#btn-add-pair")');
function seedResult() {ST.diff={md:'old result'};node('#diff-result').hidden=false;}
"""
    result = subprocess.run(
        ['node', '-e', harness + '\n(async()=>{\n' + script +
         '\n})().catch(error=>{console.error(error);process.exitCode=1;});'],
        cwd=ROOT, text=True, encoding='utf-8', capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_revisiting_comparison_keeps_editor_model_and_manual_pairs():
    run_node(r"""
load('async function refreshDiffSelects()', '$("#diff-snapshot").addEventListener');
load('async function selectCompetitor()', '// Keep both editors');
load('function collectLadderEdits(', 'function cellCls(');
load("$('#diff-save-competitor').onclick", "$('#back-to-diff').onclick");
const model={model:'Comp',trims:[{name:'Comp'}],items:[{no:3,values:['400V']}]};
ST.ladder=model;ST.ladderPath='阶梯/compare.json';ST.competitorFile='comp.json';
node('#diff-snapshot').value='self.json';node('#diff-vehicle').value='comp.json';
node('#diff-ladder').value='compare.json';node('#diff-ladder-table-wrap').model=model;
const originalPair=pair();let saved;
context.api=async(method, ...args)=>{
  if(method==='list_files')return args[0]==='快照'?['self.json']:args[0]==='阶梯'?['compare.json']:[];
  if(method==='vehicle_history')return [{file:'comp.json',label:'Comp'}];
  if(method==='save_ladder_edit'){saved=args[1];return {ok:true};}
  throw new Error('Unexpected reload: '+method);
};
await context.refreshDiffSelects();
assert.strictEqual(ST.ladder,model);
assert.strictEqual(node('#diff-ladder-table-wrap').model,model);
assert.strictEqual(node('#pairs-editor').rows[0],originalPair);
node('#diff-ladder-table-wrap').model.items[0].values[0]='800V';
await node('#diff-save-competitor').onclick();
assert.strictEqual(saved.items[0].values[0],'800V');
""")


def test_clearing_competitor_invalidates_export_and_unmounts_editor():
    run_node(r"""
load('async function selectCompetitor()', '// Keep both editors');
load('$("#btn-export-result").addEventListener', '/* ---------- ⑥ 设置');
seedResult();ST.ladder={};ST.ladderPath='old.json';ST.competitorFile='old.json';
node('#diff-ladder-table-wrap').model=ST.ladder;pair();
node('#pairs-editor').dataset.selfTrims='["Old"]';
await context.selectCompetitor();
assert.strictEqual(ST.diff,null);assert(node('#diff-result').hidden);
assert.strictEqual(ST.ladder,null);assert.strictEqual(ST.ladderPath,'');
assert.strictEqual(node('#diff-ladder-table-wrap').model,undefined);
assert.strictEqual(node('#pairs-editor').rows.length,0);
assert.strictEqual(node('#pairs-editor').dataset.selfTrims,'[]');
await node('#btn-export-result').listeners.click[0](); // No save dialog/API call.
""")


def test_changing_left_competitor_clears_old_editor_and_save_target():
    run_node(r"""
load('$("#diff-snapshot").addEventListener', 'async function rebuildPairs()');
load("$('#diff-save-self').onclick", "$('#review-competitor').onclick");
node('#diff-mode').value='competitor';node('#diff-left-vehicle').value='New';
node('#diff-ladder').value='compare.json';node('#diff-self-table').model={};
ST.leftLadder={};ST.leftLadderPath='old.json';seedResult();
context.api=async(method,...args)=>{
  if(method==='workdir_path')return args.join('/');
  if(method==='prepare_competitor')return {ladder:{trims:[{name:'New'}]}};
  if(method==='load_ladder')return {ladder:{trims:[{name:'Comp'}]}};
  throw new Error('Unexpected old-model save: '+method);
};
await node('#diff-left-vehicle').listeners.change[0]();
assert.strictEqual(node('#diff-self-table').model,undefined);
assert(node('#diff-self-editor').hidden);
assert.strictEqual(ST.leftLadder,null);assert.strictEqual(ST.leftLadderPath,'');
assert.strictEqual(ST.diff,null);
await node('#diff-save-self').onclick(); // Must not save the previous vehicle.
""")


def test_changed_inputs_discard_in_flight_comparison_response():
    run_node(r"""
load('$("#btn-run-diff").addEventListener', 'function renderDiff(');
node('#diff-mode').value='self';node('#diff-snapshot').value='Self-A.json';
node('#diff-ladder').value='Comp.json';pair();
let resolveRun,markRun;const started=new Promise(resolve=>markRun=resolve);
context.api=async(method,...args)=>{
  if(method==='workdir_path')return args.join('/');
  if(method==='run_diff'){markRun();return new Promise(resolve=>resolveRun=resolve);}
  throw new Error(method);
};
const running=node('#btn-run-diff').listeners.click[0]();await started;
node('#diff-snapshot').value='Self-B.json';context.invalidateDiff();
resolveRun({ok:true,self_model:'Self-A',md_path:'old.md',missing_valuation:[]});
await running;assert.strictEqual(ST.diff,null);assert(node('#diff-result').hidden);
""")


def test_self_editor_and_save_path_ignore_late_responses_at_every_await():
    run_node(r"""
load("$('#diff-snapshot').addEventListener('change',clearComparisonSelf)", "$('#diff-edit-self').onclick");
load("$('#diff-edit-self').onclick", "$('#review-competitor').onclick");
context.mountConfigurationEditor=(root,model)=>{root.model=model;};
node('#diff-mode').value='self';
for(const phase of ['path','snapshot','checklist','same-file']) {
  let resolveOld,markOld,hold=true,saved;
  const waiting=new Promise(resolve=>markOld=resolve);
  const pause=()=>{hold=false;markOld();return new Promise(resolve=>resolveOld=resolve);};
  context.api=async(method,...args)=>{
    if(method==='workdir_path') {
      if(phase==='path' && hold)return pause();
      return '快照/'+args[1];
    }
    if(method==='load_snapshot') {
      if(['snapshot','same-file'].includes(phase) && hold)return pause();
      return {snapshot:{model:'Latest'}};
    }
    if(method==='save_snapshot'){saved={path:args[0],model:args[1]};return {ok:true};}
    throw new Error(method);
  };
  context.loadChecklist=async()=>phase==='checklist' && hold?pause():{items:[]};
  node('#diff-snapshot').value=phase==='same-file'?'Same.json':'A.json';
  const older=node('#diff-edit-self').onclick();await waiting;
  node('#diff-snapshot').value=phase==='same-file'?'Same.json':'B.json';
  if(phase!=='same-file')for(const change of node('#diff-snapshot').listeners.change)change();
  await node('#diff-edit-self').onclick();
  resolveOld(phase==='path'?'快照/A.json':phase==='checklist'?{items:[]}:{snapshot:{model:'Old'}});
  await older;
  assert.strictEqual(node('#diff-self-table').model.model,'Latest',phase);
  await node('#diff-save-self').onclick();
  assert.strictEqual(saved.path,'快照/'+(phase==='same-file'?'Same.json':'B.json'),phase);
  assert.strictEqual(saved.model.model,'Latest',phase);
}
""")


def test_latest_comparison_wins_when_requests_finish_out_of_order():
    run_node(r"""
load('$("#btn-run-diff").addEventListener', 'function renderDiff(');
node('#diff-mode').value='self';node('#diff-snapshot').value='Self.json';
node('#diff-ladder').value='Comp.json';pair();
const resolvers=[];let markRun;
context.api=async(method,...args)=>{
  if(method==='workdir_path')return args.join('/');
  if(method==='run_diff'){return new Promise(resolve=>{resolvers.push(resolve);markRun();});}
  throw new Error(method);
};
let started=new Promise(resolve=>markRun=resolve);
const first=node('#btn-run-diff').listeners.click[0]();await started;
started=new Promise(resolve=>markRun=resolve);
const second=node('#btn-run-diff').listeners.click[0]();await started;
const latest={ok:true,self_model:'Latest',md_path:'latest.md',missing_valuation:[]};
resolvers[1](latest);await second;
resolvers[0]({ok:true,self_model:'Old',md_path:'old.md',missing_valuation:[]});await first;
assert.strictEqual(ST.diff,latest);assert(!node('#diff-result').hidden);
""")


def test_all_rule_save_entry_points_invalidate_previous_results():
    run_node(r"""
load('$("#btn-make-template").addEventListener', '$("#btn-load-valuation").addEventListener');
load('$("#btn-save-valuation").addEventListener', 'async function renderValuation()');
context.refreshDiffSelects=async()=>{};
context.api=async()=>({ok:true,valuation:{items:[]},path:'rules.json'});
ST.valuation={items:[]};
for(const id of ['#btn-save-valuation','#btn-reset-valuation','#btn-make-template']) {
  seedResult();await node(id).listeners.click[0]();
  assert.strictEqual(ST.diff,null,id);assert(node('#diff-result').hidden,id);
}
""")


def test_export_dialog_does_not_write_invalidated_results():
    run_node(r"""
load('$("#btn-export-result").addEventListener', '/* ---------- ⑥ 设置');
seedResult();let resolveDialog,markDialog;const opened=new Promise(resolve=>markDialog=resolve);
context.api=async method=>{
  assert.strictEqual(method,'save_file_dialog');
  markDialog();return new Promise(resolve=>resolveDialog=resolve);
};
const exporting=node('#btn-export-result').listeners.click[0]();await opened;
context.invalidateDiff();resolveDialog('result.md');await exporting;
""")


def test_disabling_a_trim_reconnects_bases_and_preserves_index_zero():
    run_node(r"""
let component;
context.Vue={ref:value=>({value}),computed:get=>({get value(){return get();}}),
  createApp:config=>{component=config;return {mount(){},unmount(){}};}};
vm.runInContext(fs.readFileSync('ui/stage-editor.js','utf8'),context);
const root={replaceChildren(){},querySelectorAll(){return[]}};
context.window.StageEditor.mount(root,[10,11,12,13].map((price,i)=>({name:String(i),price_guide:price})));
const setup=component.setup();
setup.used.value[1]=false;setup.toggle(1);
assert.strictEqual(setup.bases.value[2],0);
assert.strictEqual(setup.bases.value[3],2);
setup.bases.value[3]=0;setup.used.value[1]=true;setup.toggle(1);
assert.strictEqual(setup.bases.value[3],0); // Base index 0 is valid, not a missing value.
setup.used.value[0]=false;setup.toggle(0);
assert.strictEqual(setup.bases.value[1],'');
assert.strictEqual(setup.bases.value[2],1);
assert.strictEqual(setup.bases.value[3],2);
""")
