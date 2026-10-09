from test_frontend_comparison_state import run_node


PAIR_ROWS = r"""
context.document={createElement(){
  const fields={},row={listeners:{},
    addEventListener(event,handler){(this.listeners[event] ||= []).push(handler);},
    querySelector:selector=>fields[selector],
    remove(){node('#pairs-editor').rows=node('#pairs-editor').rows.filter(r=>r!==row);}};
  let html='';
  Object.defineProperty(row,'innerHTML',{get(){return html;},set(value){
    html=value;
    for(const name of ['pair-self','pair-comp','pair-self-floor','pair-comp-floor','pair-del']) {
      const match=value.match(new RegExp('<select class="'+name+'"[^>]*>([\\s\\S]*?)</select>'));
      fields['.'+name]={value:match?.[1].match(/<option>(.*?)<\/option>/)?.[1]||'',
        validity:{badInput:false},listeners:{},
        addEventListener(event,handler){(this.listeners[event] ||= []).push(handler);},
        setCustomValidity(message){this.error=message;},
        reportValidity(){this.reported=true;return !this.error;}};
    }
  }});
  return row;
}};
node('#pairs-editor').appendChild=row=>node('#pairs-editor').rows.push(row);
load('function addPairRow(', 'function collectComparisonPairs(');
node('#diff-mode').value='self';node('#diff-snapshot').value='Self.json';
node('#diff-left-vehicle').value='Left.json';node('#diff-ladder').value='Comp.json';
function add(){context.addPairRow(['Self','Self2'],['Comp','Comp2']);return node('#pairs-editor').rows.at(-1);}
function emit(row,event,selector){for(const handler of row.listeners[event]||[])handler({target:row.querySelector(selector)});}
"""


def test_each_pair_sends_its_own_numeric_yuan_prices_or_null():
    run_node(PAIR_ROWS + r"""
load('$("#btn-run-diff").addEventListener', 'function renderDiff(');
const first=add(),second=add(),empty=add();
for(const row of [first,second,empty])for(const side of ['self','comp'])assert.strictEqual(row.querySelector('.pair-'+side+'-floor').value,'');
assert(first.innerHTML.includes('本品底价（元）'));assert(first.innerHTML.includes('竞品底价（元）'));
first.querySelector('.pair-self-floor').value='100000.5';first.querySelector('.pair-comp-floor').value='120000';
second.querySelector('.pair-self-floor').value='90000';
second.querySelector('.pair-comp-floor').value='110000.25';
let sent;
context.api=async(method,...args)=>{
  if(method==='workdir_path')return args.join('/');
  assert.strictEqual(method,'run_diff');sent=args[2];
  return {ok:true,md_path:'result.md',missing_valuation:[]};
};
await node('#btn-run-diff').listeners.click[0]();
assert.deepStrictEqual(JSON.parse(JSON.stringify(sent)),[
  {self_trim:'Self',comp_trim:'Comp',self_floor_price:100000.5,comp_floor_price:120000},
  {self_trim:'Self',comp_trim:'Comp',self_floor_price:90000,comp_floor_price:110000.25},
  {self_trim:'Self',comp_trim:'Comp',self_floor_price:null,comp_floor_price:null},
]);
node('#diff-mode').value='competitor';const competitor=add();
assert(competitor.innerHTML.includes('左侧底价（元）'));assert(competitor.innerHTML.includes('右侧底价（元）'));
assert.strictEqual(competitor.querySelector('.pair-self-floor').value,'');
""")


def test_invalid_floor_prices_never_send_a_request_and_show_clear_chinese_errors():
    run_node(PAIR_ROWS + r"""
load('$("#btn-run-diff").addEventListener', 'function renderDiff(');
const row=add(),left=row.querySelector('.pair-self-floor'),right=row.querySelector('.pair-comp-floor');
let requests=0,messages=[];
context.api=async()=>{requests++;throw Error('Invalid amount must not call API');};
context.toast=(message,kind)=>messages.push({message,kind});
for(const value of ['0','-1','NaN','Infinity','1e309','abc']) {
  left.value=value;await node('#btn-run-diff').listeners.click[0]();
  assert(left.reported);assert(left.error.includes('第1组本品底价'));
  assert(left.error.includes('大于0')&&left.error.includes('单位元'));
  assert.strictEqual(messages.at(-1).kind,'err');assert.strictEqual(requests,0);
}
left.value='';left.validity.badInput=true;
await node('#btn-run-diff').listeners.click[0]();assert.strictEqual(requests,0);
left.validity.badInput=false;left.value='100000';right.value='-2';node('#diff-mode').value='competitor';
await node('#btn-run-diff').listeners.click[0]();
assert(right.error.includes('第1组右侧底价'));assert.strictEqual(requests,0);
right.value='';emit(row,'input','.pair-comp-floor');
assert.strictEqual(right.error,'');
assert.strictEqual(context.collectComparisonPairs()[0].self_floor_price,100000);
assert.strictEqual(context.collectComparisonPairs()[0].comp_floor_price,null);
""")


def test_switching_one_trim_clears_only_its_price_and_invalidates_results():
    run_node(PAIR_ROWS + r"""
const row=add(),other=add();
row.querySelector('.pair-self-floor').value='100000';row.querySelector('.pair-comp-floor').value='120000';
other.querySelector('.pair-self-floor').value='80000';seedResult();
row.querySelector('.pair-self').value='Self2';emit(row,'change','.pair-self');
assert.strictEqual(row.querySelector('.pair-self-floor').value,'');
assert.strictEqual(row.querySelector('.pair-comp-floor').value,'120000');
assert.strictEqual(other.querySelector('.pair-self-floor').value,'80000');
assert.strictEqual(ST.diff,null);assert(node('#diff-result').hidden);
row.querySelector('.pair-self-floor').value='90000';seedResult();
row.querySelector('.pair-comp').value='Comp2';emit(row,'change','.pair-comp');
assert.strictEqual(row.querySelector('.pair-comp-floor').value,'');
assert.strictEqual(row.querySelector('.pair-self-floor').value,'90000');assert.strictEqual(ST.diff,null);
""")


def test_floor_price_input_discards_a_late_comparison_response():
    run_node(PAIR_ROWS + r"""
load('$("#btn-run-diff").addEventListener', 'function renderDiff(');
const row=add();row.querySelector('.pair-self-floor').value='100000';
let resolveRun,markRun;const started=new Promise(resolve=>markRun=resolve);
context.api=async(method,...args)=>{
  if(method==='workdir_path')return args.join('/');
  assert.strictEqual(method,'run_diff');assert.strictEqual(args[2][0].self_floor_price,100000);
  markRun();return new Promise(resolve=>resolveRun=resolve);
};
const running=node('#btn-run-diff').listeners.click[0]();await started;
row.querySelector('.pair-self-floor').value='90000';emit(row,'input','.pair-self-floor');
resolveRun({ok:true,md_path:'old.md',missing_valuation:[]});await running;
assert.strictEqual(ST.diff,null);assert(node('#diff-result').hidden);
""")


def test_floor_price_input_cancels_export_after_the_save_dialog_opens():
    run_node(PAIR_ROWS + r"""
load('$("#btn-export-result").addEventListener', '/* ---------- ⑥ 设置');
const row=add();seedResult();
let resolveDialog,markDialog,requests=0;const opened=new Promise(resolve=>markDialog=resolve);
context.api=async method=>{
  requests++;assert.strictEqual(method,'save_file_dialog');markDialog();
  return new Promise(resolve=>resolveDialog=resolve);
};
const exporting=node('#btn-export-result').listeners.click[0]();await opened;
row.querySelector('.pair-comp-floor').value='120000';emit(row,'input','.pair-comp-floor');
resolveDialog('old.md');await exporting;
assert.strictEqual(requests,1);assert.strictEqual(ST.diff,null);assert(node('#diff-result').hidden);
""")


def test_overall_result_shows_yuan_prices_formula_and_backend_missing_reasons():
    run_node(r"""
load('function renderDiff(', '$("#btn-export-result").addEventListener');
const priced={pair:{self_trim:'A',comp_trim:'B'},self_price:10.9,comp_price:11,
  self_floor_price:120000,comp_floor_price:110000.25,more:[],less:[],
  valuation:{config_adv:1000.5,flat_adv:2000.5,overall:-8999.25,total_more:1000.5,total_less:0,detail:[]}};
const missing={...priced,self_floor_price:null,valuation:{config_adv:null,flat_adv:null,overall:null,
  config_adv_reason:'缺少热泵赋值',flat_adv_reason:'缺少指导价口径',overall_reason:'本品底价未填写',detail:[]}};
for(const [mode,left,right] of [['self','本品','竞品'],['competitor','左侧','右侧']]) {
  node('#diff-mode').value=mode;
  context.renderDiff({ok:true,groups:[priced,missing],cells:[]});
  const html=node('#backup-table').innerHTML;
  assert(html.includes('综合竞争力（元）'));
  assert(html.includes(left+'底价：120000 元'));assert(html.includes(right+'底价：110000.25 元'));
  assert(html.includes('1000.5＋110000.25－120000＝-8999.25 元'));
  assert(html.includes('综合竞争力＝配置优势＋'+right+'底价－'+left+'底价'));
  const formula=html.match(/<p>综合竞争力[^<]*<\/p>/)[0];assert(!formula.includes('×10000'));
  for(const reason of ['缺少热泵赋值','缺少指导价口径','本品底价未填写'])assert(html.includes(reason));
  assert(!html.includes('未设置计算公式'));assert(!/<details\b[^>]*\bopen(?:\s|=|>)/.test(html));
}
context.renderDiff({ok:true,groups:[{...priced,self_floor_price:null,valuation:{overall:null,detail:[]}}],cells:[]});
assert(node('#backup-table').innerHTML.includes('请填写双方底价后计算综合竞争力'));
""")
