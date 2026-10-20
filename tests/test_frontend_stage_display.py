from pathlib import Path

from lxml import html

from test_frontend_comparison_state import run_node


def test_display_settings_are_initially_hidden_directly_below_the_trim_selection_card():
    document = html.fromstring(Path('ui/index.html').read_text(encoding='utf-8'))
    settings = document.xpath('//*[@id="stage-display-settings"]')
    assert len(settings) == 1
    assert settings[0].getparent().get('id') == 'page-scrape'
    assert settings[0].getprevious().get('id') == 'stage-trims'
    assert 'hidden' in settings[0].attrib


def test_display_settings_show_after_reading_a_vehicle_and_hide_when_history_is_cleared():
    run_node(r"""
vm.runInContext('let stageDisplayRevision = 0;',context);
let removed=0;
context.document={querySelector:()=>({remove(){removed++;}})};
context.StageDisplaySettings={refresh(){}};
context.StageEditor={mount(){}};context.window.StageEditor=context.StageEditor;
context.refreshRawList=async()=>{};context.renderCaptureFilters=()=>{};
node('#raw-inspector').replaceChildren=()=>{};
node('#stage-trims').hidden=true;node('#stage-display-settings').hidden=true;
load('function renderStageTrimEditor()', 'function updateStageBases(');
load('function handleStageResult(res)', 'function renderCaptureFilters(');
for(const result of [{ok:false,error:'读取失败'}, {needs_browser:true,message:'请验证'}, {filters:[]}]) {
  context.handleStageResult(result);
  assert.strictEqual(node('#stage-display-settings').hidden,true);
}
context.handleStageResult({ok:true,model:'测试车',series_id:'1',rows:100,
  trims:[{name:'基础',price_guide:10}]});
assert.strictEqual(node('#stage-trims').hidden,false);
assert.strictEqual(node('#stage-display-settings').hidden,false);
assert.strictEqual(removed,1);
assert.strictEqual(vm.runInContext('stageDisplayRevision',context),1);

const record={file:'capture.json',label:'测试车',count:1};
const deleting={dataset:{deleteHistory:'0'}}, opening={dataset:{history:'0'}};
node('#raw-list').querySelectorAll=selector=>selector==='[data-delete-history]'?[deleting]:[opening];
let records=[record];context.refreshDiffSelects=async()=>{};
context.api=async(method,...args)=>{
  if(method==='vehicle_history')return records;
  assert.strictEqual(method,'remove_vehicle_history');assert.strictEqual(args[0],record.file);
  records=[];return {ok:true};
};
load('async function refreshRawList()', '$("#btn-scrape-open").addEventListener');
await context.refreshRawList();await deleting.onclick();
assert.strictEqual(node('#stage-trims').hidden,true);
assert.strictEqual(node('#stage-display-settings').hidden,true);
assert.strictEqual(ST.stage.trims.length,0);
assert.strictEqual(removed,2);
assert.strictEqual(vm.runInContext('stageDisplayRevision',context),2);
""")


def test_ladder_preview_is_below_permanent_result_tools_and_old_vehicle_requests_are_discarded():
    run_node(r"""
let afterSaved;
const siblings=[node('#stage-trims'),node('#stage-display-settings'),node('#stage-result-tools'),node('#advanced-import')];
const fields=new Map();
context.document={
  querySelector:selector=>siblings.find(element=>'#'+element.id===selector) || null,
  createElement(tag){
    assert.strictEqual(tag,'section');
    return {id:'',className:'',innerHTML:'',parentElement:null,
      querySelector:selector=>{if(!fields.has(selector))fields.set(selector,{});return fields.get(selector);},
      querySelectorAll:()=>[],scrollIntoView(){},
      remove(){const index=siblings.indexOf(this);if(index>=0)siblings.splice(index,1);this.parentElement=null;}};
  },
};
const parent={id:'page-scrape'};
for(const [index,id] of ['stage-trims','stage-display-settings','stage-result-tools','advanced-import'].entries()) {
  siblings[index].id=id;siblings[index].parentElement=parent;
}
node('#stage-trims').append=()=>assert.fail('The preview must not be nested inside the trim card');
node('#stage-result-tools').after=panel=>{
  const index=siblings.indexOf(node('#stage-result-tools'));
  siblings.splice(index+1,0,panel);panel.parentElement=parent;
};
context.StageDisplaySettings={mount(root,options){afterSaved=options.onSaved;}};
context.previewButton={};context.stagePlan=()=>[{target:0,base:null}];
context.StageEditor={mount(){}};context.window.StageEditor=context.StageEditor;
ST.stage={model:'车型',trims:[{name:'基础'}]};
load('let stageDisplayRevision =', 'const previewButton =');
load('previewButton.onclick =', "$('#stage-trim-editor').addEventListener");
load('function renderStageTrimEditor()', 'function updateStageBases(');
context.api=async()=>({ok:true,model:'车型',columns:[]});
await context.previewButton.onclick();
assert.deepStrictEqual(siblings.map(element=>element.id),['stage-trims','stage-display-settings','stage-result-tools','ladder-visual','advanced-import']);
assert.strictEqual(siblings[3].parentElement,parent);
assert.strictEqual(siblings[3].className,'card');
await context.previewButton.onclick();
assert.strictEqual(siblings.filter(element=>element.id==='ladder-visual').length,1);
afterSaved();assert(!context.document.querySelector('#ladder-visual'));
await context.previewButton.onclick();context.renderStageTrimEditor();
assert(!context.document.querySelector('#ladder-visual'));

let resolveOld;context.api=async()=>new Promise(resolve=>resolveOld=resolve);
const oldPreview=context.previewButton.onclick();context.renderStageTrimEditor();
resolveOld({ok:true,model:'旧车型',columns:[]});await oldPreview;
assert(!context.document.querySelector('#ladder-visual'));
assert.deepStrictEqual(siblings.map(element=>element.id),['stage-trims','stage-display-settings','stage-result-tools','advanced-import']);
""")


SETTINGS_HARNESS = r"""
let state, settingsTemplate, modelName='车型 A', savedCallbacks=0;
let settingsApi=async()=>{throw new Error('unexpected settings API call');};
context.Vue={ref:value=>({value}),computed:get=>({get value(){return get();}}),
  createApp:options=>{settingsTemplate=options.template;return {mount(){state=options.setup();return state;}};}};
vm.runInContext(fs.readFileSync('ui/stage-display-settings.js','utf8'),context);
const host={querySelector:()=>({open:true})}, plain=value=>JSON.parse(JSON.stringify(value));
context.window.StageDisplaySettings.mount(host,{
  api:(...args)=>settingsApi(...args),model:()=>modelName,onSaved:()=>savedCallbacks++});
"""


def test_optional_badges_reload_with_vehicle_and_never_change_saved_row_names():
    run_node(SETTINGS_HARNESS + r"""
let response={ok:true,rows:['零重力座椅','外后视镜功能','主动降噪'],excluded_rows:[],
  option_status:{'零重力座椅':'optional','外后视镜功能':'mixed'}};
let savedNames;
settingsApi=async(method,names)=>{
  if(method==='stage_display_rules')return response;
  assert.strictEqual(method,'save_stage_display_rules');savedNames=plain(names);
  response.excluded_rows=[...names];
  return {ok:true,excluded_rows:names};
};
await state.load();
assert.strictEqual(state.optionLabel('零重力座椅'),'选配');
assert.strictEqual(state.optionLabel('外后视镜功能'),'含选配');
assert.strictEqual(state.optionLabel('主动降噪'),'');
assert.strictEqual(state.optionLabel('其他车型配置'),'');
assert(settingsTemplate.includes(':value="name"'));
assert(settingsTemplate.includes('v-if="optionLabel(name)" class="stage-display-option"'));
assert(settingsTemplate.includes('隐藏配置也会隐藏对应选配'));
state.selected.value=['零重力座椅','外后视镜功能'];await state.save();
assert.deepStrictEqual(savedNames,['零重力座椅','外后视镜功能']);
response={...response,option_status:{'主动降噪':'optional'}};await state.load();
assert.strictEqual(state.optionLabel('零重力座椅'),'');
assert.strictEqual(state.optionLabel('主动降噪'),'选配');
delete response.option_status;await state.load();
assert.deepStrictEqual(plain(state.optionStatus.value),{});
assert.strictEqual(state.optionLabel('主动降噪'),'');
assert.deepStrictEqual(plain(state.selected.value),['零重力座椅','外后视镜功能']);
""")


def test_optional_badges_distinguish_trim_coverage_and_empty_packages_without_changing_preferences():
    run_node(SETTINGS_HARNESS + r"""
let response={ok:true,rows:['全选装','部分选装','全部混合','部分混合','加热包','标配'],excluded_rows:[],
  option_status:{'全选装':'optional','部分选装':'optional','全部混合':'mixed','部分混合':'mixed','加热包':'package'},
  option_availability:{'全选装':'all','部分选装':'partial','全部混合':'all','部分混合':'partial','加热包':'none'}};
let stored;
settingsApi=async(method,names)=>{
  if(method==='stage_display_rules')return response;
  assert.strictEqual(method,'save_stage_display_rules');stored=plain(names);
  return {ok:true,excluded_rows:names};
};
await state.load();
assert.strictEqual(state.optionLabel('全选装'),'全部版型选装');
assert.strictEqual(state.optionLabel('部分选装'),'部分版型选装');
assert.strictEqual(state.optionLabel('全部混合'),'全部版型含选装');
assert.strictEqual(state.optionLabel('部分混合'),'部分版型含选装');
assert.strictEqual(state.optionLabel('加热包'),'选装包（当前版型无选装记录）');
assert.strictEqual(state.optionLabel('标配'),'');
assert.deepStrictEqual(plain(state.selected.value),[]);
state.setGroup(['加热包','部分选装'],true);await state.save();
assert.deepStrictEqual(stored,['加热包','部分选装']);
assert.strictEqual(state.optionLabel('部分选装'),'部分版型选装');
modelName='车型 B';
response={ok:true,rows:['标配'],excluded_rows:stored};await state.load();
assert.deepStrictEqual(plain(state.optionAvailability.value),{});
assert.deepStrictEqual(plain(state.optionStatus.value),{});
assert.strictEqual(state.optionLabel('部分选装'),'');
assert.strictEqual(state.optionLabel('加热包'),'');
assert.deepStrictEqual(plain(state.selected.value),stored);
""")


def test_search_and_checked_filter_include_saved_rows_from_other_vehicles():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async method=>{
  assert.strictEqual(method,'stage_display_rules');
  return {ok:true,rows:['光感天幕','AR-HUD'],excluded_rows:['AR-HUD','其他车型配置']};
};
await state.load();
assert.deepStrictEqual(plain(state.visible.value),['光感天幕','AR-HUD','其他车型配置']);
state.search.value=' ar-hud ';
assert.deepStrictEqual(plain(state.visible.value),['AR-HUD']);
state.search.value='';state.excludedOnly.value=true;
assert.deepStrictEqual(plain(state.visible.value),['AR-HUD','其他车型配置']);
state.selected.value=['其他车型配置'];
assert.deepStrictEqual(plain(state.visible.value),['其他车型配置']);
assert.strictEqual(state.dirty.value,true);
state.search.value='没有这个配置';assert.deepStrictEqual(plain(state.visible.value),[]);
""")


def test_vehicle_reload_updates_source_without_discarding_draft_and_undo_restores_saved():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async()=>({ok:true,rows:['车型 A 特有配置'],excluded_rows:['备胎规格']});
await state.load();state.selected.value.push('车型 A 特有配置');
modelName='车型 B';
settingsApi=async()=>({ok:true,rows:['车型 B 特有配置'],excluded_rows:['其他已保存清单']});
await state.load();
assert.strictEqual(state.currentModel.value,'车型 B');
assert.deepStrictEqual(plain(state.source.value),['车型 B 特有配置']);
assert.deepStrictEqual(plain(state.saved.value),['备胎规格']);
assert.deepStrictEqual(plain(state.selected.value),['备胎规格','车型 A 特有配置']);
assert(state.visible.value.includes('车型 A 特有配置'));
state.failed.value=true;state.status.value='上次保存失败';state.undo();
assert.deepStrictEqual(plain(state.selected.value),['备胎规格']);
assert.strictEqual(state.dirty.value,false);assert.strictEqual(state.failed.value,false);
assert.strictEqual(state.status.value,'');assert(!state.visible.value.includes('车型 A 特有配置'));
""")


def test_save_failure_preserves_draft_and_does_not_invalidate_existing_preview():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async()=>({ok:true,rows:['原清单','新配置'],excluded_rows:['原清单']});
await state.load();state.selected.value=['新配置'];
for(const failure of ['response','transport']) {
  settingsApi=async(method,names)=>{
    assert.strictEqual(method,'save_stage_display_rules');
    assert.deepStrictEqual(plain(names),['新配置']);
    if(failure==='transport')throw new Error('连接中断');
    return {ok:false,error:'无法写入文件'};
  };
  await state.save();
  assert.deepStrictEqual(plain(state.selected.value),['新配置']);
  assert.deepStrictEqual(plain(state.saved.value),['原清单']);
  assert.strictEqual(savedCallbacks,0);assert.strictEqual(state.dirty.value,true);
  assert.strictEqual(state.saving.value,false);assert.strictEqual(state.failed.value,true);
  assert(state.status.value.includes(failure==='transport'?'连接中断':'无法写入文件'));
}
""")


def test_success_uses_backend_saved_list_refreshes_and_allows_empty_exclusions():
    run_node(SETTINGS_HARNESS + r"""
let saved=['原清单'],rows=['原清单','新配置'],requests=[];
settingsApi=async(method,names)=>{
  requests.push([method,names]);
  if(method==='stage_display_rules')return {ok:true,rows,excluded_rows:saved};
  assert.strictEqual(method,'save_stage_display_rules');
  saved=[...new Set(names)];return {ok:true,excluded_rows:saved};
};
await state.load();state.selected.value=['新配置','新配置'];await state.save();
assert.deepStrictEqual(plain(state.saved.value),['新配置']);
assert.deepStrictEqual(plain(state.selected.value),['新配置']);
assert.strictEqual(savedCallbacks,1);assert.strictEqual(state.dirty.value,false);
assert.strictEqual(state.failed.value,false);assert.strictEqual(state.saving.value,false);
assert(state.status.value.includes('已保存'));
rows=['新配置','后续抓取配置'];modelName='车型 B';
context.window.StageDisplaySettings.refresh();await new Promise(resolve=>setImmediate(resolve));
assert.deepStrictEqual(plain(state.source.value),rows);
assert.strictEqual(state.currentModel.value,'车型 B');
state.selected.value=[];await state.save();await state.load();
assert.deepStrictEqual(plain(saved),[]);assert.deepStrictEqual(plain(state.selected.value),[]);
assert.strictEqual(state.dirty.value,false);assert.strictEqual(savedCallbacks,2);
assert.deepStrictEqual(plain(requests.filter(([method])=>method==='save_stage_display_rules').at(-1)[1]),[]);
state.excludedOnly.value=true;assert.deepStrictEqual(plain(state.visible.value),[]);
""")


def test_late_load_responses_and_errors_cannot_replace_new_vehicle_state():
    run_node(SETTINGS_HARNESS + r"""
for(const stale of ['success','failure']) {
  let resolveOld,rejectOld,calls=0;
  settingsApi=async()=>{
    if(++calls===1)return new Promise((resolve,reject)=>{resolveOld=resolve;rejectOld=reject;});
    return {ok:true,rows:['当前车型配置'],excluded_rows:['当前排除配置']};
  };
  modelName='旧车型';const older=state.load();
  modelName='当前车型';await state.load();
  assert.strictEqual(state.loading.value,false);
  if(stale==='success')resolveOld({ok:true,rows:['过期车型配置'],excluded_rows:['过期排除配置']});
  else rejectOld(new Error('过期请求失败'));
  await older;
  assert.deepStrictEqual(plain(state.source.value),['当前车型配置']);
  assert.deepStrictEqual(plain(state.selected.value),['当前排除配置']);
  assert.strictEqual(state.currentModel.value,'当前车型');
  assert.strictEqual(state.loading.value,false);assert.strictEqual(state.failed.value,false);
  assert.strictEqual(state.status.value,'');assert.strictEqual(state.dirty.value,false);
}
""")


def test_saving_exclusions_discards_in_flight_old_preview_and_markdown():
    run_node(r"""
let afterSaved, resolveOld, removed=0, messages=[];
context.StageDisplaySettings={mount(root,options){afterSaved=options.onSaved;}};
context.document={querySelector(){return {remove(){removed++;}};}};
context.previewButton={};context.stagePlan=()=>[{target:0,base:null}];
context.toast=message=>messages.push(message);ST.stage={model:'车型'};
load('let stageDisplayRevision =', 'const previewButton =');
load('previewButton.onclick =', "$('#stage-trim-editor').addEventListener");
load('$("#btn-stage-export").addEventListener', '$("#btn-import-raw").addEventListener');
context.api=async()=>new Promise(resolve=>resolveOld=resolve);
const preview=context.previewButton.onclick();
afterSaved();
resolveOld({ok:true,model:'旧清单结果',columns:[]});await preview;
assert.strictEqual(removed,1); // No replacement preview was created.
assert.strictEqual(node('#md-preview').hidden,true);
assert.strictEqual(node('#md-preview-text').textContent,'');
const exporting=node('#btn-stage-export').listeners.click[0]();
afterSaved();resolveOld({ok:true,path:'原清单.md',md:'旧清单内容'});await exporting;
assert.strictEqual(node('#md-preview').hidden,true);
assert.strictEqual(node('#md-preview-text').textContent,'');
assert(messages.some(message=>message.includes('原清单.md') && message.includes('重新导出')));
""")


def test_source_categories_keep_autohome_order_and_shared_names_in_each_category():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async()=>({ok:true,
  rows:['指导价','长度(mm)','共享配置','电池能量(kWh)','前备箱'],
  groups:[
    {name:'基本参数',rows:['指导价','共享配置']},
    {name:'车身',rows:['长度(mm)','前备箱']},
    {name:'电池/充电',rows:['电池能量(kWh)','共享配置','共享配置']},
  ],excluded_rows:['共享配置']});
await state.load();
const expected=[
  {name:'基本参数',rows:['指导价','共享配置']},
  {name:'车身',rows:['长度(mm)','前备箱']},
  {name:'电池/充电',rows:['电池能量(kWh)','共享配置']},
];
assert.deepStrictEqual(plain(state.groups.value),expected);
assert.deepStrictEqual(plain(state.visibleGroups.value),expected);
assert.strictEqual(state.selectedCount(state.groups.value[0].rows),1);
assert.strictEqual(state.selectedCount(state.groups.value[1].rows),0);
assert.strictEqual(state.selectedCount(state.groups.value[2].rows),1);
assert.deepStrictEqual(plain(state.visible.value),['指导价','长度(mm)','共享配置','电池能量(kWh)','前备箱']);
""")


def test_default_and_saved_rows_outside_current_vehicle_use_their_supplied_categories():
    run_node(SETTINGS_HARNESS + r"""
const defaults=['电池容量(kWh)','后电动机最大功率(kW)','电池快充时间(小时)'];
settingsApi=async()=>({ok:true,rows:['厂商','前排座椅功能'],
  default_excluded_rows:defaults,excluded_rows:[...defaults,'车载冰箱'],
  groups:[
    {name:'基本参数',rows:['厂商','电池快充时间(小时)']},
    {name:'座椅配置',rows:['前排座椅功能']},
    {name:'电动机',rows:['后电动机最大功率(kW)']},
    {name:'电池/充电',rows:['电池容量(kWh)','电池快充时间(小时)']},
    {name:'空调/冰箱',rows:['车载冰箱']},
  ]});
await state.load();
assert.deepStrictEqual(plain(state.groups.value),[
  {name:'基本参数',rows:['厂商','电池快充时间(小时)']},
  {name:'座椅配置',rows:['前排座椅功能']},
  {name:'电动机',rows:['后电动机最大功率(kW)']},
  {name:'电池/充电',rows:['电池容量(kWh)','电池快充时间(小时)']},
  {name:'空调/冰箱',rows:['车载冰箱']},
]);
assert(!state.groups.value.some(group=>group.name==='其他车型/已保存'));
state.search.value='快充';
assert.deepStrictEqual(plain(state.visibleGroups.value),[
  {name:'基本参数',rows:['电池快充时间(小时)']},
  {name:'电池/充电',rows:['电池快充时间(小时)']},
]);
state.setGroup(state.visibleGroups.value[1].rows,false);
assert.strictEqual(state.selectedCount(state.visibleGroups.value[0].rows),0);
assert.strictEqual(state.selectedCount(state.visibleGroups.value[1].rows),0);
assert(state.selected.value.includes('后电动机最大功率(kW)'));
""")


def test_restored_default_outside_current_vehicle_stays_in_its_category_after_save_and_reload():
    run_node(SETTINGS_HARNESS + r"""
const name='后电动机最大功率(kW)';let stored=[name];
settingsApi=async(method,names)=>{
  if(method==='stage_display_rules')return {ok:true,rows:['前排座椅功能'],
    default_excluded_rows:[name],excluded_rows:stored,
    groups:[{name:'座椅配置',rows:['前排座椅功能']},{name:'电动机',rows:[name]}]};
  assert.strictEqual(method,'save_stage_display_rules');
  stored=plain(names);return {ok:true,excluded_rows:stored};
};
await state.load();state.setGroup([name],false);await state.save();await state.load();
assert.deepStrictEqual(stored,[]);
assert(state.rows.value.includes(name));
assert.deepStrictEqual(plain(state.groups.value[1]),{name:'电动机',rows:[name]});
assert(!state.selected.value.includes(name));
state.excludedOnly.value=true;
assert.deepStrictEqual(plain(state.visibleGroups.value),[]);
state.excludedOnly.value=false;state.setGroup([name],true);await state.save();await state.load();
assert.deepStrictEqual(stored,[name]);
assert.strictEqual(state.selectedCount(state.groups.value[1].rows),1);
""")


def test_category_hide_restore_syncs_shared_names_without_touching_other_rows():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async()=>({ok:true,rows:['主驾调节','座椅记忆','方向盘记忆','车载冰箱'],
  groups:[
    {name:'座椅配置',rows:['主驾调节','座椅记忆']},
    {name:'方向盘/内后视镜',rows:['座椅记忆','方向盘记忆']},
    {name:'空调/冰箱',rows:['车载冰箱']},
  ],excluded_rows:['方向盘记忆','车载冰箱','其他已隐藏']});
await state.load();
const seats=state.visibleGroups.value[0].rows;
state.setGroup(seats,true);state.setGroup(seats,true);
assert.deepStrictEqual(plain(state.selected.value),['方向盘记忆','车载冰箱','其他已隐藏','主驾调节','座椅记忆']);
assert.strictEqual(state.selectedCount(state.groups.value[1].rows),2);
assert.strictEqual(state.dirty.value,true);
state.setGroup(seats,false);
assert.deepStrictEqual(plain(state.selected.value),['方向盘记忆','车载冰箱','其他已隐藏']);
assert.strictEqual(state.selectedCount(state.groups.value[1].rows),1);
assert.strictEqual(state.dirty.value,false);
for(const busy of ['loading','saving']) {
  state[busy].value=true;state.setGroup(seats,true);
  assert.deepStrictEqual(plain(state.selected.value),['方向盘记忆','车载冰箱','其他已隐藏']);
  state[busy].value=false;
}
""")


def test_category_buttons_only_change_current_search_and_checked_filter_results():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async()=>({ok:true,rows:['座椅通风','座椅加热','座椅按摩','方向盘加热'],
  groups:[
    {name:'座椅配置',rows:['座椅通风','座椅加热','座椅按摩']},
    {name:'方向盘/内后视镜',rows:['方向盘加热']},
  ],excluded_rows:['座椅按摩','方向盘加热']});
await state.load();state.search.value='  加热  ';
assert.deepStrictEqual(plain(state.visibleGroups.value),[
  {name:'座椅配置',rows:['座椅加热']},
  {name:'方向盘/内后视镜',rows:['方向盘加热']},
]);
state.setGroup(state.visibleGroups.value[0].rows,true);
assert.deepStrictEqual(plain(state.selected.value),['座椅按摩','方向盘加热','座椅加热']);
assert(!state.selected.value.includes('座椅通风'));
state.search.value='';state.excludedOnly.value=true;
assert.deepStrictEqual(plain(state.visibleGroups.value[0]),{name:'座椅配置',rows:['座椅加热','座椅按摩']});
state.setGroup(state.visibleGroups.value[0].rows,false);
assert.deepStrictEqual(plain(state.selected.value),['方向盘加热']);
assert.deepStrictEqual(plain(state.visibleGroups.value),[{name:'方向盘/内后视镜',rows:['方向盘加热']}]);
state.search.value='没有';assert.deepStrictEqual(plain(state.visibleGroups.value),[]);
""")


def test_missing_categories_and_saved_only_rows_remain_accessible_in_last_groups():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async()=>({ok:true,rows:['已分类','旧数据配置 A','旧数据配置 B'],
  groups:[{name:'座椅配置',rows:['已分类']}],
  excluded_rows:['其他车型隐藏项','已分类']});
await state.load();state.selected.value.push('草稿中的其他车型配置');
assert.deepStrictEqual(plain(state.groups.value),[
  {name:'座椅配置',rows:['已分类']},
  {name:'未分类（旧数据）',rows:['旧数据配置 A','旧数据配置 B']},
  {name:'其他车型/已保存',rows:['其他车型隐藏项','草稿中的其他车型配置']},
]);
state.undo();assert.deepStrictEqual(plain(state.groups.value.at(-1)),{name:'其他车型/已保存',rows:['其他车型隐藏项']});
settingsApi=async()=>({ok:true,rows:['没有分类的历史行'],excluded_rows:['其他车型隐藏项']});
await state.load();
assert.deepStrictEqual(plain(state.groups.value),[
  {name:'未分类（旧数据）',rows:['没有分类的历史行']},
  {name:'其他车型/已保存',rows:['其他车型隐藏项']},
]);
settingsApi=async()=>({ok:true,rows:['分类名称为空的历史行'],groups:[{name:'',rows:['分类名称为空的历史行']}],excluded_rows:[]});
await state.load();
assert.deepStrictEqual(plain(state.groups.value),[{name:'未分类（旧数据）',rows:['分类名称为空的历史行']}]);
""")


def test_changing_vehicle_rebuilds_categories_without_discarding_unsaved_exclusions():
    run_node(SETTINGS_HARNESS + r"""
settingsApi=async()=>({ok:true,rows:['车型 A 座椅','共享配置'],
  groups:[{name:'座椅配置',rows:['车型 A 座椅','共享配置']}],excluded_rows:['备胎规格']});
await state.load();state.setGroup(state.visibleGroups.value[0].rows,true);
modelName='车型 B';
settingsApi=async()=>({ok:true,rows:['共享配置','车型 B 灯光'],
  groups:[{name:'外观/防盗',rows:['共享配置']},{name:'车外灯光',rows:['车型 B 灯光']}],
  excluded_rows:['不应覆盖未保存草稿']});
await state.load();
assert.strictEqual(state.currentModel.value,'车型 B');
assert.deepStrictEqual(plain(state.groups.value),[
  {name:'外观/防盗',rows:['共享配置']},
  {name:'车外灯光',rows:['车型 B 灯光']},
  {name:'其他车型/已保存',rows:['备胎规格','车型 A 座椅']},
]);
assert.deepStrictEqual(plain(state.selected.value),['备胎规格','车型 A 座椅','共享配置']);
assert.deepStrictEqual(plain(state.saved.value),['备胎规格']);
state.undo();
assert.deepStrictEqual(plain(state.groups.value.at(-1)),{name:'其他车型/已保存',rows:['备胎规格']});
assert.strictEqual(state.selectedCount(state.groups.value[0].rows),0);
""")


def test_bulk_category_selection_saves_flat_names_and_reloads_in_new_categories():
    run_node(SETTINGS_HARNESS + r"""
let stored=['其他已保存'],savePayload;
let response={rows:['座椅加热','座椅通风','共享配置','车外扬声器'],groups:[
  {name:'座椅配置',rows:['座椅加热','座椅通风','共享配置']},
  {name:'音响/车内灯光',rows:['共享配置','车外扬声器']},
]};
settingsApi=async(method,names)=>{
  if(method==='stage_display_rules')return {ok:true,...response,excluded_rows:stored};
  assert.strictEqual(method,'save_stage_display_rules');
  savePayload=plain(names);stored=[...new Set(names)];return {ok:true,excluded_rows:stored};
};
await state.load();
state.setGroup(state.groups.value[0].rows,true);state.setGroup(state.groups.value[1].rows,true);
await state.save();
assert.deepStrictEqual(savePayload,['其他已保存','座椅加热','座椅通风','共享配置','车外扬声器']);
assert.strictEqual(savedCallbacks,1);assert.strictEqual(state.dirty.value,false);
response={rows:['共享配置','后续新配置'],groups:[{name:'特色配置',rows:['共享配置','后续新配置']}]};
await state.load();
assert.deepStrictEqual(plain(state.selected.value),stored);
assert.strictEqual(state.selectedCount(state.groups.value[0].rows),1);
assert(!state.selected.value.includes('后续新配置'));
assert.deepStrictEqual(plain(state.groups.value.at(-1)),{
  name:'其他车型/已保存',rows:['其他已保存','座椅加热','座椅通风','车外扬声器'],
});
""")
