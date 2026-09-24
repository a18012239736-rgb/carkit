/* Vue island for the configuration-ladder trim selector. */
(() => {
  const {createApp, ref, computed} = Vue;
  let current = null;
  function mount(root, trims) {
    current?.unmount();
    const price = value => {
      const match = String(value ?? '').replace(/,/g, '').match(/\d+(?:\.\d+)?/);
      return match ? Number(match[0]) : Infinity;
    };
    const order = [...trims.keys()].sort((a,b)=>(price(trims[a].price_guide)-price(trims[b].price_guide)) || a-b);
    const app = createApp({setup() {
      const used = ref(Object.fromEntries(order.map(i=>[i,true])));
      // 自动形成价格阶梯：最低价为基础版型，后续版型默认对比前一个更低价版型。
      const bases = ref(Object.fromEntries(order.map((i,pos)=>[i,pos ? order[pos-1] : ''])));
      const earlier = i => order.filter(j=>j!==i && used.value[j] && order.indexOf(j)<order.indexOf(i));
      const options = i => earlier(i);
      const plan = computed(() => order.filter(i=>used.value[i]).map(i=>({target:i,base:bases.value[i]===''||bases.value[i]==null?null:Number(bases.value[i])})));
      function toggle(i) {
        if(!used.value[i]) { bases.value[i]=''; return; }
        const previous = earlier(i);
        if(previous.length && !bases.value[i]) bases.value[i]=previous[previous.length-1];
        order.forEach(j=>{
          if(!used.value[j]) return;
          const prev=earlier(j), base=bases.value[j];
          if(!prev.length) bases.value[j]='';
          else if(!base || !used.value[base] || !prev.includes(base)) bases.value[j]=prev[prev.length-1];
        });
      }
      function getPlan() { return plan.value; }
      return {trims,order,used,bases,options,toggle,getPlan};
    },template:`<div class="stage-editor-grid"><div v-for="i in order" :key="i" class="stage-trim-row"><label><input type="checkbox" v-model="used[i]" @change="toggle(i)"> {{trims[i].name}}（{{trims[i].price_guide ?? '待核'}}万）</label><select v-model="bases[i]" :disabled="!used[i] || !options(i).length"><option value="">基本配置</option><option v-for="j in options(i)" :value="j">{{trims[j].name}}</option></select></div></div>`});
    root.replaceChildren(); app.mount(root); current=app; root.__stagePlan=()=>app._instance.proxy.getPlan();
  }
  window.StageEditor={mount,plan:root=>root?.__stagePlan?.()||[]};
})();
