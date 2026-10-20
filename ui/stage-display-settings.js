/* Only the configuration-ladder display is filtered; valuation is independent. */
(() => {
  const {createApp, ref, computed} = Vue;
  let current = null, root = null;
  function mount(element, {api, model, onSaved}) {
    root = element;
    current = createApp({setup() {
      const source = ref([]), sourceGroups = ref([]), optionStatus = ref({}), optionAvailability = ref({}), defaults = ref([]), saved = ref([]), selected = ref([]);
      const search = ref(''), excludedOnly = ref(false), currentModel = ref('');
      const loading = ref(false), saving = ref(false), status = ref(''), failed = ref(false);
      const dirty = computed(() => selected.value.length !== saved.value.length || selected.value.some(name => !saved.value.includes(name)));
      const rows = computed(() => [...new Set([...source.value, ...defaults.value, ...saved.value, ...selected.value])]);
      const visible = computed(() => rows.value.filter(name => name.toLowerCase().includes(search.value.trim().toLowerCase()) && (!excludedOnly.value || selected.value.includes(name))));
      const groups = computed(() => {
        const classified = new Set();
        const result = sourceGroups.value.map(group => {
          const names = [...new Set(group.rows)].filter(name => rows.value.includes(name));
          names.forEach(name => classified.add(name));
          return {name: group.name || '未分类（旧数据）', rows: names};
        }).filter(group => group.rows.length);
        const unclassified = source.value.filter(name => !classified.has(name));
        if (unclassified.length) result.push({name: '未分类（旧数据）', rows: [...new Set(unclassified)]});
        const other = rows.value.filter(name => !source.value.includes(name) && !classified.has(name));
        if (other.length) result.push({name: '其他车型/已保存', rows: other});
        return result;
      });
      const visibleGroups = computed(() => {
        const names = new Set(visible.value);
        return groups.value.map(group => ({...group, rows: group.rows.filter(name => names.has(name))})).filter(group => group.rows.length);
      });
      const hasUnclassified = computed(() => groups.value.some(group => group.name === '未分类（旧数据）'));
      let revision = 0;
      async function load() {
        if (saving.value) return;
        const request = ++revision;
        loading.value = true; failed.value = false; status.value = '';
        try {
          const result = await api('stage_display_rules');
          if (!result?.ok) throw new Error(result?.error || '读取不展示清单失败，请重新打开重试');
          if (request !== revision) return;
          const addedDefaults = (result.default_excluded_rows || []).filter(name =>
            !defaults.value.includes(name) && (result.excluded_rows || []).includes(name));
          source.value = result.rows || [];
          sourceGroups.value = result.groups || [];
          optionStatus.value = result.option_status || {};
          optionAvailability.value = result.option_availability || {};
          defaults.value = result.default_excluded_rows || [];
          currentModel.value = model();
          if (!dirty.value) {
            saved.value = result.excluded_rows || [];
            selected.value = [...saved.value];
          } else if (addedDefaults.length) {
            const restored = saved.value.filter(name => !selected.value.includes(name));
            selected.value = [...new Set([...selected.value, ...addedDefaults.filter(name => !restored.includes(name))])];
            saved.value = [...new Set([...saved.value, ...addedDefaults])];
          }
        } catch (error) {
          if (request === revision) { status.value = error.message || '读取不展示清单失败，请重新打开重试'; failed.value = true; }
        } finally { if (request === revision) loading.value = false; }
      }
      async function save() {
        saving.value = true; failed.value = false; status.value = '';
        try {
          const result = await api('save_stage_display_rules', [...selected.value]);
          if (!result?.ok) throw new Error(result?.error || '保存失败，勾选内容仍保留，请重试');
          saved.value = result.excluded_rows || [];
          selected.value = [...saved.value];
          onSaved();
          status.value = '已保存。请重新查看配置阶梯图或导出；已导出的文件不会改动。';
        } catch (error) {
          status.value = error.message || '保存失败，勾选内容仍保留，请重试'; failed.value = true;
        } finally { saving.value = false; }
      }
      function selectedCount(names) { return names.filter(name => selected.value.includes(name)).length; }
      function optionLabel(name) {
        const status = optionStatus.value[name], availability = optionAvailability.value[name];
        if (status === 'package') return '选装包（当前版型无选装记录）';
        if (status === 'optional' || status === 'mixed') {
          if (availability === 'all' || availability === 'partial') {
            return (availability === 'all' ? '全部版型' : '部分版型') + (status === 'mixed' ? '含选装' : '选装');
          }
          return status === 'optional' ? '选配' : '含选配';
        }
        return '';
      }
      function setGroup(names, hidden) {
        if (saving.value || loading.value) return;
        const targets = new Set(names);
        selected.value = hidden ? [...new Set([...selected.value, ...targets])] : selected.value.filter(name => !targets.has(name));
        status.value = ''; failed.value = false;
      }
      function undo() { selected.value = [...saved.value]; status.value = ''; failed.value = false; }
      return {source, rows, defaults, saved, selected, search, excludedOnly, currentModel, loading, saving, status, failed, dirty, visible, groups, visibleGroups, hasUnclassified, optionStatus, optionAvailability, optionLabel, selectedCount, setGroup, load, save, undo};
    }, template: `<details class="card stage-display-settings" @toggle="$event.target === $event.currentTarget && $event.target.open && load()">
      <summary>不展示的配置 <span class="dim">× 表示不展示</span></summary>
      <p class="dim">只影响配置阶梯图、Markdown 和 Excel；不删除原始数据，不改变赋值计算。按汽车之家配置行名称保存，并应用于其他车型。选配在阶梯图下方单列；隐藏配置也会隐藏对应选配。</p>
      <div class="row stage-display-toolbar">
        <input type="text" v-model="search" placeholder="搜索配置名称" aria-label="搜索配置名称">
        <label><input type="checkbox" v-model="excludedOnly"> 仅查看不展示项</label>
      </div>
      <p class="dim stage-display-count">{{currentModel ? '当前车型：' + currentModel : '尚未打开车型；可管理之前保存的不展示配置'}} · 已勾选不展示 {{selectedCount(rows)}} 项<span v-if="dirty">（尚未保存）</span></p>
      <p class="dim stage-display-hint">沿用汽车之家分类；分类按钮仅作用于当前筛选结果。</p>
      <p class="dim">选装标记按当前车型的全部版型统计；“含选装”表示该配置行同时有标配和选装内容。</p>
      <p class="dim" v-if="defaults.length">标有“默认不展示”的项目已预先勾选；可取消勾选并保存，以恢复展示。</p>
      <p class="dim" v-if="hasUnclassified">部分配置尚未匹配到汽车之家分类；重新抓取车型后，可按原分类查看。</p>
      <div class="stage-display-list" :aria-busy="loading" v-if="loading">正在读取配置名称…</div>
      <div class="stage-display-list" v-else>
        <details v-for="(group, index) in visibleGroups" :key="index + ':' + group.name" class="stage-display-group" open>
          <summary>
            <span class="stage-display-group-name">{{group.name}}</span>
            <span class="stage-display-group-count">不展示 {{selectedCount(group.rows)}} / {{group.rows.length}} 项</span>
            <span class="stage-display-group-actions" @click.stop @keydown.stop>
              <button type="button" @click="setGroup(group.rows, true)" :disabled="saving || selectedCount(group.rows) === group.rows.length" :aria-label="group.name + '：全部不展示当前筛选结果'" title="仅作用于本分类当前筛选结果">全部不展示</button>
              <button type="button" @click="setGroup(group.rows, false)" :disabled="saving || !selectedCount(group.rows)" :aria-label="group.name + '：取消不展示当前筛选结果'" title="仅作用于本分类当前筛选结果">取消不展示</button>
            </span>
          </summary>
          <div class="stage-display-group-rows">
            <label v-for="name in group.rows" :key="name" :class="{'is-excluded': selected.includes(name)}">
              <input type="checkbox" :checked="selected.includes(name)" @change="setGroup([name], $event.target.checked)" :value="name" :disabled="saving"><span>{{name}}</span><span v-if="defaults.includes(name)" class="stage-display-option">默认不展示</span><span v-if="optionLabel(name)" class="stage-display-option">{{optionLabel(name)}}</span>
            </label>
          </div>
        </details>
        <p class="dim" v-if="!visible.length">{{source.length || saved.length ? '没有符合筛选条件的配置。' : '打开历史车型或抓取车型后，可勾选不需要展示的配置。'}}</p>
      </div>
      <div class="row stage-display-actions">
        <button type="button" class="primary" @click="save" :disabled="loading || saving || !dirty">{{saving ? '正在保存…' : '保存不展示清单'}}</button>
        <button type="button" @click="undo" :disabled="loading || saving || !dirty">撤销未保存修改</button>
      </div>
      <p class="status" :class="failed ? 'err' : 'ok'" role="status" aria-live="polite">{{status}}</p>
    </details>`}).mount(element);
  }
  window.StageDisplaySettings = {mount, refresh() { if (root?.querySelector('details')?.open) current.load(); }};
})();
