from test_frontend_comparison_state import run_node
from test_frontend_stage_display import SETTINGS_HARNESS


CHECKBOX_BINDINGS = r"""
const checkbox = settingsTemplate.match(/<input\b[^>]*:checked="[^"]+"[^>]*>/)?.[0];
assert(checkbox, 'The row checkbox must explicitly map checked to excluded');
const checkedExpression = checkbox.match(/:checked="([^"]+)"/)[1];
const changeExpression = checkbox.match(/@change="([^"]+)"/)[1];
const checked = name => Function('selected', 'name', 'return (' + checkedExpression + ');')(state.selected.value, name);
const change = (name, value) => Function('setGroup', 'name', '$event', changeExpression)(state.setGroup, name, {target:{checked:value}});
"""


def test_existing_excluded_rows_are_checked_without_inverting_saved_preferences():
    run_node(SETTINGS_HARNESS + CHECKBOX_BINDINGS + r"""
settingsApi=async()=>({ok:true,rows:['厂商','CLTC纯电续航里程(km)','选装套件'],
  excluded_rows:['厂商','其他车型隐藏项'],option_status:{'选装套件':'optional'}});
await state.load();
assert.strictEqual(checked('厂商'),true);
assert.strictEqual(checked('其他车型隐藏项'),true);
assert.strictEqual(checked('CLTC纯电续航里程(km)'),false);
assert.strictEqual(checked('选装套件'),false);
assert.strictEqual(state.optionLabel('选装套件'),'选配');
assert.deepStrictEqual(plain(state.saved.value),['厂商','其他车型隐藏项']);
assert.deepStrictEqual(plain(state.selected.value),['厂商','其他车型隐藏项']);
assert.strictEqual(state.selectedCount(state.visible.value),2);
assert.strictEqual(state.dirty.value,false);
assert(settingsTemplate.includes('不展示的配置'));
assert(settingsTemplate.includes('勾选即不展示'));
assert(settingsTemplate.includes('仅查看不展示项'));
assert(settingsTemplate.includes('保存不展示清单'));
assert(!settingsTemplate.includes('勾选显示'));
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
change('厂商',false); // Unchecking removes a row from the exclusion list.
change('CLTC纯电续航里程(km)',true); // Checking excludes a visible row.
assert.strictEqual(checked('厂商'),false);
assert.strictEqual(checked('CLTC纯电续航里程(km)'),true);
assert.strictEqual(state.dirty.value,true);
await state.save();
assert.deepStrictEqual(payload,['其他车型隐藏项','CLTC纯电续航里程(km)']);
assert.deepStrictEqual(plain(state.saved.value),payload);
assert.strictEqual(state.dirty.value,false);
assert.strictEqual(savedCallbacks,1);
await state.load();
assert.strictEqual(checked('厂商'),false);
assert.strictEqual(checked('CLTC纯电续航里程(km)'),true);
assert.strictEqual(checked('其他车型隐藏项'),true);
""")


def test_category_buttons_use_current_filtered_rows_with_excluded_checked_semantics():
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
clickGroup('全部不展示');
assert.strictEqual(checked('前排无线充电'),true);
assert.strictEqual(checked('后排无线充电'),true);
assert.strictEqual(checked('USB接口'),false); // Outside the search stays untouched.
assert.strictEqual(checked('车联网'),true); // Another category stays untouched.
assert.strictEqual(state.selectedCount(state.visibleGroups.value[0].rows),2);
state.excludedOnly.value=true;
assert.deepStrictEqual(plain(state.visible.value),['前排无线充电','后排无线充电']);
clickGroup('取消不展示');
assert.strictEqual(checked('前排无线充电'),false);
assert.strictEqual(checked('后排无线充电'),false);
assert.deepStrictEqual(plain(state.visible.value),[]); // The filter continues to mean hidden items.
assert.deepStrictEqual(plain(state.selected.value),['车联网']);
""")


def test_undo_reload_and_new_source_rows_do_not_flip_visibility():
    run_node(SETTINGS_HARNESS + CHECKBOX_BINDINGS + r"""
let rows=['厂商','续航'];
settingsApi=async()=>({ok:true,rows,excluded_rows:['厂商']});
await state.load();change('厂商',false);change('续航',true);
state.undo();
assert.strictEqual(checked('厂商'),true);
assert.strictEqual(checked('续航'),false);
assert.strictEqual(state.dirty.value,false);
rows=['厂商','续航','新抓取的额外配置'];modelName='车型 B';
await state.load();
assert.strictEqual(checked('厂商'),true);
assert.strictEqual(checked('续航'),false);
assert.strictEqual(checked('新抓取的额外配置'),false);
assert.strictEqual(state.selectedCount(state.visible.value),1);
assert.strictEqual(state.currentModel.value,'车型 B');
assert.deepStrictEqual(plain(state.selected.value),['厂商']);
assert.strictEqual(state.dirty.value,false);
""")


def test_default_exclusions_remain_checked_when_clearing_a_category():
    run_node(SETTINGS_HARNESS + CHECKBOX_BINDINGS + r"""
let stored=['三电系统质保','备胎规格'];
settingsApi=async(method,names)=>{
  if(method==='stage_display_rules')return {ok:true,
    rows:['三电系统质保','备胎规格','续航'],
    groups:[{name:'基本参数',rows:['三电系统质保','备胎规格','续航']}],
    default_excluded_rows:['三电系统质保'],excluded_rows:stored};
  assert.strictEqual(method,'save_stage_display_rules');stored=plain(names);
  return {ok:true,excluded_rows:stored};
};
await state.load();
assert.strictEqual(checked('三电系统质保'),true);
assert.strictEqual(state.editableCount(state.rows.value),1);
assert(settingsTemplate.includes(':disabled="saving || defaults.includes(name)"'));
assert(settingsTemplate.includes('默认不展示'));
change('三电系统质保',false);
assert.strictEqual(checked('三电系统质保'),true);
state.setGroup(state.rows.value,false);
assert.deepStrictEqual(plain(state.selected.value),['三电系统质保']);
assert.strictEqual(state.editableCount(state.rows.value),0);
assert.strictEqual(checked('备胎规格'),false);
await state.save();await state.load();
assert.deepStrictEqual(stored,['三电系统质保']);
assert.strictEqual(checked('三电系统质保'),true);
assert.strictEqual(state.dirty.value,false);
""")
