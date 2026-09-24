/* Vue 3 editor for the PPT draft columns. */
(() => {
  'use strict';
  const {createApp, ref, computed} = Vue;
  let app = null;
  function mount(root, model, {onChange, onInvalidate} = {}) {
    app?.unmount();
    app = createApp({
      setup() {
        const draft = ref(model);
        const columns = computed(() => draft.value.columns);
        const bases = i => columns.value.filter((c,j)=>j!==i && c.name);
        const changed = () => {onChange?.();onInvalidate?.();};
        const rename = (i,e) => {
          const next=e.target.value.trim(), col=columns.value[i], old=col.name;
          if(!next)return;
          if(columns.value.some((c,j)=>j!==i && c.name===next)){e.target.value=old;return;}
          col.name=next;
          columns.value.forEach(c=>{if(c.base===old)c.base=next;});
          changed();
        };
        const set = (i,key,value) => {columns.value[i][key]=value;changed();};
        const add = () => {columns.value.push({name:'',base:null,price:null,text:''});changed();};
        const remove = i => {
          if(columns.value.length===1){window.toast?.('至少保留一个版型','err');return;}
          const old=columns.value.splice(i,1)[0];columns.value.forEach(c=>{if(c.base===old.name)c.base=null;});changed();
        };
        return {columns,bases,rename,set,add,remove};
      },
      template:`<div class="ppt-draft-grid"><article v-for="(col,i) in columns" :key="i" class="ppt-column">
        <div class="ppt-column-head"><span class="ppt-column-index">版型 {{i+1}}</span><button v-if="columns.length>1" type="button" class="ppt-remove" @click="remove(i)">删除版型</button></div>
        <label>版型名称<input class="ppt-name" :value="col.name" @change="rename(i,$event)"></label>
        <label>比较基准<select class="ppt-base" :value="col.base||''" @change="set(i,'base',$event.target.value||null)"><option value="">独立基础配置</option><option v-for="base in bases(i)" :key="base.name" :value="base.name">{{base.name}}</option></select></label>
        <label>价格（万元）<input class="ppt-price" type="number" min="0" step="0.01" :value="col.price??''" @input="set(i,'price',$event.target.value)"></label>
        <label>配置内容（每行一项，也可稍后在完整表格填写）<textarea class="ppt-text" :value="col.text||''" @input="set(i,'text',$event.target.value)"></textarea></label>
      </article><button type="button" class="ppt-add-column" @click="add">＋ 添加版型</button></div>`
    });
    root.classList.add('vue-ppt-draft');
    app.mount(root);
  }
  function unmount(){app?.unmount();app=null;}
  window.PptDraftEditor={mount,unmount};
})();
