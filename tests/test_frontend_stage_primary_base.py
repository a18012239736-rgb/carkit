from test_frontend_comparison_state import run_node


HARNESS = r"""
let state, component;
context.Vue={ref:value=>({value}),computed:get=>({get value(){return get();}}),
  createApp:config=>{component=config;return {mount(){state=config.setup();},unmount(){}};}};
vm.runInContext(fs.readFileSync('ui/stage-editor.js','utf8'),context);
const host={replaceChildren(){},querySelectorAll(){return[];}};
const plain=value=>JSON.parse(JSON.stringify(value));
const stagePlan=()=>plain(context.window.StageEditor.plan(host));
function mount(prices=[10,11,12,13]) {
  const trims=prices.map((price,i)=>({name:'版型'+i,price_guide:price}));
  context.window.StageEditor.mount(host,trims);
  return trims;
}
function setUsed(i,value) {state.used.value[i]=value;state.toggle(i);}
function assertValidPlan() {
  const seen=new Set();
  for(const row of stagePlan()) {
    assert(!seen.has(row.target),'each output trim occurs once');
    assert(row.base===null || seen.has(row.base),'bases refer only to earlier selected trims');
    assert.notStrictEqual(row.target,row.base,'no self comparison');
    seen.add(row.target);
  }
}
"""


def test_any_price_trim_can_be_primary_without_mutating_source_trims():
    run_node(HARNESS + r"""
const trims=mount();const before=JSON.stringify(trims);
state.chooseBase(3);
assert.strictEqual(Number(state.baseTrim.value),3);
assert.deepStrictEqual(plain(state.order.value),[3,0,1,2]);
assert.deepStrictEqual(stagePlan()[0],{target:3,base:null});
assert.strictEqual(JSON.stringify(trims),before,'raw trim order and prices remain unchanged');
assertValidPlan();
""")


def test_selecting_an_unchecked_primary_checks_it_and_updates_plan_immediately():
    run_node(HARNESS + r"""
mount();setUsed(2,false);
state.chooseBase('2');
assert.strictEqual(state.used.value[2],true);
assert.strictEqual(Number(state.baseTrim.value),2);
assert.deepStrictEqual(stagePlan().map(row=>row.target),[2,0,1,3]);
assert.deepStrictEqual(stagePlan()[0],{target:2,base:null});
assertValidPlan();
""")


def test_changing_primary_preserves_valid_manual_bases_and_repairs_invalid_ones():
    run_node(HARNESS + r"""
mount();state.bases.value[3]=0;
state.chooseBase(2);
assert.strictEqual(state.bases.value[2],'','the chosen primary cannot keep its old parent');
assert.strictEqual(Number(state.bases.value[0]),2,'the former primary gets a valid earlier parent');
assert.strictEqual(Number(state.bases.value[1]),0,'valid inherited relationship remains');
assert.strictEqual(Number(state.bases.value[3]),0,'manual base index zero remains valid');
assert.deepStrictEqual(plain(state.options(0)),[2]);
assert.deepStrictEqual(plain(state.options(3)),[2,0,1]);
assertValidPlan();
""")


def test_unchecking_primary_elects_the_next_selected_trim_and_reconnects_dependents():
    run_node(HARNESS + r"""
mount();setUsed(0,false);state.chooseBase(2);setUsed(2,false);
assert.strictEqual(Number(state.baseTrim.value),1);
assert.deepStrictEqual(stagePlan(),[{target:1,base:null},{target:3,base:1}]);
assert.deepStrictEqual(plain(state.options(3)),[1]);
assertValidPlan();
""")


def test_all_unchecked_can_be_restored_through_primary_selector_without_dom_render():
    run_node(HARNESS + r"""
mount();for(const i of [0,1,2,3])setUsed(i,false);
assert.deepStrictEqual(stagePlan(),[]);
state.chooseBase(3);
assert.deepStrictEqual(stagePlan(),[{target:3,base:null}]);
assert.strictEqual(state.used.value[3],true);
assertValidPlan();
""")


def test_rechecking_a_trim_does_not_replace_the_explicit_primary():
    run_node(HARNESS + r"""
mount();state.chooseBase(3);setUsed(0,false);setUsed(0,true);
assert.strictEqual(Number(state.baseTrim.value),3);
assert.deepStrictEqual(stagePlan().map(row=>row.target),[3,0,1,2]);
assert.strictEqual(Number(state.bases.value[0]),3);
assertValidPlan();
""")


def test_missing_prices_ties_and_source_index_zero_work_with_any_primary():
    run_node(HARNESS + r"""
mount([null,'10.00',0,'待核','10万']);
assert.deepStrictEqual(plain(state.order.value),[2,1,4,0,3]);
state.chooseBase(0);
assert.deepStrictEqual(plain(state.order.value),[0,2,1,4,3]);
assert.deepStrictEqual(stagePlan()[0],{target:0,base:null});
assert.strictEqual(Number(state.bases.value[2]),0,'unknown-price index zero is still a valid parent');
assertValidPlan();
""")


def test_repeated_primary_changes_never_leave_future_or_unselected_base_references():
    run_node(HARNESS + r"""
mount();
for(const primary of [2,1,3,0,2]) {
  state.chooseBase(primary);
  assert.strictEqual(stagePlan()[0].target,primary);
  assertValidPlan();
}
setUsed(1,false);state.chooseBase(3);assertValidPlan();
setUsed(3,false);assertValidPlan();
""")
