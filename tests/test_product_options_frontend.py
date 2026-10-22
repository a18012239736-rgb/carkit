from test_frontend_comparison_state import run_node


HARNESS = r"""
let definition,changes=0,invalidations=0;
context.Vue={ref:value=>({value}),computed:get=>({get value(){return get();}}),watch(){},
  createApp:options=>{definition=options;return {mount(){},unmount(){}};}};
vm.runInContext(fs.readFileSync('ui/config-editor.js','utf8'),context);
vm.runInContext(fs.readFileSync('ui/ppt-draft-editor.js','utf8'),context);
function root(){return {classList:{add(){},remove(){}}};}
function config(model,kind='snapshot',review=false) {
  context.window.ConfigEditor.mount(root(),{model,kind,review,choices:()=>[],
    cascade:(_,edited)=>edited,updateSnapshot(){throw new Error('Options must not change valued cells');},
    onChange(){changes++;}});
  return definition.setup();
}
function draft(model) {
  context.window.PptDraftEditor.mount(root(),model,{onChange(){changes++;},onInvalidate(){invalidations++;}});
  return definition.setup();
}
function event(value){return {target:{value,setCustomValidity(){},reportValidity(){}}};}
function plain(value){return JSON.parse(JSON.stringify(value));}
"""


def test_grouped_configuration_editors_hide_unused_rows_without_losing_saved_data():
    run_node(HARNESS + r"""
for(const kind of ['snapshot','ladder']) {
  const trims=[{name:'A',mix:'40%'},{name:'B',mix:'60%'}];
  const cells=[2,7,20,29,35,36,43,99].map(no=>({no,name:'配置'+no,
    values:kind==='snapshot'?{A:'✕',B:'●'}:['✕','●']}));
  const model={trims,[kind==='snapshot'?'cells':'items']:cells};
  const original=JSON.stringify(model),editor=config(model,kind,true);
  const groups=editor.groups.value,rows=groups.flatMap(group=>group.rows);
  assert(!rows.some(row=>row.cell.no===2));
  assert.strictEqual(new Set(rows.map(row=>row.key)).size,rows.length);
  assert.deepStrictEqual(plain(rows.map(row=>row.serial)),plain(rows.map((_,i)=>i+1)));
  assert.strictEqual(groups[groups.length-1].name,'其他配置');
  assert.strictEqual(rows.filter(row=>row.cell.no===36).length,5);
  assert(rows.every(row=>cells.includes(row.cell)));
  assert.strictEqual(JSON.stringify(model),original);
  assert(!definition.template.includes("key:'mix'"));
  if(kind==='ladder') {
    const mirror=rows.find(row=>row.cell.no===20);
    editor.change(mirror.cell,1,null,'电调+折叠+加热');
    assert.strictEqual(cells.find(cell=>cell.no===20).values[1],'电调+折叠+加热');
    assert.strictEqual(cells.find(cell=>cell.no===2).values[1],'●');
    assert.strictEqual(model.trims[1].mix,'60%');
  }
}
""")


def test_configuration_editors_use_autohome_groups_without_losing_configuration_rows():
    run_node(HARNESS + r"""
const checklist=JSON.parse(fs.readFileSync('engine/rules/checklist_v1.json','utf8')).items;
const catalogue=JSON.parse(fs.readFileSync('engine/rules/autohome_categories.json','utf8')).groups;
for(const kind of ['snapshot','ladder']) {
  const cells=checklist.map(item=>({...item,
    values:kind==='snapshot'?{基础型:'✕',舒适型:'●'}:['✕','●']}));
  const model={trims:[{name:'基础型'},{name:'舒适型'}],[kind==='snapshot'?'cells':'items']:cells};
  const original=JSON.stringify(model),editor=config(model,kind),groups=editor.groups.value;
  const names=plain(groups.map(group=>group.name));
  assert.deepStrictEqual(catalogue.map(group=>group.name).filter(name=>names.includes(name)),names);
  const groupFor=no=>groups.find(group=>group.rows.some(row=>row.cell.no===no)).name;
  for(const [no,name] of [[5,'被动安全'],[7,'驾驶硬件'],[9,'驾驶功能'],[44,'天窗/玻璃'],
    [29,'方向盘/内后视镜'],[32,'车内充电'],[36,'座椅配置'],[37,'音响/车内灯光']]) {
    assert.strictEqual(groupFor(no),name);
  }
  const rows=groups.flatMap(group=>group.rows);
  const visible=checklist.filter(item=>!item.merged_into && item.no!==2).map(item=>item.no).sort((a,b)=>a-b);
  assert.deepStrictEqual(plain([...new Set(rows.map(row=>row.cell.no))].sort((a,b)=>a-b)),visible);
  assert.strictEqual(new Set(rows.map(row=>row.key)).size,rows.length);
  assert.deepStrictEqual(plain(rows.map(row=>row.serial)),plain(rows.map((_,i)=>i+1)));
  assert.strictEqual(JSON.stringify(model),original);
}
assert.strictEqual(changes,0);
""")

def test_legacy_snapshot_opening_does_not_create_options_or_change_values():
    run_node(HARNESS + r"""
const model={trims:[{name:'基础型'},{name:'舒适型',base:'基础型'}],cells:[{no:7,values:{基础型:'360影像',舒适型:'540影像'}}]};
const original=JSON.stringify(model),editor=config(model);
assert.strictEqual(editor.optionText(0),'');assert.strictEqual(editor.optionText(1),'');
assert.strictEqual(JSON.stringify(model),original);assert.strictEqual(changes,0);
const row=definition.template.match(/<tr v-if="kind==='snapshot'"><td class="no">—<\/td><td>选装配置[\s\S]*?<\/tr>/)[0];
assert(row.includes(':aria-label="t.name+\'选装配置\'"'));
assert(row.includes(':value="optionText(i)"'));assert(row.includes('不参与赋值'));
""")


def test_snapshot_option_textarea_normalizes_each_trim_without_inheritance_or_pricing():
    run_node(HARNESS + r"""
const model={trims:[{name:'基础型'},{name:'舒适型',base:'基础型'}],cells:[{no:7,values:{基础型:'360影像',舒适型:'540影像'}}]};
const original=JSON.stringify(model.cells),editor=config(model);
const handler=definition.template.match(/@change="(options\(i,[^"]+)"/)[1];
vm.runInNewContext(handler,{...editor,i:0,$event:event('  天窗选装包\r\n\n车漆包\n 天窗选装包 \n')});
assert.deepStrictEqual(plain(model.options),{基础型:['天窗选装包','车漆包']});
assert.strictEqual(editor.optionText(0),'天窗选装包\n车漆包');
assert.strictEqual(editor.optionText(1),''); // A comparison base is not optional-equipment inheritance.
vm.runInNewContext(handler,{...editor,i:1,$event:event('副驾座椅包\n专属轮毂')});
assert.deepStrictEqual(plain(model.options.舒适型),['副驾座椅包','专属轮毂']);
assert.strictEqual(JSON.stringify(model.cells),original);assert.strictEqual(changes,2);
const saved=plain(model);assert.deepStrictEqual(saved.options.基础型,['天窗选装包','车漆包']);
""")


def test_snapshot_rename_preserves_optional_equipment_with_updated_trim_key():
    run_node(HARNESS + r"""
const model={trims:[{name:'A'},{name:'B',base:'A'}],cells:[{no:7,values:{A:'360影像',B:'540影像'},links:{B:'A'}}],options:{A:['全景天窗'],B:['轮毂包']}};
const editor=config(model,'snapshot',true),handler=definition.template.match(/@change="(rename\(i,[^"]+)"/)[1];
vm.runInNewContext(handler,{...editor,i:0,$event:event('新基础型')});
assert.deepStrictEqual(plain(model.options),{新基础型:['全景天窗'],B:['轮毂包']});
assert.strictEqual(editor.optionText(0),'全景天窗');assert.strictEqual(editor.optionText(1),'轮毂包');
assert.strictEqual(model.trims[1].base,'新基础型');assert.strictEqual(model.cells[0].links.B,'新基础型');
assert.strictEqual(model.cells[0].values.新基础型,'360影像');assert.strictEqual(changes,1);
const saved=plain(model);assert(!('A' in saved.options));
editor.rename(0,event('B'));assert.strictEqual(model.trims[0].name,'新基础型');assert.strictEqual(changes,1);
""")


def test_snapshot_clearing_options_affects_only_the_selected_trim():
    run_node(HARNESS + r"""
const model={trims:[{name:'A'},{name:'B',base:'A'}],cells:[],options:{A:['天窗'],B:['轮毂']}};
const editor=config(model);editor.options(0,' \r\n\n');
assert.deepStrictEqual(plain(model.options),{A:[],B:['轮毂']});
assert.strictEqual(editor.optionText(0),'');assert.strictEqual(editor.optionText(1),'轮毂');assert.strictEqual(changes,1);
""")


def test_optional_equipment_row_is_snapshot_only_not_competitor_editor():
    run_node(HARNESS + r"""
const model={trims:[{name:'A'}],items:[{no:7,values:['540影像']}],options:{A:['原有数据']}};
const original=JSON.stringify(model),editor=config(model,'ladder');
const row=definition.template.match(/<tr v-if="kind==='snapshot'"><td class="no">—<\/td><td>选装配置[\s\S]*?<\/tr>/)[0];
assert(row.startsWith('<tr v-if="kind===\'snapshot\'"'));
assert.strictEqual(editor.kind,'ladder');assert.strictEqual(JSON.stringify(model),original);assert.strictEqual(changes,0);
""")


def test_ppt_draft_options_are_editable_independent_and_normalized_on_blur():
    run_node(HARNESS + r"""
const model={columns:[{name:'A',base:null,price:8.99,text:'540°透明底盘'},{name:'B',base:'A',price:9.99,text:'座椅通风'}]};
const editor=draft(model),originalText=model.columns.map(c=>c.text);
assert(definition.template.includes(':value="col.options||\'\'"'));
assert(definition.template.includes('仅本版型展示，不参与赋值'));
const input=definition.template.match(/@input="(set\(i,'options',[^"]+)"/)[1];
const blur=definition.template.match(/@change="(cleanOptions\(i,[^"]+)"/)[1];
vm.runInNewContext(input,{...editor,i:0,$event:event('天窗包\n')});
assert.strictEqual(model.columns[0].options,'天窗包\n'); // Keep a trailing newline while typing the next item.
vm.runInNewContext(blur,{...editor,i:0,$event:event(' 天窗包\r\n轮毂包\n天窗包\n\n')});
assert.strictEqual(model.columns[0].options,'天窗包\n轮毂包');
assert.strictEqual(model.columns[1].options,undefined);assert.deepStrictEqual(model.columns.map(c=>c.text),originalText);
editor.add();assert.strictEqual(model.columns[2].options,'');assert.strictEqual(model.columns[2].base,null);
editor.rename(0,event('新A'));assert.strictEqual(model.columns[1].base,'新A');assert.strictEqual(model.columns[0].options,'天窗包\n轮毂包');
assert.strictEqual(changes,4);assert.strictEqual(invalidations,4);
assert.strictEqual(plain(model).columns[0].options,'天窗包\n轮毂包');
""")


def test_ppt_expand_collects_optional_text_with_renamed_trims_and_keeps_preview_and_saved_options():
    run_node(r"""
load("$('#ppt-expand').onclick", "$('#ppt-save').onclick");
load("$('#ppt-save').onclick", '// Arrange existing controls');
ST.pptDraft={model:'原车型',price_kind:'指导价',source:'测试PPT',columns:[
  {name:'原基础型',base:null,price:8.99,text:'540°透明底盘',options:'旧天窗包'},
  {name:'原舒适型',base:'原基础型',price:9.99,text:'座椅通风',options:'旧车漆包'}]};
const row=fields=>({querySelector:selector=>Object.hasOwn(fields,selector)?{value:fields[selector]}:null});
const rows=[
  row({'.ppt-name':' 新基础型 ','.ppt-base':'','.ppt-price':'8.99','.ppt-text':'540°透明底盘','.ppt-options':' 天窗包\n轮毂包\n'}),
  row({'.ppt-name':'新舒适型','.ppt-base':'原基础型','.ppt-price':'9.99','.ppt-text':'座椅通风','.ppt-options':'专属车漆'})];
context.$$=selector=>{assert.strictEqual(selector,'#ppt-columns .ppt-column');return rows;};
node('#ppt-model').value='测试本品';node('#ppt-price-kind').value='指导价';node('#ppt-status').style={};
let sent,rendered=0,saved;
const snapshot={model:'测试本品',status:'待确认',trims:[{name:'新基础型'},{name:'新舒适型',base:'新基础型'}],
  cells:[{no:7,values:{新基础型:'540影像',新舒适型:'540影像'}}],
  options:{新基础型:['天窗包','轮毂包'],新舒适型:['专属车漆']},rulings:[{remaining:{}}]};
context.api=async(method,...args)=>{
  if(method==='ppt_preview') {sent=args[0];return {snapshot};}
  assert.strictEqual(method,'save_ppt_snapshot');assert.strictEqual(args[0],snapshot);assert.strictEqual(args[1],true);
  saved=JSON.parse(JSON.stringify(args[0]));return {snapshot:saved,path:'快照/测试本品.json'};
};
context.renderSnapshot=async()=>{rendered++;assert.deepStrictEqual(JSON.parse(JSON.stringify(ST.snapshot.options)),snapshot.options);};
context.collectSnapshotEdits=()=>true;
await node('#ppt-expand').onclick();
assert.strictEqual(sent.model,'测试本品');assert.strictEqual(sent.source,'测试PPT');
assert.deepStrictEqual(JSON.parse(JSON.stringify(sent.columns)),[
  {name:'新基础型',base:null,price:'8.99',text:'540°透明底盘',options:' 天窗包\n轮毂包\n'},
  {name:'新舒适型',base:'新基础型',price:'9.99',text:'座椅通风',options:'专属车漆'}]);
assert.strictEqual(ST.snapshot,snapshot);assert.strictEqual(ST.snapshotPath,'');
assert.strictEqual(node('#ppt-review').hidden,false);assert.strictEqual(node('#ppt-confirm').checked,false);
node('#ppt-confirm').checked=true;await node('#ppt-save').onclick();
assert.deepStrictEqual(saved.options,{新基础型:['天窗包','轮毂包'],新舒适型:['专属车漆']});
assert.strictEqual(ST.snapshot,saved);assert.strictEqual(ST.snapshotPath,'快照/测试本品.json');
assert.strictEqual(rendered,2);assert.strictEqual(node('#ppt-review').hidden,true);
""")
