/* Vue 3 valuation-rule editor. It edits the existing ST.valuation shape in place. */
(() => {
  'use strict';
  const {createApp, ref, computed} = Vue;
  let app = null;
  function mount(root, model, schema, names) {
    app?.unmount();
    app = createApp({
      setup() {
        const valuation = ref(model);
        const rows = computed(() => [...valuation.value.items]
          .filter(item => names[item.no] != null)
          .sort((a,b) => (a.no===45?36.5:a.no)-(b.no===45?36.5:b.no)));
        const label = no => names[no] || String(no);
        const specs = no => schema[String(no)] || [];
        const setFixed = (item, value) => { item.val = value === '' ? null : Number(value); };
        const setParam = (item, key, value) => { item.params ||= {}; item.params[key] = value === '' ? null : Number(value); };
        return {valuation, rows, label, specs, setFixed, setParam};
      },
      template: `<table class="grid valuation-grid vue-valuation-table"><thead><tr><th>#</th><th>配置项</th><th>计价方式</th><th>可修改的金额与阈值</th><th>备注</th></tr></thead><tbody>
        <tr v-for="(item,index) in rows" :key="item.no" :class="{'valuation-excluded':item.rule==='excluded'}">
          <td class="no">{{index+1}}</td><td>{{label(item.no)}}</td>
          <td>{{item.rule==='excluded'?'不参与赋值':item.rule==='dynamic'?'动态分档':'固定金额'}}</td>
          <td v-if="item.rule==='excluded'" class="dim">仅保留配置展示</td>
          <td v-else><div class="valuation-fields"><label v-if="item.rule!=='dynamic'" class="valuation-field"><span>固定金额</span><input type="number" min="0" step="any" :value="item.val ?? ''" @input="setFixed(item,$event.target.value)"><em>元</em></label><label v-for="spec in specs(item.no)" :key="spec.key" class="valuation-field"><span>{{spec.label}}</span><input type="number" min="0" step="any" :value="item.params?.[spec.key] ?? ''" @input="setParam(item,spec.key,$event.target.value)"><em>{{spec.unit||''}}</em></label></div></td>
          <td>{{item.note || ''}}</td>
        </tr></tbody></table>`
    });
    root.classList.add('vue-valuation-editor');
    app.mount(root);
  }
  function unmount() {app?.unmount();app=null;}
  function validate(root) {
    for(const input of root.querySelectorAll('input[type=number]')) {
      if(input.value==='' || !input.checkValidity() || !Number.isFinite(Number(input.value))) {input.focus();return false;}
    }
    return true;
  }
  window.ValuationEditor={mount,unmount,validate};
})();
