from test_frontend_comparison_state import run_node


EDITORS = r"""
load("$('#diff-edit-self').onclick", "$('#back-to-diff').onclick");
context.loadChecklist=async()=>({items:[]});
context.mountConfigurationEditor=(root,model)=>{root.model=model;};
context.renderLadderTable=(selector,model)=>{node(selector).model=model || ST.ladder;};
context.collectLadderEdits=()=>{};
node('#diff-self-editor').hidden=true;
node('#diff-competitor-editor').hidden=true;
node('#diff-mode').value='self';
node('#diff-snapshot').value='Self.json';
node('#diff-left-vehicle').value='Left.json';
node('#diff-ladder').value='Right.json';
ST.ladder={model:'Right',trims:[{name:'Right'}],items:[{no:3,values:['400V']}]};
ST.ladderPath='阶梯/Right.json';
"""


def test_switching_editor_sides_reuses_both_models_without_reloading_left_drafts():
    run_node(EDITORS + r"""
for(const kind of ['snapshot','ladder']) {
  context.clearComparisonSelf();
  node('#diff-competitor-editor').hidden=true;
  node('#diff-mode').value=kind==='snapshot'?'self':'competitor';
  const left={model:'Left',trims:[{name:'Left'}],items:[{no:3,values:['400V']}],cells:[]};
  const calls=[];
  context.api=async(method,...args)=>{
    calls.push([method,...args]);
    if(method==='workdir_path')return '快照/Self.json';
    if(method==='load_snapshot')return {snapshot:left};
    if(method==='prepare_competitor')return {ladder:left,path:'阶梯/Left.json'};
    throw new Error('Unexpected API: '+method);
  };
  seedResult();
  await node('#diff-edit-self').onclick();
  assert.strictEqual(ST.diff.md,'old result','opening an editor is not an edit');
  const leftRoot=node('#diff-self-table');
  leftRoot.model.items[0].values[0]='800V';
  const loaded=calls.length;
  node('#review-competitor').onclick();
  assert(node('#diff-self-editor').hidden);
  assert(!node('#diff-competitor-editor').hidden);
  const rightRoot=node('#diff-ladder-table-wrap'),rightModel=rightRoot.model;
  rightModel.items[0].values[0]='800V';
  await node('#diff-edit-self').onclick();
  assert(!node('#diff-self-editor').hidden);
  assert(node('#diff-competitor-editor').hidden);
  assert.strictEqual(leftRoot.model,left);
  assert.strictEqual(leftRoot.model.items[0].values[0],'800V');
  assert.strictEqual(calls.length,loaded,'same source must not be fetched again');
  node('#review-competitor').onclick();
  assert.strictEqual(rightRoot.model,rightModel);
  assert.strictEqual(rightRoot.model.items[0].values[0],'800V');
  assert.strictEqual(calls.length,loaded);
}
""")


def test_opening_right_editor_cancels_late_left_load_at_every_await():
    run_node(EDITORS + r"""
for(const phase of ['path','snapshot','checklist']) {
  context.clearComparisonSelf();
  node('#diff-competitor-editor').hidden=true;
  let resolveOld,markStarted;
  const started=new Promise(resolve=>markStarted=resolve);
  const pause=()=>{markStarted();return new Promise(resolve=>resolveOld=resolve);};
  context.api=async method=>{
    if(method==='workdir_path')return phase==='path'?pause():'快照/Self.json';
    if(method==='load_snapshot')return phase==='snapshot'?pause():{snapshot:{model:'Late',cells:[]}};
    throw new Error('Unexpected API: '+method);
  };
  context.loadChecklist=async()=>phase==='checklist'?pause():{items:[]};
  const loading=node('#diff-edit-self').onclick();
  await started;
  node('#review-competitor').onclick();
  assert(!node('#diff-competitor-editor').hidden,phase);
  resolveOld(phase==='path'?'快照/Self.json':phase==='snapshot'?{snapshot:{model:'Late',cells:[]}}:{items:[]});
  await loading;
  assert(node('#diff-self-editor').hidden,phase+' must not reopen left');
  assert(!node('#diff-competitor-editor').hidden,phase+' keeps right active');
  assert.strictEqual(node('#diff-self-table').model,undefined,phase+' discards stale model');
  assert.strictEqual(node('#diff-self-editor').dataset.source,undefined,phase);
}
""")


def test_return_buttons_hide_editors_without_discarding_unsaved_models():
    run_node(EDITORS + r"""
let reads=0;
const left={model:'Self',trims:[{name:'Self'}],cells:[],draft:'original'};
context.api=async method=>{
  reads++;
  if(method==='workdir_path')return '快照/Self.json';
  if(method==='load_snapshot')return {snapshot:left};
  throw new Error('Unexpected API: '+method);
};
await node('#diff-edit-self').onclick();
left.draft='unsaved';
const loaded=reads;
let unmounts=0;
context.ConfigEditor.unmount=()=>{unmounts++;};
node('#diff-back-self').onclick();
assert(node('#diff-self-editor').hidden);
assert(node('#diff-competitor-editor').hidden);
assert.strictEqual(node('#diff-self-table').model,left);
await node('#diff-edit-self').onclick();
assert(!node('#diff-self-editor').hidden);
assert.strictEqual(node('#diff-self-table').model.draft,'unsaved');
assert.strictEqual(reads,loaded);
node('#review-competitor').onclick();
const right=node('#diff-ladder-table-wrap').model;
right.draft='right unsaved';
node('#diff-back-competitor').onclick();
assert(node('#diff-self-editor').hidden);
assert(node('#diff-competitor-editor').hidden);
node('#review-competitor').onclick();
assert.strictEqual(node('#diff-ladder-table-wrap').model,right);
assert.strictEqual(right.draft,'right unsaved');
assert.strictEqual(unmounts,0,'return and reopen only hide/show mounted editors');
""")


def test_editors_close_only_after_valid_successful_saves():
    run_node(EDITORS + r"""
for(const kind of ['snapshot','left-ladder','right-ladder']) {
  context.clearComparisonSelf();
  node('#diff-competitor-editor').hidden=true;
  node('#diff-mode').value=kind==='left-ladder'?'competitor':'self';
  ST.plan={session:'plan',paths:{left:'session/left.json'}};
  const left={model:'Left',trims:[{name:'Left'}],items:[],cells:[]};
  context.api=async method=>{
    if(method==='load_snapshot')return {snapshot:left};
    if(method==='load_ladder')return {ladder:left,path:'session/left.json'};
    throw new Error('Unexpected load: '+method);
  };
  if(kind==='right-ladder')node('#review-competitor').onclick();
  else await node('#diff-edit-self').onclick();
  const panel=node(kind==='right-ladder'?'#diff-competitor-editor':'#diff-self-editor');
  const button=node(kind==='right-ladder'?'#diff-save-competitor':'#diff-save-self');
  assert(!panel.hidden,kind);
  let saves=0;
  context.api=async()=>{saves++;return {ok:true};};
  context.ConfigEditor.validate=()=>false;
  await button.onclick();
  assert(!panel.hidden,kind+' validation failure stays open');
  assert.strictEqual(saves,0,kind+' invalid draft is not written');
  context.ConfigEditor.validate=()=>true;
  context.api=async()=>{throw new Error('Save unavailable');};
  await assert.rejects(button.onclick(),/Save unavailable/);
  assert(!panel.hidden,kind+' rejected save stays open');
  context.api=async()=>({ok:false,error:'Save refused'});
  await button.onclick();
  assert(!panel.hidden,kind+' unsuccessful save stays open');
  seedResult();
  context.api=async()=>({ok:true});
  await button.onclick();
  assert(panel.hidden,kind+' successful save returns to pairing');
  assert.strictEqual(ST.diff,null,kind+' save invalidates old result');
}
""")


def test_late_right_save_does_not_close_a_different_vehicle_editor():
    run_node(EDITORS + r"""
node('#review-competitor').onclick();
const previous=ST.ladder;
let resolveSave,markStarted;
const started=new Promise(resolve=>markStarted=resolve);
context.api=async(method,path,model)=>{
  assert.strictEqual(method,'save_ladder_edit');
  assert.strictEqual(path,'阶梯/Right.json');
  assert.strictEqual(model,previous);
  markStarted();return new Promise(resolve=>resolveSave=resolve);
};
const saving=node('#diff-save-competitor').onclick();
await started;
const next={model:'New vehicle',trims:[{name:'New'}],items:[]};
ST.ladder=next;ST.ladderPath='阶梯/New.json';
node('#diff-ladder-table-wrap').model=next;
node('#diff-competitor-editor').hidden=false;
resolveSave({ok:true});await saving;
assert.strictEqual(ST.ladder,next);
assert.strictEqual(node('#diff-ladder-table-wrap').model,next);
assert(!node('#diff-competitor-editor').hidden,'late old save keeps new editor open');
""")
