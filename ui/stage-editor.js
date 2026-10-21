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
    const priceOrder = [...trims.keys()].sort((a,b)=>(price(trims[a].price_guide)-price(trims[b].price_guide)) || a-b);
    const app = createApp({setup() {
      const used = ref(Object.fromEntries(priceOrder.map(i=>[i,true])));
      const baseTrim = ref(priceOrder[0] ?? '');
      const order = computed(() => baseTrim.value === '' ? priceOrder : [baseTrim.value,...priceOrder.filter(i=>i!==baseTrim.value)]);
      const bases = ref(Object.fromEntries(priceOrder.map((i,pos)=>[i,pos ? priceOrder[pos-1] : ''])));
      const earlier = i => order.value.filter(j=>j!==i && used.value[j] && order.value.indexOf(j)<order.value.indexOf(i));
      const options = i => earlier(i);
      const plan = computed(() => order.value.filter(i=>used.value[i]).map(i=>({target:i,base:bases.value[i]===''||bases.value[i]==null?null:Number(bases.value[i])})));
      root.__stagePlan = () => plan.value.map(row=>({...row}));
      function repairBases() {
        order.value.forEach(j=>{
          if(!used.value[j]) return;
          const prev=earlier(j), base=bases.value[j];
          if(!prev.length) bases.value[j]='';
          else if(base==='' || base==null || !used.value[base] || !prev.includes(Number(base))) bases.value[j]=prev[prev.length-1];
        });
      }
      function chooseBase(value = baseTrim.value) {
        if(value === '' || !priceOrder.includes(Number(value))) return;
        baseTrim.value = Number(value);
        used.value[baseTrim.value] = true;
        repairBases();
      }
      function toggle(i) {
        if(!used.value[i]) bases.value[i]='';
        if(baseTrim.value === '' || !used.value[baseTrim.value])
          baseTrim.value = priceOrder.find(j=>used.value[j]) ?? '';
        repairBases();
      }
      return {trims,priceOrder,baseTrim,order,used,bases,options,toggle,chooseBase};
    },template:`<div class="stage-editor-grid"><label class="row">基本版型<select id="stage-primary-base" v-model="baseTrim" @change="chooseBase()" :disabled="!trims.length"><option v-if="baseTrim === ''" value="" disabled>请选择基本版型</option><option v-for="i in priceOrder" :key="i" :value="i">{{trims[i].name}}（{{trims[i].price_guide ?? '待核'}}万）</option></select></label><div class="stage-trim-head" aria-hidden="true"><span>输出版型 / 指导价</span><span>相对哪个版型比较</span></div><div v-for="i in order" :key="i" class="stage-trim-row"><label><input class="stage-use" :data-i="i" type="checkbox" v-model="used[i]" @change="toggle(i)"> {{trims[i].name}}（{{trims[i].price_guide ?? '待核'}}万）</label><select class="stage-base" :aria-label="trims[i].name + '的比较基准'" :data-i="i" v-model="bases[i]" :disabled="!used[i] || !options(i).length"><option value="">基本配置</option><option v-for="j in options(i)" :value="j">{{trims[j].name}}</option></select></div></div>`});
    root.replaceChildren(); app.mount(root); current=app;
  }
  window.StageEditor={mount,plan:root=>root?.__stagePlan?.()||[]};
})();
