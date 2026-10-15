import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    # Exercise the shipped handlers with a minimal DOM; no copied production logic.
    harness = r"""
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const source=fs.readFileSync('ui/app.js','utf8'), nodes=new Map();
const selectIds=new Set(['#diff-mode','#diff-snapshot','#diff-left-vehicle','#diff-vehicle','#diff-ladder','#diff-valuation','#comparison-plan-list']);
const decode=text=>String(text).replace(/&quot;/g,'"').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
function element(id='') {
  const el={hidden:false,disabled:false,open:false,checked:false,dataset:{},options:[],rows:[],listeners:{},children:[],
    addEventListener(event,handler){(this.listeners[event] ||= []).push(handler);},
    appendChild(child){this.rows.push(child);child.parent=this;},
    querySelector(selector){return this.fields?.[selector] || node(id+' '+selector);},
    querySelectorAll(selector){return selector==='.pair-row'?this.rows:[];},
    remove(){if(this.parent)this.parent.rows=this.parent.rows.filter(row=>row!==this);},
    showModal(){this.open=true;},close(){this.open=false;},
    setCustomValidity(message){this.error=message;},reportValidity(){return !this.error;},
    validity:{badInput:false},classList:{add(){},remove(){},toggle(){}},
    closest(){return null;}};
  let value='',html='';
  Object.defineProperty(el,'value',{get(){return value;},set(next){value=String(next);}});
  Object.defineProperty(el,'innerHTML',{get(){return html;},set(next){
    html=String(next);
    if(selectIds.has(id)) {
      this.options=[...html.matchAll(/<option(?: value="([^"]*)")?[^>]*>(.*?)<\/option>/g)].map(match=>({value:decode(match[1]??match[2])}));
      this.value=this.options[0]?.value || '';
    }
    if(this.className==='pair-row') {
      this.fields=Object.fromEntries(['.pair-self','.pair-comp','.pair-self-floor','.pair-comp-floor','.pair-del'].map(key=>[key,element()]));
      for(const [side,choices] of ['self','comp'].map(side=>[side,html.match(new RegExp('<select class="pair-'+side+'"[^>]*>(.*?)</select>','s'))?.[1] || ''])) {
        this.fields['.pair-'+side].options=[...choices.matchAll(/<option>(.*?)<\/option>/g)].map(match=>({value:decode(match[1])}));
        this.fields['.pair-'+side].value=this.fields['.pair-'+side].options[0]?.value || '';
      }
    }
  }});
  return el;
}
function node(id) {if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);}
const events={};
const document={querySelector:node,querySelectorAll:selector=>selector==='#pairs-editor .pair-row'?node('#pairs-editor').rows:[],
  createElement:()=>element(),addEventListener(event,handler){(events[event] ||= []).push(handler);}};
const window={confirm:()=>true,addEventListener(){},pywebview:{}};
const ST={diff:null,diffRevision:0,pairsRevision:0,competitorRevision:0,selfEditorRevision:0,
  plan:null,ladder:null,ladderPath:'',leftLadder:null,leftLadderPath:'',competitorFile:'',valuation:null,
  stage:{trims:[]}};
const calls=[],toasts=[];
const context={document,window,ST,$:node,$$:document.querySelectorAll,
  ConfigEditor:{unmount(root){delete root.model;},isMounted:root=>!!root.model,validate:()=>true},
  stagePlan:()=>[],configurationOrderKey:no=>no,toast:(...args)=>toasts.push(args),
  api:async(method,...args)=>{calls.push([method,...args]);throw new Error('Unexpected API: '+method);},
  loadChecklist:async()=>({items:[]}),mountConfigurationEditor:(root,model)=>{root.model=model;},
  renderLadderTable:(selector,model)=>{node(selector).model=model || ST.ladder;},
  collectLadderEdits(){},showPage(){}};
vm.createContext(context);
vm.runInContext('let comparisonSelf=null, comparisonSelfPath="";',context);
function load(start,end) {
  const from=source.indexOf(start),to=source.indexOf(end,from);
  assert(from>=0 && to>from,'production source boundaries: '+start);
  vm.runInContext(source.slice(from,to),context);
}
load('function setActionBusy(', 'function configurationChoices(');
vm.runInContext(source.split('\n').find(line=>line.startsWith('const esc =')),context);
load('async function refreshDiffSelects()', '$("#diff-snapshot").addEventListener');
load('async function rebuildPairs()', 'function renderDiff(');
load('function renderDiff(', '$("#btn-export-result").addEventListener');
load('async function selectCompetitor()', '// Keep both editors');
load('function clearComparisonSelf()', "$('#delete-self-file')");
load("$('#diff-snapshot').addEventListener('change',clearComparisonSelf)", "$('#back-to-diff').onclick");
node('#diff-self-editor').hidden=true;node('#diff-competitor-editor').hidden=true;
node('#ppt-review').hidden=true;node('#diff-mode').value='self';
vm.runInContext(fs.readFileSync('ui/comparison-tools.js','utf8'),context);
const tools=window.ComparisonTools;
const result=id=>({ok:true,comparison_id:id,groups:[],cells:[],review:[],evidence:[],missing_valuation:[],md_path:id+'.md'});
function archived(name='Saved',kind='snapshot') {
  return {name,created_at:'2026-10-14T01:00:00Z',session:'frozen-'+name,
    inputs:{left_kind:kind,left:{model:'Left',trims:[{name:'A'},{name:'B'}],cells:[]},
      right:{model:'Right',trims:[{name:'X'},{name:'Y'}],items:[]},
      pairs:[{self_trim:'B',comp_trim:'X',self_floor_price:80321,comp_floor_price:null},
        {self_trim:'A',comp_trim:'Y',self_floor_price:null,comp_floor_price:90987.5}]},
    paths:{left:'session/'+name+'/left.json',right:'session/'+name+'/right.json',valuation:'session/'+name+'/rules.json'},
    result:result('saved-'+name)};
}
function seedCurrent(id='current') {ST.diff=result(id);context.renderDiff(ST.diff);}
function defer(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
const json=value=>JSON.parse(JSON.stringify(value));
"""
    completed = subprocess.run(
        ['node', '-e', harness + '\n(async()=>{\n' + script +
         '\n})().catch(error=>{console.error(error);process.exitCode=1;});'],
        cwd=ROOT, text=True, encoding='utf-8', capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_open_plan_restores_all_manual_pairs_and_missing_floor_prices_without_recalculation():
    run_node(r"""
const plan=archived();node('#comparison-plan-list').value='saved.json';
context.api=async(method,...args)=>{calls.push([method,...args]);assert.strictEqual(method,'open_comparison_plan');return plan;};
await node('#btn-open-plan').onclick();
assert.strictEqual(ST.plan,plan);assert.strictEqual(ST.diff,plan.result);
assert.deepStrictEqual(json(context.collectComparisonPairs()),plan.inputs.pairs);
assert.deepStrictEqual(calls,[['open_comparison_plan','saved.json']]);
assert(node('#diff-status').textContent.includes('尚未重新计算'));
assert(node('#comparison-plan-status').textContent.includes('原方案不会被覆盖'));
assert(node('#comparison-plan-context').textContent.includes('算法使用当前程序版本'));
assert.strictEqual(node('#diff-save-self').textContent,'保存方案工作副本');
for(const id of ['#diff-mode','#diff-snapshot','#diff-left-vehicle','#diff-vehicle','#diff-valuation','#diff-toggle-valuation','#btn-save-valuation','#btn-reset-valuation','#btn-make-template','#btn-load-valuation'])assert(node(id).disabled,id);
for(const id of ['#diff-edit-self','#review-competitor','#btn-add-pair','#btn-run-diff'])assert(!node(id).disabled,id);
""")


def test_plan_recalculation_uses_frozen_session_paths_and_current_manual_pairs():
    run_node(r"""
for(const kind of ['snapshot','ladder']) {
  const plan=archived(kind,kind);node('#comparison-plan-list').value=kind+'.json';
  context.api=async method=>{assert.strictEqual(method,'open_comparison_plan');return plan;};
  await tools.openPlan();
  const row=node('#pairs-editor').rows[0];row.querySelector('.pair-comp-floor').value='76543';
  const expected=json(context.collectComparisonPairs());let args;
  context.api=async(method,...values)=>{assert.strictEqual(method,'run_diff');args=values;return result('new-'+kind);};
  await node('#btn-run-diff').listeners.click[0]();
  assert.deepStrictEqual(json(args),[plan.paths.left,plan.paths.right,expected,plan.paths.valuation,kind==='ladder',plan.session]);
  assert.strictEqual(ST.diff.comparison_id,'new-'+kind);
}
""")


def test_plan_configuration_editors_read_and_save_work_copies_without_rebuilding_pairs():
    run_node(r"""
for(const kind of ['snapshot','ladder']) {
  const plan=archived(kind,kind);node('#comparison-plan-list').value=kind+'.json';
  context.api=async method=>{assert.strictEqual(method,'open_comparison_plan');return plan;};
  await tools.openPlan();const originalRows=[...node('#pairs-editor').rows];const saved=[];
  context.api=async(method,...args)=>{
    if(method==='load_ladder')return {ladder:plan.inputs.left,path:plan.paths.left};
    if(method==='load_snapshot')return {snapshot:plan.inputs.left};
    if(method==='save_ladder_edit' || method==='save_snapshot'){saved.push([method,...args]);return {ok:true};}
    throw new Error('Must not prepare source or rebuild plan pairs: '+method);
  };
  await node('#diff-edit-self').onclick();assert(!node('#diff-self-editor').hidden);
  await node('#diff-save-self').onclick();
  assert.strictEqual(saved[0][1],plan.paths.left);assert.strictEqual(saved[0][2],plan.inputs.left);
  assert.deepStrictEqual(node('#pairs-editor').rows,originalRows);assert.strictEqual(ST.diff,null);
  node('#review-competitor').onclick();assert(!node('#diff-competitor-editor').hidden);
  await node('#diff-save-competitor').onclick();
  assert.strictEqual(saved[1][1],plan.paths.right);assert.strictEqual(saved[1][2],plan.inputs.right);
}
""")


def test_dirty_pair_closes_evidence_and_blocks_saving_the_old_result():
    run_node(r"""
const plan=archived();node('#comparison-plan-list').value='saved.json';
context.api=async()=>plan;await tools.openPlan();
ST.diff.evidence=[{pair:0,no:35,name:'座椅调节',left:{rows:[],value:'主驾10向电调'},right:{rows:[],value:'主驾6向电调'}}];
tools.showEvidence(0,35);assert(node('#comparison-evidence').open);
const row=node('#pairs-editor').rows[0],field=row.querySelector('.pair-self-floor');
field.value='80000';row.listeners.input[0]({target:field});
assert.strictEqual(ST.diff,null);assert(node('#diff-result').hidden);assert(!node('#comparison-evidence').open);
assert(node('#btn-save-plan').disabled);
context.api=async()=>{throw new Error('Dirty results must not save');};
await node('#btn-save-plan').onclick();
""")


def test_save_plan_deduplicates_double_click_and_uses_the_displayed_result_token():
    run_node(r"""
seedCurrent('displayed-token');node('#comparison-plan-name').value='  10月方案  ';
const waiting=defer(), saved=[];
context.api=async(method,...args)=>{
  if(method==='save_comparison_plan'){saved.push(args);return waiting.promise;}
  if(method==='comparison_plans')return {plans:[]};
  throw new Error(method);
};
const first=node('#btn-save-plan').onclick();await node('#btn-save-plan').onclick();
assert.deepStrictEqual(saved,[['10月方案','displayed-token']]);
assert(node('#btn-save-plan').disabled);
waiting.resolve({name:'10月方案',created_at:'2026-10-14T01:00:00Z'});await first;
assert(!node('#btn-save-plan').disabled);
assert(node('#comparison-plan-status').textContent.includes('已另存'));
""")


def test_late_open_plan_response_does_not_replace_newer_comparison_state():
    run_node(r"""
const waiting=defer();node('#comparison-plan-list').value='Old.json';
context.api=async method=>{assert.strictEqual(method,'open_comparison_plan');return waiting.promise;};
const opening=tools.openPlan();context.invalidateDiff();seedCurrent('newer');
waiting.resolve(archived('Old'));await opening;
assert.strictEqual(ST.plan,null);assert.strictEqual(ST.diff.comparison_id,'newer');
assert.strictEqual(node('#btn-open-plan').dataset.busy,undefined);
""")


def test_plan_list_refresh_discards_older_responses():
    run_node(r"""
const old=defer(),latest=defer();let count=0;
context.api=async method=>{assert.strictEqual(method,'comparison_plans');return ++count===1?old.promise:latest.promise;};
const first=tools.refreshPlans(),second=tools.refreshPlans();
latest.resolve({plans:[{file:'Latest.json',name:'Latest',created_at:''}]});await second;
old.resolve({plans:[{file:'Old.json',name:'Old',created_at:''}]});await first;
assert(node('#comparison-plan-list').innerHTML.includes('Latest.json'));
assert(!node('#comparison-plan-list').innerHTML.includes('Old.json'));
""")


def test_late_save_response_does_not_label_a_different_result_as_saved():
    run_node(r"""
seedCurrent('old-token');node('#comparison-plan-name').value='Old';
const waiting=defer();context.api=async method=>method==='save_comparison_plan'?waiting.promise:{plans:[]};
const saving=node('#btn-save-plan').onclick();context.invalidateDiff();seedCurrent('latest-token');
node('#comparison-plan-status').textContent='Latest state';
waiting.resolve({name:'Old',created_at:''});await saving;
assert.strictEqual(ST.diff.comparison_id,'latest-token');
assert.strictEqual(node('#comparison-plan-status').textContent,'Latest state');
""")


def test_in_flight_normal_refresh_cannot_replace_opened_plan_or_auto_repair_it():
    run_node(r"""
for(const phase of ['list_files','vehicle_history']) {
  ST.plan=null;const waiting=defer(),started=defer(),plan=archived(phase);
  context.api=async(method,...args)=>{
    if(method===phase){started.resolve();return waiting.promise;}
    if(method==='list_files')return [];
    if(method==='open_comparison_plan')return plan;
    throw new Error('Late ordinary refresh must stop: '+method);
  };
  const refreshing=context.refreshDiffSelects();await started.promise;
  node('#comparison-plan-list').value='Saved.json';await tools.openPlan();
  waiting.resolve(phase==='list_files'?['ordinary.json']:[{file:'ordinary.json',label:'Ordinary'}]);await refreshing;
  assert.strictEqual(ST.plan,plan);assert.strictEqual(ST.diff,plan.result);
  assert.strictEqual(node('#diff-snapshot').value,'__plan_left__');
  assert.strictEqual(node('#diff-vehicle').value,'__plan_right__');
  assert.deepStrictEqual(json(context.collectComparisonPairs()),plan.inputs.pairs);
}
""")


def test_leaving_plan_unmounts_work_copy_and_restores_normal_rule_controls():
    run_node(r"""
const plan=archived();node('#comparison-plan-list').value='Saved.json';
context.api=async()=>plan;await tools.openPlan();
node('#diff-self-table').model={};node('#diff-ladder-table-wrap').model={};
context.api=async method=>{
  if(method==='list_files' || method==='vehicle_history')return [];
  throw new Error('Leaving a plan must not change source data: '+method);
};
await node('#btn-leave-plan').onclick();
assert.strictEqual(ST.plan,null);assert.strictEqual(ST.diff,null);
assert.strictEqual(ST.ladder,null);assert.strictEqual(ST.ladderPath,'');
assert.strictEqual(node('#pairs-editor').rows.length,0);
assert.strictEqual(node('#diff-self-table').model,undefined);
assert.strictEqual(node('#diff-ladder-table-wrap').model,undefined);
assert(node('#comparison-plan-banner').hidden);
for(const id of ['#diff-mode','#diff-snapshot','#diff-left-vehicle','#diff-vehicle','#diff-valuation','#diff-toggle-valuation','#btn-save-valuation','#btn-reset-valuation','#btn-make-template','#btn-load-valuation'])assert(!node(id).disabled,id);
""")


def test_review_and_evidence_escape_source_html_and_reject_unsafe_source_links():
    run_node(r"""
const unsafe='<img src=x onerror="alert(1)"><script>alert(2)</script>';
seedCurrent();ST.diff.review=[{pair:0,no:35,level:'warning',name:unsafe,side:'left',message:unsafe}];
ST.diff.evidence=[{pair:0,no:35,name:unsafe,rule:unsafe,amount:400,
  left:{model:unsafe,trim:unsafe,source_url:'javascript:alert(1)',captured_at:unsafe,
    rows:[{name:unsafe,cell:{dot:'●',text:unsafe,subs:[{dot:'○',text:unsafe}]}}],
    value:unsafe,source_value:unsafe,calculation:[unsafe],notes:[unsafe]},
  right:{model:'Right',trim:'X',source_url:'https://www.autohome.com.cn/config/series/8140.html',rows:[],value:{text:unsafe}}}];
tools.render(ST.diff);tools.showEvidence(0,35);
for(const id of ['#comparison-review-list','#comparison-evidence-content']) {
  const html=node(id).innerHTML;assert(!html.includes('<img'),id);assert(!html.includes('<script'),id);
  assert(html.includes('&lt;img'),id);assert(html.includes('&quot;alert(1)&quot;'),id);
  assert(!html.includes('href="javascript:'),id);
}
assert(node('#comparison-evidence-content').innerHTML.includes('rel="noopener noreferrer"'));
assert(node('#comparison-evidence').open);
node('#comparison-evidence-close').onclick();assert(!node('#comparison-evidence').open);
""")
