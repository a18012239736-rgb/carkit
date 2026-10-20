from test_comparison_tools_frontend import run_node


def test_warning_summary_stays_visible_without_overriding_manual_expansion():
    run_node(r"""
const review=node('#comparison-review');
const comparison=result('review');
comparison.review=[
  {pair:0,no:35,level:'warning',name:'座椅调节',side:'left',message:'方向待确认'},
  {pair:0,no:21,level:'info',name:'中控屏',side:'right',message:'人工配置'},
];
tools.render(comparison);
assert(!review.hidden);assert(!review.open);
assert.strictEqual(review.dataset.hasWarnings,'true');
assert(node('#comparison-review-summary').textContent.includes('有1项待核'));
assert(node('#comparison-review-list').innerHTML.includes('方向待确认'));
review.open=true;
node('#comparison-review-info').checked=true;
ST.diff=comparison;node('#comparison-review-info').onchange();
assert(review.open);
assert(node('#comparison-review-list').innerHTML.includes('人工配置'));
review.open=false;tools.render(comparison);assert(!review.open);
review.open=true;tools.render(result('new-review'));assert(review.open);
assert.strictEqual(review.dataset.hasWarnings,'false');
assert(node('#comparison-review-summary').textContent.includes('未发现已知待核项'));
assert(node('#comparison-review-list').innerHTML.includes('不代表配置已全部人工核实'));
""")


def test_result_save_controls_keep_original_saving_gates_and_show_local_feedback():
    run_node(r"""
const controls=node('#comparison-save-controls'),status=node('#comparison-save-status');
assert(controls.hidden);assert(node('#btn-save-plan').disabled);
seedCurrent('current');assert(!controls.hidden);assert(!node('#btn-save-plan').disabled);
node('#comparison-plan-name').value='工作台方案';
context.api=async method=>method==='save_comparison_plan'
  ?{name:'工作台方案',created_at:'2026-10-20T01:00:00Z'}:{plans:[]};
await node('#btn-save-plan').onclick();
assert(status.textContent.includes('已另存方案：工作台方案'));
assert.strictEqual(status.textContent,node('#comparison-plan-status').textContent);
context.invalidateDiff();assert(controls.hidden);assert(node('#btn-save-plan').disabled);
assert.strictEqual(status.textContent,'');
""")


def test_late_save_feedback_does_not_label_the_new_result_as_saved():
    run_node(r"""
seedCurrent('old');const waiting=defer();
context.api=async method=>method==='save_comparison_plan'?waiting.promise:{plans:[]};
const saving=node('#btn-save-plan').onclick();
context.invalidateDiff();seedCurrent('new');
node('#comparison-save-status').textContent='当前结果尚未保存';
waiting.resolve({name:'旧结果',created_at:''});await saving;
assert.strictEqual(node('#comparison-save-status').textContent,'当前结果尚未保存');
assert.strictEqual(ST.diff.comparison_id,'new');
""")


def test_opening_plan_confirms_hidden_mounted_drafts_before_clearing_them():
    run_node(r"""
for(const rootId of ['#diff-self-table','#diff-ladder-table-wrap']) {
  context.hideComparisonEditors();ST.plan=null;
  seedCurrent('current');
  const current=ST.diff,draft={model:'Unsaved',value:'800V'};
  node(rootId).model=draft;
  node('#diff-self-editor').hidden=true;
  node('#diff-competitor-editor').hidden=true;
  node('#comparison-plan-list').value='Saved.json';
  let confirmations=0,opens=0;
  window.confirm=()=>{confirmations++;return false;};
  const plan=archived();
  context.api=async method=>{
    assert.strictEqual(method,'open_comparison_plan');opens++;return plan;
  };
  await tools.openPlan();
  assert.strictEqual(confirmations,1,rootId+' hidden draft needs confirmation');
  assert.strictEqual(opens,0,rootId+' cancellation must not open a plan');
  assert.strictEqual(node(rootId).model,draft,rootId+' cancellation retains draft');
  assert.strictEqual(ST.diff,current,rootId+' cancellation retains result');
  assert.strictEqual(ST.plan,null);
  window.confirm=()=>{confirmations++;return true;};
  await tools.openPlan();
  assert.strictEqual(confirmations,2);
  assert.strictEqual(opens,1);
  assert.strictEqual(node(rootId).model,undefined,rootId+' confirmation permits clearing');
  assert.strictEqual(ST.plan,plan);
  assert.strictEqual(ST.diff,plan.result);
}
""")
