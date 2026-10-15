from test_frontend_comparison_state import run_node
from test_frontend_stage_display import SETTINGS_HARNESS


CHECKBOX_BINDINGS = r"""
const checkbox = settingsTemplate.match(/<input\b[^>]*:checked="[^"]+"[^>]*>/)?.[0];
assert(checkbox, 'The row checkbox must explicitly map checked to visible');
const checkedExpression = checkbox.match(/:checked="([^"]+)"/)[1];
const changeExpression = checkbox.match(/@change="([^"]+)"/)[1];
const checked = name => Function('selected', 'name', 'return (' + checkedExpression + ');')(state.selected.value, name);
const change = (name, value) => Function('setGroup', 'name', '$event', changeExpression)(state.setGroup, name, {target:{checked:value}});
"""


def test_existing_hidden_rows_are_unchecked_without_migrating_saved_preferences():
    run_node(SETTINGS_HARNESS + CHECKBOX_BINDINGS + r"""
settingsApi=async()=>({ok:true,rows:['厂商','CLTC纯电续航里程(km)','选装套件'],
  excluded_rows:['厂商','其他车型隐藏项'],option_status:{'选装套件':'optional'}});
await state.load();
assert.strictEqual(checked('厂商'),false);
assert.strictEqual(checked('其他车型隐藏项'),false);
assert.strictEqual(checked('CLTC纯电续航里程(km)'),true);
assert.strictEqual(checked('选装套件'),true);
assert.strictEqual(state.optionLabel('选装套件'),'选配');
assert.deepStrictEqual(plain(state.saved.value),['厂商','其他车型隐藏项']);
assert.deepStrictEqual(plain(state.selected.value),['厂商','其他车型隐藏项']);
assert.strictEqual(state.shownCount(state.visible.value),2);
assert.strictEqual(state.dirty.value,false);
assert(settingsTemplate.includes('展示的配置'));
assert(settingsTemplate.includes('勾选显示，取消隐藏'));
assert(settingsTemplate.includes('仅查看隐藏项'));
""")


def test_check_uncheck_and_save_still_send_only_hidden_row_names_to_backend():
    run_node(SETTINGS_HARNESS + CHECKBOX_BINDINGS + r"""
let saved=['厂商','其他车型隐藏项'], payload;
settingsApi=async(method,names)=>{
  if(method==='stage_display_rules')return {ok:true,rows:['厂商','CLTC纯电续航里程(km)'],excluded_rows:saved};
  assert.strictEqual(method,'save_stage_display_rules');
  payload=plain(names);saved=[...names];return {ok:true,excluded_rows:saved};
};
await state.load();
change('厂商',true); // Checking makes an old hidden row visible.
change('CLTC纯电续航里程(km)',false); // Unchecking hides a visible row.
assert.strictEqual(checked('厂商'),true);
assert.strictEqual(checked('CLTC纯电续航里程(km)'),false);
assert.strictEqual(state.dirty.value,true);
await state.save();
assert.deepStrictEqual(payload,['其他车型隐藏项','CLTC纯电续航里程(km)']);
assert.deepStrictEqual(plain(state.saved.value),payload);
assert.strictEqual(state.dirty.value,false);
assert.strictEqual(savedCallbacks,1);
await state.load();
assert.strictEqual(checked('厂商'),true);
assert.strictEqual(checked('CLTC纯电续航里程(km)'),false);
assert.strictEqual(checked('其他车型隐藏项'),false);
""")


def test_category_buttons_use_current_filtered_rows_with_visible_checked_semantics():
    run_node(SETTINGS_HARNESS + CHECKBOX_BINDINGS + r"""
settingsApi=async()=>({ok:true,rows:['前排无线充电','后排无线充电','USB接口','车联网'],
  groups:[{name:'车内充电',rows:['前排无线充电','后排无线充电','USB接口']},
    {name:'互联网',rows:['车联网']}],excluded_rows:['前排无线充电','车联网']});
await state.load();state.search.value='无线';
assert.deepStrictEqual(plain(state.visibleGroups.value),[{name:'车内充电',rows:['前排无线充电','后排无线充电']}]);
function clickGroup(label) {
  const button=[...settingsTemplate.matchAll(/<button\b[^>]*>[^<]*<\/button>/g)]
    .map(match=>match[0]).find(html=>html.endsWith('>'+label+'</button>'));
  assert(button, 'Missing category action: '+label);
  const expression=button.match(/@click="([^"]+)"/)[1];
  Function('setGroup','group',expression)(state.setGroup,state.visibleGroups.value[0]);
}
clickGroup('全部隐藏');
assert.strictEqual(checked('前排无线充电'),false);
assert.strictEqual(checked('后排无线充电'),false);
assert.strictEqual(checked('USB接口'),true); // Outside the search stays untouched.
assert.strictEqual(checked('车联网'),false); // Another category stays untouched.
assert.strictEqual(state.shownCount(state.visibleGroups.value[0].rows),0);
state.excludedOnly.value=true;
assert.deepStrictEqual(plain(state.visible.value),['前排无线充电','后排无线充电']);
clickGroup('全选显示');
assert.strictEqual(checked('前排无线充电'),true);
assert.strictEqual(checked('后排无线充电'),true);
assert.deepStrictEqual(plain(state.visible.value),[]); // The filter continues to mean hidden items.
assert.deepStrictEqual(plain(state.selected.value),['车联网']);
""")


def test_undo_reload_and_new_source_rows_do_not_flip_visibility():
    run_node(SETTINGS_HARNESS + CHECKBOX_BINDINGS + r"""
let rows=['厂商','续航'];
settingsApi=async()=>({ok:true,rows,excluded_rows:['厂商']});
await state.load();change('厂商',true);change('续航',false);
state.undo();
assert.strictEqual(checked('厂商'),false);
assert.strictEqual(checked('续航'),true);
assert.strictEqual(state.dirty.value,false);
rows=['厂商','续航','新抓取的额外配置'];modelName='车型 B';
await state.load();
assert.strictEqual(checked('厂商'),false);
assert.strictEqual(checked('续航'),true);
assert.strictEqual(checked('新抓取的额外配置'),true);
assert.strictEqual(state.shownCount(state.visible.value),2);
assert.strictEqual(state.currentModel.value,'车型 B');
assert.deepStrictEqual(plain(state.selected.value),['厂商']);
assert.strictEqual(state.dirty.value,false);
""")
