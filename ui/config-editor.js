/* Vue 3 configuration editor island. No network or build step at runtime. */
(() => {
  'use strict';
  const {createApp, ref, computed, watch} = Vue;
  const mounted = new Map();
  const absent = value => /^(✕|×|无|无配置|-|不适用)$/.test(value);
  const Cell = {
    props: ['value', 'no', 'sub', 'choices', 'parseSeatAdjust'],
    emits: ['change'],
    setup(props, {emit}) {
      const custom = ref(false);
      const value = computed(() => String(props.value ?? '✕'));
      let lastEmitted;
      const screenDraft = ref(null);
      const send = v => {lastEmitted=v;emit('change', v);};
      watch(()=>props.value,v=>{if(v!==lastEmitted)screenDraft.value=null;});
      const options = computed(() => [...new Set([value.value, ...(props.sub ? ['✕','●','[待定]'] : props.choices || [])])]);
      const label = v => v === '✕' ? '无' : v === '●' ? '有' : v;
      const choose = e => e.target.value === '__custom__' ? custom.value = true : send(e.target.value);
      const count = computed(() => (value.value.match(/\d+(?:\.\d+)?/) || [''])[0]);
      const simpleCount = computed(()=>/^[●]?\s*\d+(?:\.\d+)?\s*(?:km|扬声器|喇叭|个)?$/i.test(value.value));
      const screen = computed(() => {
        if(screenDraft.value) return screenDraft.value;
        const suffix=(value.value.match(/[（(]○[^()（）]*[)）]/g)||[]).join('');
        const standard=value.value.replace(/[（(]○[^()（）]*[)）]/g,'');
        const match = standard.match(/(\d+(?:\.\d+)?)\s*(?:英寸|吋|寸)/) || standard.match(/^[●○]?\s*(\d+(?:\.\d+)?)(?![\d.]|\s*[kK])/);
        const present=!!match || /中控|娱乐屏|副驾屏|仪表/.test(standard);
        return {state: value.value.includes('[待定]') ? 'pending' : absent(value.value) ? 'absent' : present ? value.value.startsWith('○') ? 'optional' : 'present' : 'pending', size:match?.[1] || '', lcd:standard.includes('全液晶'), suffix};
      });
      function screenChange(key, v) {
        const s = {...screen.value, [key]:v};
        screenDraft.value=s;
        const name=props.no === 29 ? (s.lcd ? '全液晶仪表' : '仪表') : props.no === 21 ? '中控屏' : '副驾娱乐屏';
        send(s.state === 'absent' ? '✕' : s.state === 'pending' ? '[待定]' : (!s.size && key==='lcd') ? (s.state==='optional'?'○':'')+name+s.suffix : !s.size || +s.size <= 0 || +s.size > 100 ? '[待定]屏幕尺寸未填写' : (s.state === 'optional' ? '○' : '') + Number(s.size) + '寸' + name + s.suffix);
      }
      const emptySeats = () => ['主驾','副驾'].map(name=>({name,count:null,mode:null}));
      const seatDetail = ref({seats:emptySeats(),editable:false,hint:'正在解析座椅配置…'});
      let seatRevision = 0;
      watch(()=>props.value,async () => {
        if(props.no!==35 || props.sub) return;
        const revision=++seatRevision;
        seatDetail.value={seats:emptySeats(),editable:false,hint:'正在解析座椅配置…'};
        try {
          const details=await props.parseSeatAdjust(value.value);
          if(revision!==seatRevision) return;
          if(!details.ok) throw new Error(details.error);
          seatDetail.value=details;
        } catch(error) {
          if(revision===seatRevision) seatDetail.value={seats:emptySeats(),editable:false,hint:'座椅配置未能解析，原文已保留；请自定义填写后核对。'};
        }
      },{immediate:true});
      const seats = computed(()=>seatDetail.value.seats);
      function seatChange(i, key, v) {
        if(!seatDetail.value.editable) return;
        const parts = seats.value.map(s => ({...s})); parts[i][key] = v;
        send((seatDetail.value.prefix || '') + parts.filter(s=>s.count || s.mode).map(s => s.name + (s.count ? s.count + '向' : '') + (s.mode || '')).join('+') + (seatDetail.value.suffix || ''));
      }
      const mirrorText = computed(()=>value.value.replace(/电动调节/g,'电调').replace(/电动折叠/g,'折叠'));
      const simpleMirror = computed(()=>absent(value.value) || /^(?:电调|折叠|加热)+$/.test(mirrorText.value.replace(/[●+\s]/g,'')));
      function mirrorChange(part, v) {
        const parts = ['电调','折叠','加热'].filter(p => p === part ? v === '●' : mirrorText.value.includes(p));
        send(parts.join('+') || '✕');
      }
      return {value, custom, options, label, choose, send, count, simpleCount, screen, screenChange, seats, seatDetail, seatChange, mirrorText, simpleMirror, mirrorChange, absent};
    },
    template: `
      <div class="ce-cell">
        <select v-if="sub" :value="value" class="ce-binary" :aria-label="sub" @change="send($event.target.value)"><option v-for="v in options" :key="v" :value="v">{{label(v)}}</option></select>
        <template v-else-if="[1,37].includes(no) && simpleCount">
          <input type="number" min="0" step="1" :aria-label="no===1?'纯电续航':'扬声器数量'" :value="count" @input="send($event.target.value ? $event.target.value+(no===1?'km':'扬声器') : '[待定]')">
          <span>{{no===1?'km':'个'}}</span>
        </template>
        <template v-else-if="[21,22,29].includes(no)">
          <select aria-label="屏幕状态" :value="screen.state" @change="screenChange('state',$event.target.value)"><option value="present">有</option><option value="absent">无配置</option><option value="pending">待定</option><option value="optional">选装</option></select>
          <input aria-label="屏幕尺寸" type="number" min="0.1" max="100" step="0.01" :value="screen.size" :disabled="['absent','pending'].includes(screen.state)" @input="screenChange('size',$event.target.value)"><span>英寸</span>
          <label v-if="no===29"><input type="checkbox" :checked="screen.lcd" :disabled="['absent','pending'].includes(screen.state)" @change="screenChange('lcd',$event.target.checked)">全液晶</label>
          <small v-if="screen.state==='pending' || screen.suffix || screen.state==='optional' || !screen.size">原文：{{value}}{{!screen.size && ['present','optional'].includes(screen.state)?'；尺寸未注明':''}}</small>
        </template>
        <template v-else-if="no===20 && simpleMirror">
          <label v-for="part in ['电调','折叠','加热']" :key="part">{{part}}<select class="ce-binary" :aria-label="part" :value="mirrorText.includes(part)?'●':'✕'" @change="mirrorChange(part,$event.target.value)"><option value="✕">无</option><option value="●">有</option></select></label>
        </template>
        <template v-else>
          <select v-if="choices && !custom" class="ce-main-choice" :value="value" aria-label="配置" @change="choose"><option v-for="v in options" :key="v" :value="v">{{label(v)}}</option><option value="__custom__">自定义填写…</option></select>
          <input v-else type="text" aria-label="配置自定义值" :value="value" @change="send($event.target.value.trim() || '✕')">
          <small v-if="[1,20,37].includes(no) && !absent(value)">保留原文；{{no===20?'分项未完整展开，请核对后选择配置。':'请核对后填写明确的数值和单位。'}}</small>
          <div v-if="no===35 && !absent(value)" class="ce-seat-adjust">
            <label v-for="(seat,i) in seats" :key="seat.name">{{seat.name}}<select :aria-label="seat.name+'调节方式'" :value="seat.mode || ''" :disabled="!seatDetail.editable" @change="seatChange(i,'mode',$event.target.value)"><option value="" disabled>待核</option><option>手调</option><option>电调</option></select><input type="number" min="2" max="30" step="1" placeholder="未注明" :aria-label="seat.name+'调节方向'" :value="seat.count" :disabled="!seatDetail.editable" @change="seatChange(i,'count',$event.target.value)">向</label>
          </div>
          <small v-if="no===35 && seatDetail.hint">{{seatDetail.hint}}</small>
        </template>
      </div>`
  };

  function mount(root, {model, kind, names = {}, choices, parseSeatAdjust, updateSnapshot, cascade, onChange, review = false}) {
    unmount(root);
    root.onchange = null; root.onfocusout = null;
    const app = createApp({
      components: {ConfigCell:Cell},
      setup() {
        const revision = ref(0);
        const cells = kind === 'snapshot' ? model.cells : model.items;
        const rows = computed(() => {
          revision.value;
          return [...cells].sort((a,b)=>(a.no===45?36.5:a.no)-(b.no===45?36.5:b.no)).flatMap(c => {
            if (c.merged_into) return [];
            if (c.no===36) {
              const rows = ['通风','加热','按摩','头枕音响'].map(f=>({cell:c,key:'36-'+f,name:'座椅'+f,subs:['主驾'+f,'副驾'+f]}));
              rows.push({cell:c,key:'36-rear',name:'座椅二排功能',rear:true,subs:['二排通风','二排加热','二排按摩','二排头枕音响']});
              const subs = kind==='snapshot' ? [...new Set(Object.values(c.values).flatMap(v=>v&&typeof v==='object'?Object.keys(v):[]))] : (c.subs||[]).map(s=>s.sub);
              return rows.concat(subs.filter(s=>!rows.some(r=>r.subs.includes(s))).map(s=>({cell:c,key:'36-'+s,name:'座椅功能 · '+s,sub:s})));
            }
            const subs = kind==='snapshot' ? [...new Set(Object.values(c.values).flatMap(v=>v&&typeof v==='object'?Object.keys(v):[]))] : (c.subs||[]).map(s=>s.sub);
            const name = names[c.no] || c.name || String(c.no);
            const detailRows=subs.map(s=>({cell:c,key:c.no+'-'+s,name:name+' · '+s,sub:s}));
            return kind==='snapshot' && subs.length ? detailRows : [{cell:c,key:String(c.no),name}, ...detailRows];
          });
        });
        function get(c,i,sub) {
          revision.value;
          if (kind==='snapshot') {const v=c.values[model.trims[i].name]; return sub ? v?.[sub] ?? (typeof v==='string' && v.includes('[待定]') ? v : '✕') : v ?? '✕';}
          return sub ? c.subs?.find(s=>s.sub===sub)?.values[i] ?? '✕' : c.values[i] ?? '✕';
        }
        function change(c,i,sub,value) {
          if(kind==='snapshot') updateSnapshot(model,c.no,model.trims[i].name,value,sub||'');
          else {
            let target=c;
            if(sub) {c.subs ||= []; target=c.subs.find(s=>s.sub===sub); if(!target) {target={sub,values:model.trims.map(()=> '✕')}; c.subs.push(target);}}
            const original=[...target.values], edited=[...original]; edited[i]=value;
            target.values=cascade(original,edited);
          }
          revision.value++; onChange();
        }
        function price(i,e) {
          const n=e.target.value===''?null:Number(e.target.value);
          if(n!==null&&(!Number.isFinite(n)||n<=0)) {e.target.setCustomValidity('指导价应为正数，单位万元');e.target.reportValidity();return;}
          e.target.setCustomValidity('');model.trims[i].price_guide=n;revision.value++;onChange();
        }
        function rename(i,e) {
          const trim=model.trims[i], old=trim.name, name=e.target.value.trim();
          if(!name || model.trims.some((t,j)=>j!==i && t.name===name)) {
            e.target.setCustomValidity('版型名称不能为空或重复');e.target.reportValidity();return;
          }
          e.target.setCustomValidity('');
          if(name===old)return;
          for(const c of cells) {
            c.values[name]=c.values[old];delete c.values[old];
            if(c.links) {
              if(old in c.links){c.links[name]=c.links[old];delete c.links[old];}
              for(const [child,link] of Object.entries(c.links)) {
                if(link===old)c.links[child]=name;
                else if(link&&typeof link==='object')for(const sub of Object.keys(link))if(link[sub]===old)link[sub]=name;
              }
            }
          }
          for(const t of model.trims)if(t.base===old)t.base=name;
          trim.name=name;revision.value++;onChange();
        }
        function metadata(t,key,value) {t[key]=value;revision.value++;onChange();}
        function priceSource(t) {
          const reference = t.price_reference == null ? '未写价格' : t.price_reference+'万元';
          if(t.price_source==='指导价') return `指导价来源：${reference}；${t.price_guide==null?'请核对后填写':'已填入，请核对'}。`;
          if(t.price_source==='TP价格') return `TP价格：${reference}，仅作参考；指导价请另填。`;
          return `原页价格：${reference}，口径未确定；请确认后填写指导价。`;
        }
        return {rows,trims:model.trims,kind,get,change,choices,parseSeatAdjust,price,review,rename,metadata,priceSource};
      },
      template: `<table class="grid ce-table"><thead><tr><th>#</th><th>配置项</th><th v-for="(t,i) in trims" :key="i">{{t.name}}</th><th v-if="review">依据</th></tr></thead><tbody>
        <tr v-if="review"><td class="no">—</td><td>版型名称</td><td v-for="(t,i) in trims" :key="i"><input type="text" aria-label="版型名称" :value="t.name" @change="rename(i,$event)"></td><td></td></tr>
        <tr v-if="kind==='snapshot'"><td class="no">—</td><td>指导价（万元）</td><td v-for="(t,i) in trims" :key="i"><input type="number" min="0.01" step="0.01" aria-label="指导价（万元）" :value="t.price_guide" @change="price(i,$event)"><small v-if="review && t.price_source">{{priceSource(t)}}</small></td><td v-if="review"></td></tr>
        <template v-if="review"><tr v-for="field in [{key:'mix',name:'占比'},{key:'range',name:'续航备注'}]" :key="field.key"><td class="no">—</td><td>{{field.name}}</td><td v-for="(t,i) in trims" :key="i"><input type="text" :aria-label="field.name" :value="t[field.key] || ''" @change="metadata(t,field.key,$event.target.value)"></td><td></td></tr></template>
        <tr v-for="(row,n) in rows" :key="row.key"><td class="no">{{n+1}}</td><td>{{row.name}}</td><td v-for="(t,i) in trims" :key="i">
          <div v-if="row.subs" class="ce-seat-functions" :class="{'ce-rear-functions':row.rear}"><label v-for="sub in row.subs" :key="sub">{{row.rear ? sub.slice(2) : sub.slice(0,2)}}<config-cell :no="row.cell.no" :sub="sub" :value="get(row.cell,i,sub)" @change="change(row.cell,i,sub,$event)"/></label></div>
          <config-cell v-else :no="row.cell.no" :sub="row.sub" :choices="choices(row.cell.no)" :parse-seat-adjust="parseSeatAdjust" :value="get(row.cell,i,row.sub)" @change="change(row.cell,i,row.sub,$event)"/>
        </td><td v-if="review"><input type="text" aria-label="配置依据" :value="row.cell.basis || ''" @change="metadata(row.cell,'basis',$event.target.value)"></td></tr></tbody></table>`
    });
    root.classList.add('vue-config-editor');
    app.mount(root); mounted.set(root,app);
  }
  function unmount(root) {
    mounted.get(root)?.unmount(); mounted.delete(root);
    root.classList.remove('vue-config-editor');
  }
  function validate(root) {return [...root.querySelectorAll('input')].every(input=>input.reportValidity());}
  window.ConfigEditor = {mount,unmount,validate,isMounted:root=>mounted.has(root)};
})();
