/* carkit 前端逻辑：pywebview js_api 调用 + 表格渲染 */
"use strict";

const ST = {
  checklist: null,
  ladder: null, ladderPath: "",
  snapshot: null, snapshotPath: "",
  valuation: null, valuationPath: "",
  diff: null,
  leftLadder: null, leftLadderPath: "",
  stage: {trims: [], seriesId: "", model: ""},
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function configurationChoices(no) {
  const base=['✕','[待定]','不适用'];
  const choices={
    3:['400V','800V'],
    4:Array.from({length:8},(_,i)=>i+16).flatMap(n=>[`R${n}钢轮毂`,`R${n}铝轮毂`]),
    7:['360影像','540影像'],9:['定速巡航','基础L2','高速NOA','城市NOA'],
    11:['●'],12:['手动前备箱','电动前备箱'],13:['●'],14:['●'],15:['●'],16:['●'],
    17:['卤素大灯','LED大灯'],18:['电动天窗','不可开启全景天窗','可开启全景天窗'],19:['●'],
    20:['电调','折叠','加热','电调+折叠','电调+加热','折叠+加热','电调+折叠+加热'],
    24:['●'],25:['塑料','仿皮','真皮','翻毛皮','NAPPA'],26:['手调','电调'],27:['●'],28:['●'],
    30:['HUD','AR-HUD','P-HUD'],31:['流媒体'],32:Array.from({length:10},(_,i)=>`USB/Type-C ${i+1}个`),
    33:['1个无线充电','2个无线充电'],39:['单色','多色'],40:['●'],41:['●'],
    5:[2,4,6,7,8,9,10,11,12].map(n=>`${n}气囊`),
    8:[1,2,3,4,5].map(n=>`${n}颗激光雷达`),
    35:['主驾手调+副驾手调','主驾6向电调+副驾4向手调','主驾6向电调+副驾4向电调','主驾8向电调+副驾4向电调','主驾10向电调+副驾6向电调'],
    38:[1,2,3,4].map(n=>`${n}车外扬声器`),
    6:['悬架软硬调节','悬架高低调节','悬架软硬+高低调节'],
    23:['4G','5G'],34:['织物','仿皮','真皮','翻毛皮','NAPPA真皮'],
    43:['●'],44:['●'],45:['主驾座椅记忆','副驾座椅记忆','前排座椅记忆'],
  };
  return choices[no]?base.concat(choices[no]):null;
}

function addConfigurationChoices(root, snapshotCells=null) {
  const seatCells=snapshotCells?root.querySelectorAll('input[data-cell][data-sub]'):root.matches('td[data-no="36"][data-sub]')?[root]:root.querySelectorAll('td[data-no="36"][data-sub]');
  seatCells.forEach(field=>{
    const no=snapshotCells?snapshotCells[+field.dataset.cell].no:+field.dataset.no;
    if(no!==36)return;
    const current=snapshotCells?field.value:field.textContent.trim();
    const container=snapshotCells?field.parentElement:field;
    if(!snapshotCells){field.contentEditable='false';field.textContent='';}
    const stored=snapshotCells?field:document.createElement('input');
    stored.hidden=true;stored.value=current;
    if(!snapshotCells){stored.dataset.configValue='true';container.append(stored);}
    const select=document.createElement('select');
    select.style.cssText='width:100%;min-width:105px';
    [...new Set([current,'✕','●','[待定]'])].forEach(value=>select.add(new Option(value==='✕'?'无配置':value==='●'?'有':value,value)));
    select.value=current;select.onchange=()=>{stored.value=select.value;container.classList.toggle('pending',select.value.includes('[待定]'));};
    container.prepend(select);
  });
  const fields=snapshotCells ? root.querySelectorAll('input[data-cell]') : root.matches('td[data-no]:not([data-sub])') ? [root] : root.querySelectorAll('td[data-no]:not([data-sub])');
  fields.forEach(field=>{
    const no=snapshotCells?snapshotCells[+field.dataset.cell].no:+field.dataset.no;
    if(!snapshotCells && field.querySelector('input[data-step]')) return;
    if(no===1 || no===37){
      const current=snapshotCells?field.value:field.textContent.trim();
      const container=snapshotCells?field.parentElement:field;
      const number=document.createElement('input'); number.type='number'; number.step='1'; number.min='0'; number.style.width='90%';
      const m=String(current).match(/\d+(?:\.\d+)?/); number.value=m?m[0]:'';
      const stored=snapshotCells?field:document.createElement('input'); stored.hidden=true; stored.value=current;
      if(!snapshotCells){field.contentEditable='false';field.textContent='';stored.dataset.configValue='true';container.append(stored);}
      number.oninput=()=>{stored.value=number.value+(no===1?'km':'扬声器');};
      container.prepend(number);
      return;
    }
    if([21,22,29].includes(no)){
      addScreenEditor(field,no,!!snapshotCells);
      return;
    }
    const options=configurationChoices(no);
    if(!options)return;
    const current=snapshotCells?field.value:field.textContent.trim();
    const container=snapshotCells?field.parentElement:field;
    if(!snapshotCells){field.contentEditable='false';field.textContent='';}
    const select=document.createElement('select');
    select.style.cssText='width:100%;min-width:190px';
    const values=[...new Set([current,...options])];
    values.forEach(value=>select.add(new Option(value==='✕'?'无配置':value==='●'?'有':value,value)));
    select.add(new Option('自定义填写…','__custom__'));
    const input=snapshotCells?field:document.createElement('input');
    input.value=current;input.hidden=true;
    if(!snapshotCells){input.dataset.configValue='true';container.append(input);}
    container.prepend(select);
    if(no===35){
      const editor=document.createElement('div');
      editor.innerHTML=['主驾','副驾'].map(seat=>`<label>${seat}<select data-seat-mode><option>手调</option><option>电调</option></select><input data-seat-count type="number" min="2" max="30" step="1" placeholder="总方向数" style="width:75px">向</label>`).join('');
      container.append(editor);
      ['主驾','副驾'].forEach((seat,i)=>{
        const match=current.match(new RegExp(seat+'(\\d+)向(手调|电调)'));
        if(match){editor.querySelectorAll('[data-seat-count]')[i].value=match[1];editor.querySelectorAll('[data-seat-mode]')[i].value=match[2];}
      });
      editor.onchange=()=>{
        const counts=[...editor.querySelectorAll('[data-seat-count]')];
        if(counts.some(x=>!x.value||!x.checkValidity()))return;
        input.value=['主驾','副驾'].map((s,i)=>s+counts[i].value+'向'+editor.querySelectorAll('[data-seat-mode]')[i].value).join('+');
        if(![...select.options].some(o=>o.value===input.value))select.add(new Option(input.value,input.value),0);
        select.value=input.value;input.hidden=true;
      };
    }
    select.onchange=()=>{
      input.hidden=select.value==='__custom__'?false:true;
      if(input.hidden)input.value=select.value;
      else input.focus();
      container.classList.remove('pending');
      if(input.value.includes('[待定]'))container.classList.add('pending');
    };
  });
}
function seatSubLabel(sub){
  const m=String(sub).match(/^(主驾|副驾|二排)(通风|加热|按摩|头枕音响)$/);
  return m?`座椅${m[2]} · ${m[1]}`:sub;
}
function configurationOrderKey(no){
  return Number(no)===45?36.5:Number(no);
}
function configurationDisplayOrder(items){
  return [...items].sort((a,b)=>configurationOrderKey(a.no)-configurationOrderKey(b.no));
}
function cascadeLadderValues(original,edited){
  const explicit=edited.map((value,i)=>value!==original[i]), result=[...original];
  explicit.forEach((changed,i)=>{
    if(!changed)return;
    result[i]=edited[i];
    for(let j=i+1;j<original.length&&original[j]===original[i];j++)if(!explicit[j])result[j]=edited[i];
  });
  return result;
}
function mirrorParts(value){
  const s=String(value||'');
  return ['电调','折叠','加热'].map(x=>s.includes(x));
}
function mirrorEditorCell(value, attrs){
  const parts=mirrorParts(value);
  return ['电调','折叠','加热'].map((name,i)=>`<label class="compact-choice">${name}<select data-mirror="${attrs}" data-mirror-part="${i}"><option value="✕" ${!parts[i]?'selected':''}>无</option><option value="●" ${parts[i]?'selected':''}>有</option></select></label>`).join('');
}
function addScreenEditor(field,no,isInput){
  const current=isInput?field.value:field.textContent.trim();
  const container=isInput?field.parentElement:field;
  if(!isInput){field.contentEditable='false';field.textContent='';}
  const stored=isInput?field:document.createElement('input');
  stored.hidden=true;stored.value=current;
  if(!isInput){stored.dataset.configValue='true';container.append(stored);}
  const editor=document.createElement('div');
  editor.className='screen-editor';
  editor.style.cssText='display:flex;align-items:center;gap:6px;flex-wrap:wrap';
  editor.innerHTML='<select aria-label="屏幕状态"><option value="present">有</option><option value="absent">无配置</option><option value="pending">待定</option><option value="optional">选装</option></select><input aria-label="屏幕尺寸（英寸）" type="number" min="0.1" max="100" step="0.01" placeholder="尺寸" style="width:85px"><span>英寸</span>'+(no===29?'<label><input type="checkbox">全液晶</label>':'');
  const state=editor.querySelector('select'), size=editor.querySelector('input[type=number]'), lcd=editor.querySelector('input[type=checkbox]');
  const match=current.match(/(\d+(?:\.\d+)?)\s*(?:英寸|吋|寸)/)||current.match(/^[●○]?\s*(\d+(?:\.\d+)?)(?![\d.]|\s*[kK])/);
  state.value=current.includes('[待定]')?'pending':/^(✕|×|无|无配置|-|不适用)$/.test(current)?'absent':match?(current.startsWith('○')?'optional':'present'):'pending';
  if(match)size.value=Number(match[1]);
  if(lcd)lcd.checked=current.includes('全液晶');
  const sync=()=>{
    size.disabled=['absent','pending'].includes(state.value);
    if(lcd)lcd.disabled=size.disabled;
    stored.value=state.value==='absent'?'✕':state.value==='pending'?'[待定]':!size.value||!size.checkValidity()?'[待定]屏幕尺寸未填写':(state.value==='optional'?'○':'')+Number(size.value)+'寸'+(no===29?(lcd.checked?'全液晶仪表':'仪表'):no===21?'中控屏':'副驾娱乐屏');
    container.classList.toggle('pending',stored.value.includes('[待定]'));
  };
  editor.oninput=sync;editor.onchange=sync;
  container.append(editor);
  // Preserve existing values (including optional alternatives) until actually edited.
  size.disabled=['absent','pending'].includes(state.value);
  if(lcd)lcd.disabled=size.disabled;
  if(state.value==='pending'&&!current.includes('[待定]'))stored.value='[待定]'+current;
}
function configurationCellValue(td){
  return td.querySelector('input[data-config-value]')?.value.trim() ?? td.textContent.trim();
}

function updateSnapshotValue(snap,no,name,value,sub=''){
  const cell=snap.cells.find(c=>c.no===no);
  if(!cell)return [];
  const get=n=>sub?(cell.values[n]||{})[sub]:cell.values[n];
  if(get(name)===value)return [];
  const links=cell.links||(cell.links={});
  if(sub&&links[name]&&typeof links[name]==='object')delete links[name][sub];
  else delete links[name];
  const changed=[],queue=[name],seen=new Set();
  while(queue.length){
    const current=queue.shift();
    if(seen.has(current))continue;
    seen.add(current);
    if(sub){
      if(!cell.values[current]||typeof cell.values[current]!=='object')cell.values[current]={};
      cell.values[current][sub]=value;
    }else cell.values[current]=value;
    changed.push(current);
    for(const [child,link] of Object.entries(links)){
      const parent=sub&&link&&typeof link==='object'?link[sub]:link;
      if(parent===current)queue.push(child);
    }
  }
  return changed;
}

// Compatibility boundary for older integrations that extract the linkage helper.
function bindSnapshotEditor() {}

function toast(msg, cls = "") {
  const el = document.createElement("div");
  el.className = "toast-item " + cls;
  el.textContent = msg;
  $("#toast").appendChild(el);
  setTimeout(() => el.remove(), cls === "err" ? 9000 : 4500);
}

async function api(method, ...args) {
  if (!window.pywebview || !window.pywebview.api) {
    toast("pywebview API 未就绪（浏览器直开无后端）", "err");
    throw new Error("api not ready");
  }
  try {
    const res = await window.pywebview.api[method](...args);
    if (res && typeof res === "object" && res.error && res.ok === undefined) {
      toast(res.error, "err");
      throw new Error(res.error);
    }
    if (res && res.ok === false) {
      toast(res.error || "操作失败", "err");
      throw new Error(res.error);
    }
    return res;
  } catch (e) {
    if (e.message !== "api not ready") toast(String(e.message || e), "err");
    throw e;
  }
}

/* ---------- 导航 ---------- */
const layout = $('#layout');
const sidebarCollapsed = localStorage.getItem('carkit.sidebarHidden') === '1';
if (sidebarCollapsed) layout.classList.add('sidebar-collapsed');
function setSidebarHidden(hidden) {
  layout.classList.toggle('sidebar-collapsed', hidden);
  localStorage.setItem('carkit.sidebarHidden', hidden ? '1' : '0');
  $('#sidebar-hide').setAttribute('aria-label', hidden ? '显示侧边栏' : '隐藏侧边栏');
}
$('#sidebar-hide').addEventListener('click', () => setSidebarHidden(true));
$('#sidebar-show').addEventListener('click', () => setSidebarHidden(false));
$$(".nav-item").forEach((btn) =>
  btn.addEventListener("click", () => {
    $$(".nav-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $$(".page").forEach((p) => p.classList.remove("active"));
    $("#page-" + btn.dataset.page).classList.add("active");
    if (btn.dataset.page === "diff") refreshDiffSelects();
    if (btn.dataset.page === "scrape") refreshRawList();
  })
);

/* ---------- ① 抓取 ---------- */
async function refreshRawList() {
  const records = await api("vehicle_history");
  ST.history = records;
  const list = $("#raw-list");
  list.innerHTML = records.length ? records.map((r,i) => `<li class="history-row"><div><strong>${esc(r.label)}</strong><div class="dim">${r.count} 个版型 · 可直接继续生成文档或用于对比</div></div><button data-history="${i}">继续生成阶梯</button><button data-delete-history="${i}">删除</button></li>`).join('') : '<li class="empty">还没有车型。抓取一次后，会自动保存在这里。</li>';
  list.querySelectorAll('[data-delete-history]').forEach(b=>b.onclick=async()=>{
    const r=records[+b.dataset.deleteHistory];
    if(!window.confirm(`删除历史记录「${r.label}」？\n原始数据移入回收站，已导出的文档保留。`))return;
    await api('remove_vehicle_history',r.file);
    ST.stage={trims:[],seriesId:'',model:''};
    $('#stage-trims').hidden=true;$('#md-preview').hidden=true;
    if($('#diff-vehicle').value===r.file){
      $('#diff-vehicle').value='';$('#diff-ladder').innerHTML='';
      ST.ladder=null;ST.ladderPath='';ST.diff=null;
      $('#diff-result').hidden=true;$('#diff-competitor-editor').hidden=true;
      $('#pairs-editor').querySelectorAll('.pair-row').forEach(row=>row.remove());
      $('#diff-status').textContent='竞品历史已删除，请重新选择';
    }
    await refreshRawList();await refreshDiffSelects();
    toast('历史记录已移入回收站','ok');
  });
  list.querySelectorAll('[data-history]').forEach(b => b.onclick = async () => handleStageResult(await api('open_history', records[+b.dataset.history].file)));
  $('#ladder-raw-select').innerHTML = records.map(r=>`<option value="${esc(r.file)}">${esc(r.label)}</option>`).join('');
}

$("#btn-scrape-open").addEventListener("click", async () => {
  const sid = $("#scrape-series").value.trim();
  if (!sid) return toast("请填写 seriesId 或 URL", "err");
  $("#scrape-status").textContent = "搜索和读取中…";
  $("#scrape-status").className = "status";
  const res = await api("stage_search", sid, "");
  handleStageResult(res);
});

$("#btn-scrape-capture").addEventListener("click", async () => {
  const res = await api("stage_continue");
  handleStageResult(res);
});

function handleStageResult(res) {
  if (res.filters) { renderCaptureFilters(res.filters); return; }
  if (res.candidates) {
    $("#stage-candidates").hidden = false;
    $("#stage-candidate-list").innerHTML = res.candidates.map(c => `<button class="candidate" data-sid="${c.id}">${esc(c.name)}（车系 ${c.id}）</button>`).join(" ");
    $$(".candidate").forEach(b => b.addEventListener("click", async () => handleStageResult(await api("stage_choose_series", b.dataset.sid))));
    $("#scrape-status").textContent = "请选择要抓取的车系";
    return;
  }
  if (res.needs_browser) { $("#scrape-status").textContent = "⚠ " + res.message; $("#scrape-status").className = "status warn"; return; }
  if (!res.ok) { $("#scrape-status").textContent = "✕ " + res.error; $("#scrape-status").className = "status err"; return; }
  $("#stage-candidates").hidden = true;
  $('#raw-inspector').hidden=true; $('#raw-inspector').replaceChildren(); $('#md-preview').hidden=true; $('#stage-export-status').textContent='';
  ST.stage = {trims: res.trims, seriesId: res.series_id, model: res.model};
  $("#scrape-status").textContent = `✓ 已读取 ${res.model}：${res.trims.length} 个版型、${res.rows} 行完整配置${res.raw_path ? `\n原始数据：${res.raw_path}` : ""}`;
  $("#scrape-status").className = "status ok";
  renderStageTrimEditor();
  refreshRawList();
}

function renderCaptureFilters(filters) {
  $('#stage-candidates').hidden = true;
  let panel = $('#capture-filters');
  if (!panel) { panel=document.createElement('div'); panel.id='capture-filters'; panel.className='card'; $('#stage-trims').before(panel); }
  panel.hidden=false;
  panel.innerHTML='<div class="capture-heading"><div><h2>选择抓取条件</h2><p>按需选择，可多选。未勾选的条件不作限制。</p></div><span class="capture-step">抓取前筛选</span></div>'+filters.map((f,i)=>`<fieldset class="capture-filter"><legend>${esc(f.label)}</legend><div class="capture-options">${f.values.map(v=>`<label class="capture-option"><input type="checkbox" data-filter="${i}" data-value="${esc(v.value)}"><span>${esc(v.label)}</span></label>`).join('')}</div></fieldset>`).join('')+'<div class="capture-actions"><button id="btn-confirm-capture" class="primary">开始抓取</button><span id="capture-filter-status" class="status" role="status" aria-live="polite"></span></div>';
  $('#btn-confirm-capture').onclick=async()=>{
    const selected={}; $$('#capture-filters [data-filter]:checked').forEach(x=>(selected[filters[+x.dataset.filter].label] ||= []).push(x.dataset.value));
    const button=$('#btn-confirm-capture'), status=$('#capture-filter-status');
    button.disabled=true; button.textContent='正在抓取…';
    status.className='status'; status.textContent='正在读取配置，请稍候';
    try {
      const result=await api('stage_apply_filters', selected);
      handleStageResult(result);
      status.textContent=result.needs_browser ? '请完成浏览器验证后继续' : '配置读取完成';
    } catch (error) {
      status.className='status err'; status.textContent=error.message || '抓取失败，请重试';
    } finally { button.disabled=false; button.textContent='开始抓取'; }
  };
}

function renderStageTrimEditor() {
  document.querySelector('#ladder-visual')?.remove();
  $("#stage-trims").hidden = false;
  const trims = ST.stage.trims;
  if(window.StageEditor) { StageEditor.mount($('#stage-trim-editor'), trims); return; }
  const price = t => {
    const m=String(t.price_guide ?? '').replace(/,/g,'').match(/\d+(?:\.\d+)?/);
    return m ? Number(m[0]) : Infinity;
  };
  const order = trims.map((_,i)=>i).sort((a,b)=>price(trims[a])-price(trims[b]) || a-b);
  $("#stage-trim-editor").innerHTML = order.map(i => `<div class="stage-trim-row"><label><input type="checkbox" class="stage-use" data-i="${i}" checked> ${esc(trims[i].name)}（${trims[i].price_guide ?? '待核'}万）</label><select class="stage-base" data-i="${i}"><option value="">基本配置</option></select></div>`).join("");
  $$(".stage-use").forEach(cb => cb.addEventListener('change', updateStageBases));
  updateStageBases(true);
}

function updateStageBases(reset=false) {
  const earlier=[];
  $$('.stage-use').forEach(cb => {
    const i=+cb.dataset.i, sel=document.querySelector(`.stage-base[data-i="${i}"]`), old=sel.value;
    sel.innerHTML='<option value="">基本配置</option>'+earlier.map(j=>`<option value="${j}">${esc(ST.stage.trims[j].name)}</option>`).join('');
    if (reset !== true && [...sel.options].some(o=>o.value===old)) sel.value=old;
    else sel.value=ST.stage.trims[i].price_guide != null && earlier.length ? String(earlier[earlier.length-1]) : '';
    sel.disabled=!cb.checked || !earlier.length;
    if(cb.checked) earlier.push(i);
  });
}

function stagePlan() {
  if(window.StageEditor && $('#stage-trim-editor').__stagePlan) return StageEditor.plan($('#stage-trim-editor'));
  const plan=[]; const selected=new Set($$(".stage-use:checked").map(x=>+x.dataset.i));
  $$(".stage-use").forEach(cb=>{const i=+cb.dataset.i;if(selected.has(i)){const sel=document.querySelector(`.stage-base[data-i="${i}"]`);plan.push({target:i,base:sel&&sel.value!==''?+sel.value:null});}});
  return plan;
}

const previewButton = document.createElement('button');
previewButton.textContent = '查看配置阶梯图';
previewButton.id = 'btn-stage-preview';
$('#btn-stage-export').before(previewButton);
previewButton.onclick = async () => {
  const res = await api('stage_preview', stagePlan());
  if (!res.ok) return toast(res.error, 'err');
  document.querySelector('#ladder-visual')?.remove();
  const panel = document.createElement('section');
  panel.id = 'ladder-visual';
  panel.innerHTML = `<div class="ladder-heading"><h2>配置阶梯</h2><button class="close-ladder">收起</button></div><p class="dim">指导价单位：万元 · 按上方所选比较基准显示；选装单列</p><div class="ladder-scroll"><div class="ladder-sheet"><h3 class="ladder-model">${esc(res.model)}</h3><div class="ladder-columns">${res.columns.map(c => `<article class="ladder-column"><h4>${esc(c.name)}</h4><div class="ladder-price">${c.price == null ? '待核' : Number(c.price).toFixed(2)}</div><strong>${c.base == null ? '基础配置：' : '相对 '+esc(c.base)+'：'}</strong><ul>${(c.items.length ? c.items : ['配置相同，仅价格/续航差异。']).map(x=>`<li>${esc(x)}</li>`).join('')}</ul>${c.options.length ? `<details><summary>选装配置</summary><ul>${c.options.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>` : ''}</article>`).join('')}</div></div></div>`;
  panel.querySelector('.ladder-heading h2').textContent = res.model + ' · 配置阶梯';
  panel.querySelector('.ladder-model').textContent = `${res.columns.length} 个版型 · 指导价与配置一览`;
  panel.querySelectorAll('.ladder-column').forEach((card, i) => {
    const c = res.columns[i];
    card.classList.toggle('is-base', c.base == null);
    const badge = document.createElement('span');
    badge.className = 'ladder-badge';
    badge.textContent = c.base == null ? '基础版型' : '差异配置';
    card.prepend(badge);
    const price = card.querySelector('.ladder-price');
    const unit = document.createElement('small');
    unit.textContent = c.price == null ? '指导价待核' : '万元';
    price.append(unit);
  });
  $('#stage-trims').append(panel);
  panel.querySelector('.close-ladder').onclick = () => panel.remove();
  panel.scrollIntoView({behavior:'smooth', block:'start', inline:'start'});
  panel.querySelector('.ladder-scroll').scrollLeft = 0;
};
$('#stage-trim-editor').addEventListener('change', () => document.querySelector('#ladder-visual')?.remove());

$("#btn-stage-export").addEventListener("click", async () => {
  const plan = stagePlan();
  const res=await api("stage_export",plan,ST.stage.model+'-配置阶梯',true);
  if (res.cancelled) return;
  $('#md-preview').hidden=false; $('#md-preview-text').textContent=res.md;
  $("#stage-export-status").textContent=res.ok?'✓ 已导出：'+res.path:'✕ '+res.error;
  $("#stage-export-status").className=res.ok?'status ok':'status err';
});

$("#btn-import-raw").addEventListener("click", async () => {
  const path = await api("open_file_dialog", ["原始数据 (*.json;*.html;*.htm)"]);
  if (!path || path.error) return;
  const res = await api("import_raw", path);
  if (res.ok) {
    $("#import-status").textContent =
      `✓ ${res.model || ""} ${res.trims.length} 版型 × ${res.rows} 行 → ${res.path}` +
      (res.lossy ? "（⚠ 旧版富结构，双子项有损）" : "");
    $("#import-status").className = "status ok";
    handleStageResult(await api("open_history", res.path.split(/[\\/]/).pop()));
    refreshRawList();
  }
});

/* ---------- ② 竞品阶梯 ---------- */
async function loadChecklist() {
  if (!ST.checklist) ST.checklist = await api("checklist");
  return ST.checklist;
}

$("#btn-build-ladder").addEventListener("click", async () => {
  const f = $("#ladder-raw-select").value;
  if (!f) return toast("先导入原始数据", "err");
  const path = await api("workdir_path", "raw", f);
  const m = f.match(/-(\d+)-/);
  const res = await api("build_ladder", path, $("#ladder-model").value, m ? m[1] : "");
  if (res.ok) {
    ST.ladder = res.ladder; ST.ladderPath = res.path;
    $("#ladder-info").textContent = `${res.ladder.model} · ${res.ladder.trims.length} 版型 · ${res.path}`;
    renderLadderTable();
    toast("阶梯已生成", "ok");
  }
});

$("#btn-load-ladder").addEventListener("click", async () => {
  const path = await api("open_file_dialog", ["阶梯 (*.json)"]);
  if (!path || path.error) return;
  const res = await api("load_ladder", path);
  if (res.ok) {
    ST.ladder = res.ladder; ST.ladderPath = path;
    $("#ladder-info").textContent = path;
    renderLadderTable();
  }
});

$("#btn-save-ladder").addEventListener("click", async () => {
  if (!ST.ladder || !ST.ladderPath) return toast("无阶梯数据", "err");
  collectLadderEdits();
  await api("save_ladder_edit", ST.ladderPath, ST.ladder);
  toast("已保存", "ok");
});

$("#btn-export-ladder-md").addEventListener("click", async () => {
  if (!ST.ladderPath) return toast("先生成/载入阶梯", "err");
  collectLadderEdits();
  await api("save_ladder_edit", ST.ladderPath, ST.ladder);
  const res = await api("build_ladder_md_only", ST.ladderPath).catch(() => null);
  toast(res && res.ok ? "md 已导出: " + res.path : "已保存 JSON（md 随生成时输出于同目录）");
});

function renderLadderTable(target="#ladder-table-wrap", lad=ST.ladder) {
  if (!lad) return;
  const wrap = $(target);
  if(window.ConfigEditor) {
    mountConfigurationEditor(wrap,lad,'ladder');
    return;
  }
  let html = '<table class="grid"><thead><tr><th>#</th><th>配置项</th>';
  html += lad.trims.map((t) => `<th>${t.name}<br><span class="dim">${t.price_guide ?? ""}万</span></th>`).join("");
  html += "</tr></thead><tbody>";
  for (const [rowIndex,it] of configurationDisplayOrder(lad.items).entries()) {
    const serial=rowIndex+1;
    if(it.no===36){
      const bySub=Object.fromEntries((it.subs||[]).map(sr=>[sr.sub,sr.values]));
      ['通风','加热','按摩','头枕音响'].forEach(feature=>{
        html+=`</tr><tr><td class="no">${serial}</td><td>座椅${feature}</td>`;
        html+=it.values.map((_,i)=>{
          const main=(bySub['主驾'+feature]||[])[i]||'✕',副=(bySub['副驾'+feature]||[])[i]||'✕';
          return `<td data-no="36" data-i="${i}" data-seat-cell><label>主驾<select data-seat="主驾${feature}"><option value="✕" ${main==='✕'?'selected':''}>无</option><option value="●" ${main==='●'?'selected':''}>有</option></select></label><label>副驾<select data-seat="副驾${feature}"><option value="✕" ${副==='✕'?'selected':''}>无</option><option value="●" ${副==='●'?'selected':''}>有</option></select></label></td>`;
        }).join('');
      });
      html+=`</tr>`;
      continue;
    }
    if(it.no===20){
      html += `<tr><td class="no">${serial}</td><td>${it.name}</td>`;
      html += it.values.map((v,i)=>`<td data-no="20" data-i="${i}" data-mirror-cell>${mirrorEditorCell(v,`${i}`)}</td>`).join('');
      html += '</tr>'; continue;
    }
    html += `<tr><td class="no">${serial}</td><td>${it.name}${it.unmapped ? ' <span class="tag warn">待映射</span>' : ""}</td>`;
    html += it.values.map((v, i) =>
      it.no===1 || it.no===37
        ? `<td data-no="${it.no}" data-i="${i}" class="${cellCls(v)}"><input data-step type="number" min="0" step="1" value="${(String(v).match(/\d+(?:\.\d+)?/)||[''])[0]}"></td>`
        : `<td contenteditable data-no="${it.no}" data-i="${i}" class="${cellCls(v)}">${esc(v)}</td>`).join("");
    html += "</tr>";
    for (const sr of it.subs || []) {
      html += `<tr><td class="no">—</td><td class="dim">${seatSubLabel(sr.sub)}</td>`;
      html += sr.values.map((v, i) =>
        `<td contenteditable data-no="${it.no}" data-sub="${sr.sub}" data-i="${i}" class="${cellCls(v)}">${esc(v)}</td>`).join("");
      html += "</tr>";
    }
  }
  html += "</tbody></table>";
  wrap.innerHTML = html;
  addConfigurationChoices(wrap);
  wrap.onchange=event=>{
    if(event.target.value==='__custom__')return;
    collectLadderEdits(target,lad); renderLadderTable(target,lad);
  };
  wrap.onfocusout=event=>{
    const cell=event.target.closest('td[data-no]');
    if(cell&&(cell.contentEditable==='true'||event.target.dataset.configValue)){
      collectLadderEdits(target,lad); renderLadderTable(target,lad);
    }
  };
}

function collectLadderEdits(target="#ladder-table-wrap", ladder=ST.ladder) {
  if (!ladder) return;
  if(ConfigEditor.isMounted($(target))) return;
  const originals=new Map(ladder.items.map(it=>[it.no,{values:[...it.values],subs:Object.fromEntries((it.subs||[]).map(sr=>[sr.sub,[...sr.values]]))}]));
  $$(target+" td[data-no]").forEach((td) => {
    const no = +td.dataset.no, i = +td.dataset.i;
    const it = ladder.items.find((x) => x.no === no);
    if (!it) return;
    if (td.dataset.seatCell) {
      td.querySelectorAll('select[data-seat]').forEach(select=>{
        const sr=(it.subs||[]).find(s=>s.sub===select.dataset.seat); if(sr)sr.values[i]=select.value||'✕';
      });
    } else if (td.querySelector('input[data-step]')) {
      const raw=td.querySelector('input[data-step]').value;
      it.values[i]=raw+(no===1?'km':'扬声器');
    } else if (td.dataset.mirrorCell) {
      it.values[i] = ['电调','折叠','加热'].filter((_,p)=>td.querySelector(`select[data-mirror-part="${p}"]`)?.value==='●').join('+') || '✕';
    } else if (td.dataset.sub) {
      const sr = (it.subs || []).find((s) => s.sub === td.dataset.sub);
      if (sr) sr.values[i] = configurationCellValue(td);
    } else {
      it.values[i] = configurationCellValue(td);
    }
  });
  ladder.items.forEach(it=>{
    const old=originals.get(it.no); if(!old)return;
    it.values=cascadeLadderValues(old.values,it.values);
    (it.subs||[]).forEach(sr=>{if(old.subs[sr.sub])sr.values=cascadeLadderValues(old.subs[sr.sub],sr.values);});
  });
}

function cellCls(v) {
  const s = String(v);
  if (s.includes("✕")) return "absent";
  if (s.includes("[待定]") || s.includes("待映射") || s.includes("待赋值")) return "pending";
  return "";
}
const esc = (s) => String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");

/* ---------- ③ 快照 ---------- */
$("#btn-new-snapshot").addEventListener("click", async () => {
  const model = prompt("自产品车型代号（如 T19NG）：");
  if (!model) return;
  const trims = [];
  while (true) {
    const name = prompt(`版型 ${trims.length + 1} 名称（留空结束）：`);
    if (!name) break;
    const price = parseFloat(prompt(`${name} 指导价（万元）：`) || "NaN");
    trims.push({ name, price_guide: isNaN(price) ? null : price });
  }
  if (!trims.length) return toast("至少一个版型", "err");
  const res = await api("new_snapshot", model, trims);
  if (res.ok) {
    ST.snapshot = res.snapshot; ST.snapshotPath = res.path;
    $("#snapshot-info").textContent = res.path;
    renderSnapshot();
    toast("快照已创建，请逐项填写", "ok");
  }
});

$("#btn-load-snapshot").addEventListener("click", async () => {
  const path = await api("open_file_dialog", ["快照 (*.json)"]);
  if (!path || path.error) return;
  const res = await api("load_snapshot", path);
  if (res.ok) {
    ST.snapshot = res.snapshot; ST.snapshotPath = path;
    $("#snapshot-info").textContent = `${res.snapshot.model} ${res.snapshot.version} · ${path}`;
    renderSnapshot();
  }
});

$("#btn-save-snapshot").addEventListener("click", async () => {
  if (ST.snapshot && ST.snapshot.status === "待确认") return toast("请在PPT导入区核对并确认保存", "err");
  if (!ST.snapshot || !ST.snapshotPath) return toast("无快照数据", "err");
  if(!collectSnapshotEdits())return;
  await api("save_snapshot", ST.snapshotPath, ST.snapshot);
  toast("快照已保存", "ok");
});

async function renderSnapshot() {
  const snap = ST.snapshot;
  if (!snap) return;
  const cl = await loadChecklist();
  const items = cl.items.filter((it) => !it.merged_into);
  // Fill missing checklist entries so imported drafts remain fully reviewable.
  for(const item of items) if(!snap.cells.some(c=>c.no===item.no)) {
    snap.cells.push({no:item.no,values:Object.fromEntries(snap.trims.map(t=>[t.name,'[待定]'])),basis:''});
  }
  $('#snapshot-trims').replaceChildren();
  mountConfigurationEditor($('#snapshot-table-wrap'),snap,'snapshot',Object.fromEntries(items.map(it=>[it.no,it.name])),true);
}

function collectSnapshotEdits() {
  return ConfigEditor.validate($('#snapshot-table-wrap'));
}

/* ---------- ④ 赋值表 ---------- */
let valuationEditorSchema = {};

$("#diff-toggle-valuation").addEventListener("click", async () => {
  showPage('valuation');
  await loadCurrentValuation();
});
$("#diff-close-valuation").addEventListener("click", async () => {
  showPage('diff');
  await refreshDiffSelects();
});

async function loadCurrentValuation(force=false) {
  if (ST.valuation && !force) return renderValuation();
  const res = await api("current_valuation");
  if (!res.ok) return;
  ST.valuation = res.valuation;
  ST.valuationPath = res.path;
  valuationEditorSchema = res.editor_schema || {};
  $("#valuation-info").textContent = res.customized ? "当前使用：已保存的自定义规则" : "当前使用：内置默认规则";
  await renderValuation();
}

$("#btn-make-template").addEventListener("click", async () => {
  if (ST.valuation) {
    if (!collectValuationEdits()) return;
    const saved = await api("save_current_valuation", ST.valuation);
    if (!saved.ok) return;
    ST.valuation = saved.valuation;
  }
  const res = await api("make_valuation_template");
  if (res.ok) toast("当前规则 Excel 已生成：\n" + res.path, "ok");
});

$("#btn-load-valuation").addEventListener("click", async () => {
  const path = await api("open_file_dialog", ["赋值表 (*.xlsx;*.json)"]);
  if (!path || path.error) return;
  const res = await api("load_valuation", path);
  if (res.ok) {
    ST.valuation = res.valuation;
    valuationEditorSchema = res.editor_schema || valuationEditorSchema;
    $("#valuation-info").textContent = "已导入，点击“保存并立即应用”后生效：" + path;
    renderValuation();
  }
});

$("#btn-save-valuation").addEventListener("click", async () => {
  if (!ST.valuation) return toast("赋值规则尚未载入", "err");
  if (!collectValuationEdits()) return;
  const res = await api("save_current_valuation", ST.valuation);
  if (!res.ok) return;
  ST.valuation = res.valuation;
  ST.valuationPath = res.path;
  $("#valuation-info").textContent = "已保存；后续对比默认使用此规则";
  await refreshDiffSelects();
  toast("赋值规则已保存并立即生效", "ok");
});

$("#btn-reset-valuation").addEventListener("click", async () => {
  if (!window.confirm("恢复所有内置默认赋值？已保存的自定义规则将被移除。")) return;
  const res = await api("reset_current_valuation");
  if (!res.ok) return;
  ST.valuation = res.valuation;
  valuationEditorSchema = res.editor_schema || {};
  $("#valuation-info").textContent = "已恢复内置默认规则";
  await renderValuation();
  toast("已恢复内置默认赋值", "ok");
});

async function renderValuation() {
  const v = ST.valuation;
  if (!v) return;
  const cl = await loadChecklist();
  const nameByNo = {};
  for (const it of cl.items) nameByNo[it.no] = it.md_name || it.name;
  const byNo = {};
  for (const it of v.items) byNo[it.no] = it;
  ValuationEditor.mount($("#valuation-table-wrap"), v, valuationEditorSchema, nameByNo);
}

function collectValuationEdits() {
  if (!ST.valuation) return false;
  if(!ValuationEditor.validate($("#valuation-table-wrap"))) {
    toast('请填写大于等于0的有效数字', 'err');
    return false;
  }
  return true;
}

/* ---------- ⑤ 对比 ---------- */
async function refreshDiffSelects() {
  const [snaps, lads, vals] = await Promise.all([
    api("list_files", "快照"), api("list_files", "阶梯"), api("list_files", "赋值"),
  ]);
  fillSelect("#diff-snapshot", snaps.filter(f=>f.endsWith('.json')));
  fillSelect("#diff-valuation", vals.filter(f=>(f.endsWith('.json') || f.endsWith('.xlsx')) && f !== '当前赋值规则.json'), "当前已保存赋值规则（默认）");
  const history = await api('vehicle_history');
  const sel = $('#diff-vehicle'); const previous = sel.value;
  sel.innerHTML = '<option value="">请选择已抓取的竞品</option>'+history.map(r=>`<option value="${esc(r.file)}">${esc(r.label)}</option>`).join('');
  if ([...sel.options].some(o=>o.value===previous)) sel.value=previous;
  const left=$('#diff-left-vehicle'), oldLeft=left.value;
  left.innerHTML=sel.innerHTML;
  if([...left.options].some(o=>o.value===oldLeft)) left.value=oldLeft;
  if(sel.value) await selectCompetitor();
}
function fillSelect(sel, files, placeholder) {
  const el = $(sel);
  const previous = el.value;
  el.innerHTML = (placeholder ? `<option value="">${placeholder}</option>` : "") +
    files.map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join("");
  if([...el.options].some(o=>o.value===previous)) el.value=previous;
}

$("#diff-snapshot").addEventListener("change", rebuildPairs);
$('#diff-left-vehicle').addEventListener('change', async()=>{ $('#diff-result').hidden=true; ST.diff=null; await rebuildPairs(); });
$('#diff-mode').addEventListener('change', async()=>{
  const competitor=$('#diff-mode').value==='competitor';
  $('#diff-left-vehicle').hidden=!competitor; $('#diff-snapshot').hidden=competitor;
  $('#delete-self-file').hidden=competitor;
  $('#diff-edit-self').textContent=competitor?'修改左侧竞品配置':'修改当前本品配置';
  $('#diff-save-self').textContent=competitor?'保存左侧竞品修正':'保存本品修正';
  hideComparisonEditors(); $('#diff-result').hidden=true; ST.diff=null;
  await rebuildPairs();
});
$("#diff-ladder").addEventListener("change", rebuildPairs);
$('#diff-valuation').addEventListener('change',()=>{ST.diff=null;$('#diff-result').hidden=true;});

async function rebuildPairs() {
  ST.diff=null;
  $('#diff-result').hidden=true;
  const box = $("#pairs-editor");
  box.querySelectorAll(".pair-row").forEach((r) => r.remove());
  const competitor=$('#diff-mode').value==='competitor';
  const [sn, ld] = [competitor ? $('#diff-left-vehicle').value : $("#diff-snapshot").value, $("#diff-ladder").value];
  if (!sn || !ld) return;
  const sp = await api("workdir_path", "快照", sn);
  const lp = await api("workdir_path", "阶梯", ld);
  const [sres, lres] = [competitor ? await api('prepare_competitor',sn) : await api("load_snapshot", sp), await api("load_ladder", lp)];
  const st = (competitor ? sres.ladder : sres.snapshot).trims.map((t) => t.name);
  const ct = lres.ladder.trims.map((t) => t.name);
  box.dataset.selfTrims = JSON.stringify(st);
  box.dataset.compTrims = JSON.stringify(ct);
  addPairRow(st, ct);
}

$("#btn-add-pair").addEventListener("click", () => {
  ST.diff=null;
  $('#diff-result').hidden=true;
  const box = $("#pairs-editor");
  addPairRow(JSON.parse(box.dataset.selfTrims || "[]"), JSON.parse(box.dataset.compTrims || "[]"));
});

function addPairRow(st, ct) {
  const row = document.createElement("div");
  row.className = "pair-row";
  row.innerHTML = `
    <select class="pair-self">${st.map((t) => `<option>${t}</option>`).join("")}</select>
    <span class="dim">VS</span>
    <select class="pair-comp">${ct.map((t) => `<option>${t}</option>`).join("")}</select>
    <button class="pair-del">✕</button>`;
  row.querySelector(".pair-del").addEventListener("click", () => {row.remove();ST.diff=null;$('#diff-result').hidden=true;});
  row.addEventListener('change',()=>{ST.diff=null;$('#diff-result').hidden=true;});
  $("#pairs-editor").appendChild(row);
}

$("#btn-run-diff").addEventListener("click", async () => {
  const competitor=$('#diff-mode').value==='competitor';
  const sn = competitor ? $('#diff-left-vehicle').value : $("#diff-snapshot").value, ld = $("#diff-ladder").value;
  if (!sn || !ld) return toast("请先选择快照与竞品阶梯", "err");
  const pairs = $$("#pairs-editor .pair-row").map((r) => ({
    self_trim: r.querySelector(".pair-self").value,
    comp_trim: r.querySelector(".pair-comp").value,
  }));
  if (!pairs.length) return toast("请至少指定一组版型配对（铁律：人工指定）", "err");
  const sp = competitor ? (await api('prepare_competitor',sn)).path : await api("workdir_path", "快照", sn);
  const lp = await api("workdir_path", "阶梯", ld);
  const vv = $("#diff-valuation").value;
  const vp = vv ? await api("workdir_path", "赋值", vv) : "";
  $("#diff-status").textContent = "计算中…";
  const res = await api("run_diff", sp, lp, pairs, vp, competitor);
  if (res.ok) {
    ST.diff = res;
    $("#diff-status").textContent = "✓ 结果已生成: " + res.md_path +
      (res.missing_valuation.length ? `\n⚠ [待赋值] 项: ${res.missing_valuation.join(", ")} —— 请补赋值表，程序不脑补` : "");
    $("#diff-status").className = "status ok";
    renderDiff(res);
  } else {
    $("#diff-status").textContent = "✕ " + res.error;
    $("#diff-status").className = "status err";
  }
});

function renderDiff(res) {
  $("#diff-result").hidden = false;
  const groups = res.groups;
  // P21 layout: each manually paired comparison is a column; metrics are rows.
  let h = '<table class="grid backup-table"><thead><tr><th class="backup-label"></th>';
  h += groups.map((g) =>
    `<th>${esc(g.pair.self_trim)} ${fmtP(g.self_price)}<br><span class="dim">VS</span><br>${esc(g.pair.comp_trim)} ${fmtP(g.comp_price)}</th>`).join("") + "</tr></thead><tbody>";
  h += "<tr><th class=\"backup-label\">版型</th>" + groups.map((g) =>
    `<td>${esc(g.pair.self_trim)} vs ${esc(g.pair.comp_trim)}</td>`).join("") + "</tr>";
  h += `<tr><th class="backup-label">${esc(res.self_model || "本品")}多</th>` + groups.map((g) =>
    `<td class="v-more">${g.more.length ? g.more.map(esc).join("<br>") : "—"}</td>`).join("") + "</tr>";
  h += `<tr><th class="backup-label">${esc(res.self_model || "本品")}少</th>` + groups.map((g) =>
    `<td class="v-less">${g.less.length ? g.less.map(esc).join("<br>") : "—"}</td>`).join("") + "</tr>";
  const money = (k, label) =>
    `<tr><th class="backup-label">${label}</th>` + groups.map((g) => {
      const v = (g.valuation || {})[k];
      const reason = k==='overall' ? '综合竞争力公式尚未设置' : k==='flat_adv' && (g.self_price==null || g.comp_price==null) ? '缺少本品或竞品指导价' : '缺少赋值规则';
      return `<td>${v == null ? `<span class="dim">${reason}</span>` : v}</td>`;
    }).join("") + "</tr>";
  h += money("config_adv", "配置优势") + money("flat_adv", "拉平指导价优势") + money("overall", "综合竞争力[待公式]");
  h += "</tbody></table>";
  $("#backup-table").innerHTML = h;
  $("#backup-table").innerHTML += groups.map(g=>{
    const v=g.valuation||{};
    return `<details open><summary>赋值计算明细：${esc(g.pair.self_trim)} vs ${esc(g.pair.comp_trim)}</summary><p>配置优势＝多配置合计 ${v.total_more??'?'} − 少配置合计 ${v.total_less??'?'} ＝ ${v.config_adv??'?'} 元</p><p>拉平指导价优势＝配置优势＋（竞品指导价−本品指导价）×10000</p><table class="grid"><tr><th>配置差异</th><th>计价依据</th><th>金额（元）</th></tr>${(v.detail||[]).map(x=>`<tr><td>${esc(x.side)}：${esc(x.display||String(x.no))}</td><td>${esc(x.rule||'')}</td><td>${x.amount>0?'+':''}${x.amount}</td></tr>`).join('')}</table></details>`;
  }).join('');
  // 判定明细
  const nos = [...new Set(res.cells.map((c) => c.no))].sort((a, b) => configurationOrderKey(a) - configurationOrderKey(b));
  const nameByNo = {};
  res.cells.forEach((c) => (nameByNo[c.no] = c.name));
  let d = '<table class="grid"><thead><tr><th>#</th><th>配置项</th>';
  d += groups.map((g) => `<th>${g.pair.self_trim}vs${g.pair.comp_trim}</th>`).join("") + "</tr></thead><tbody>";
  for (const [rowIndex,no] of nos.entries()) {
    d += `<tr><td class="no">${rowIndex+1}</td><td>${nameByNo[no]}</td>`;
    for (let pi = 0; pi < groups.length; pi++) {
      const c = res.cells.find((x) => x.no === no && x.pair === pi);
      if (!c) { d += "<td></td>"; continue; }
      const cls = { "多": "v-more", "少": "v-less", "同": "v-same", "豁免": "v-exempt", "不计": "v-na" }[c.verdict] || "";
      d += `<td class="${cls}">${esc(c.display)}</td>`;
    }
    d += "</tr>";
  }
  d += "</tbody></table>";
  $("#detail-table").innerHTML = d;
}

const fmtP = (p) => (p == null ? "?" : p);

$("#btn-export-result").addEventListener("click", async () => {
  if (!ST.diff) return toast("先运行对比", "err");
  const filename = `竞争力对比-${ST.diff.self_model||'本品'}vs${ST.diff.comp_model||'竞品'}`.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_')+'.md';
  const dest = await api("save_file_dialog", filename, ["Markdown (*.md)"]);
  if (!dest || dest.error) return;
  await api("write_text_file", dest, ST.diff.md);
  toast("已导出: " + dest, "ok");
});

/* ---------- ⑥ 设置 ---------- */
async function initSettings() {
  const p = await api("ping");
  $("#rules-version").textContent = "规则 " + p.rules;
  $("#workdir-label").textContent = p.workdir;
  $("#set-workdir").textContent = p.workdir;
  $("#set-rules").textContent = p.rules + "（engine/rules/，可热更新）";
}
$("#btn-check-browser").addEventListener("click", async () => {
  const r = await api("scrape_status");
  $("#set-browser").textContent = r.available
    ? `✓ 可用：${r.channel || r.browser || ""}`
    : `✕ ${r.error || "未检测到"}`;
});

/* ---------- init ---------- */
window.addEventListener("pywebviewready", async () => {
  await initSettings();
  await loadChecklist();
  refreshRawList();
});
// 浏览器直开（无 pywebview）时给提示
setTimeout(() => {
  if (!window.pywebview) $("#scrape-status").textContent = "（浏览器直开模式：无后端，仅供预览界面）";
}, 1500);


function showPage(name) {
  $$('.page').forEach(p=>p.classList.toggle('active',p.id==='page-'+name));
  const navName=name==='valuation'?'diff':name;
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===navName));
}
async function selectCompetitor() {
  $('#diff-ladder').innerHTML='';
  $('#pairs-editor').querySelectorAll('.pair-row').forEach(r=>r.remove());
  const filename=$('#diff-vehicle').value;
  if(!filename) return;
  const result=await api('prepare_competitor',filename);
  if($('#diff-vehicle').value!==filename) return;
  ST.ladder=result.ladder; ST.ladderPath=result.path;
  const file=result.path.split(/[\\/]/).pop();
  $('#diff-ladder').innerHTML=`<option value="${esc(file)}">${esc(result.ladder.model)}</option>`;
  await rebuildPairs();
}
$('#diff-vehicle').addEventListener('change',()=>{
  ConfigEditor.unmount($('#diff-ladder-table-wrap'));
  $('#diff-competitor-editor').hidden=true;
  $('#diff-ladder-table-wrap').innerHTML='';
  selectCompetitor();
});
// Keep both editors inside the comparison workflow.
$('#pairs-editor').before($('#diff-competitor-editor'));
$('#review-competitor').textContent='修改当前竞品配置';
$('#diff-competitor-editor h3').textContent='修改竞品配置';
let comparisonSelf=null, comparisonSelfPath='';
function mountConfigurationEditor(root,model,kind,names={},review=false) {
  ConfigEditor.mount(root,{model,kind,names,review,choices:configurationChoices,
    updateSnapshot:updateSnapshotValue,cascade:cascadeLadderValues,
    onChange:()=>{ST.diff=null;$('#diff-result').hidden=true;}});
}
function hideComparisonEditors() {
  ConfigEditor.unmount($('#diff-self-table'));
  ConfigEditor.unmount($('#diff-ladder-table-wrap'));
  $('#diff-self-editor').hidden = true;
  $('#diff-competitor-editor').hidden = true;
  $('#diff-self-table').innerHTML = '';
  $('#diff-ladder-table-wrap').innerHTML = '';
}
$('#delete-self-file').onclick=async()=>{
  const file=$('#diff-snapshot').value;
  if(!file)return toast('请先选择要删除的本品文件','err');
  if(!window.confirm(`删除本品配置「${file}」？\n文件将移入工作目录的回收站，原始PPT不受影响。`))return;
  await api('remove_imported_snapshot',file);
  comparisonSelf=null;comparisonSelfPath='';
  ST.snapshot=null;ST.snapshotPath='';ST.diff=null;
  ConfigEditor.unmount($('#snapshot-table-wrap'));
  $('#diff-self-editor').hidden=true;$('#diff-result').hidden=true;
  $('#snapshot-table-wrap').innerHTML='';$('#snapshot-trims').innerHTML='';$('#snapshot-info').textContent='';
  $('#diff-status').textContent='已移入回收站';
  await refreshDiffSelects();await rebuildPairs();
  toast('已删除；可在工作目录的回收站找回','ok');
};
$('#diff-snapshot').addEventListener('change',()=>{
  ConfigEditor.unmount($('#diff-self-table'));
  $('#diff-self-editor').hidden=true; comparisonSelf=null;
});
$('#diff-edit-self').onclick=async()=>{
  const competitor=$('#diff-mode').value==='competitor';
  hideComparisonEditors();
  if(competitor){
    const file=$('#diff-left-vehicle').value;
    if(!file)return toast('请先选择左侧竞品','err');
    const r=await api('prepare_competitor',file);
    if(!r || r.error)return toast(r?.error||'竞品配置读取失败','err');
    ST.leftLadder=r.ladder; ST.leftLadderPath=r.path;
    $('#diff-self-editor h3').textContent='修改左侧竞品配置';
    $('#diff-self-editor p').textContent='仅修改本次对比使用的竞品配置，不影响原始抓取记录。';
    renderLadderTable('#diff-self-table',ST.leftLadder);
    $('#diff-self-editor').hidden=false;
    return;
  }
  const file=$('#diff-snapshot').value;
  if(!file)return toast('请先选择本品配置','err');
  comparisonSelfPath=await api('workdir_path','快照',file);
  const r=await api('load_snapshot',comparisonSelfPath);
  comparisonSelf=r.snapshot;
  $('#diff-self-editor h3').textContent='修改本品配置';
  $('#diff-self-editor p').textContent='修改会同步到继承该项的版型，保存后重新对比。';
  const checklist=await loadChecklist();
  mountConfigurationEditor($('#diff-self-table'),comparisonSelf,'snapshot',Object.fromEntries(checklist.items.map(x=>[x.no,x.name])));
  $('#diff-self-editor').hidden=false;
};
$('#diff-save-self').onclick=async()=>{
  if(!ConfigEditor.validate($('#diff-self-table'))) return;
  if($('#diff-mode').value==='competitor'){
    if(!ST.leftLadder||!ST.leftLadderPath)return toast('请先选择左侧竞品','err');
    collectLadderEdits('#diff-self-table',ST.leftLadder);
    const r=await api('save_ladder_edit',ST.leftLadderPath,ST.leftLadder);
    if(r&&r.ok){$('#diff-result').hidden=true;ST.diff=null;await rebuildPairs();toast('左侧竞品修正已保存，请运行对比','ok');}
    return;
  }
  if(!comparisonSelf)return;
  await api('save_snapshot',comparisonSelfPath,comparisonSelf);
  $('#diff-result').hidden=true; ST.diff=null;
  toast('本品修正已保存，请运行对比','ok');
};
$('#review-competitor').onclick=()=>{
  if(!ST.ladder || !$('#diff-ladder').value) return toast('请先选择竞品');
  ConfigEditor.unmount($('#diff-self-table'));
  $('#diff-self-editor').hidden=true;
  $('#diff-self-table').innerHTML='';
  const panel=$('#diff-competitor-editor'); panel.hidden=!panel.hidden;
  if(!panel.hidden) renderLadderTable('#diff-ladder-table-wrap');
};
$('#diff-save-competitor').onclick=async()=>{
  if(!ConfigEditor.validate($('#diff-ladder-table-wrap'))) return;
  if(!ST.ladderPath) return;
  collectLadderEdits('#diff-ladder-table-wrap');
  const r=await api('save_ladder_edit',ST.ladderPath,ST.ladder);
  if(r && r.ok){ $('#diff-result').hidden=true; ST.diff=null; toast('竞品修正已保存，请运行对比','ok'); }
};
$('#back-to-diff').onclick=async()=>{
  collectLadderEdits();
  if(ST.ladderPath) await api('save_ladder_edit',ST.ladderPath,ST.ladder);
  showPage('diff'); await rebuildPairs();
};
// The comparison data editor is contextual, not a second ladder workflow.
$('#ladder-raw-select').closest('.row').hidden=true;
$('#btn-export-ladder-md').hidden=true;
$('#page-settings ol').closest('.card').innerHTML='<h2>使用顺序</h2><p>配置阶梯：抓取或选择历史车型 → 检查版型 → 指定基准 → 导出MD。</p><p>竞争力对比：准备本品配置和赋值规则 → 选择历史竞品 → 配对版型 → 检查结果。</p><p class="dim">原始配置自动保留；可在竞争力对比中修正计算用的竞品配置。修正不会覆盖原始抓取记录。</p>';

// Secondary tools are reached from the workflow, with an explicit return.
for(const name of ['snapshot']){
  const button=document.createElement('button');
  button.textContent='返回竞争力对比';
  button.onclick=async()=>{showPage('diff');await refreshDiffSelects();};
  $('#page-'+name).prepend(button);
}
$$('[data-goto]').forEach(b=>b.onclick=()=>showPage(b.dataset.goto));
$('#inspect-raw').onclick=async()=>{
  const wrap=$('#raw-inspector');
  if(!wrap.hidden) {wrap.hidden=true;return;}
  const {raw}=await api('stage_get_raw');
  const cell=c=>[c,...(c.subs||[])].map(v=>(v.dot||'')+(v.text||'')).filter(Boolean).join(' / ')||'—';
  wrap.innerHTML='<table class="grid"><thead><tr><th>配置项</th>'+raw.trims.map(t=>`<th>${esc(t.short)}</th>`).join('')+'</tr></thead><tbody>'+raw.rows.map(r=>'<tr><td>'+esc(r.name)+'</td>'+r.cells.map(c=>'<td>'+esc(cell(c))+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
  wrap.hidden=false;
};


// PPT import is local, draft-first, and requires explicit review before persistence.
ST.pptPath=''; ST.pptDraft=null;
function renderDraftColumns(draft) {
  PptDraftEditor.mount($('#ppt-columns'),draft,{onInvalidate:invalidateDraftPreview});
}
function collectDraftColumns() {
  return ST.pptDraft;
}
function invalidateDraftPreview() {
  $('#ppt-review').hidden=true; $('#ppt-confirm').checked=false;
}
$('#btn-manual-product').onclick=()=>{
  if(ST.pptDraft && !window.confirm('开始手动填写将清空当前导入草稿，是否继续？'))return;
  ST.pptDraft={model:'',price_kind:'指导价',source:'手动填写',columns:[{name:'',base:null,price:null,text:''}]};
  $('#ppt-model').value=''; $('#ppt-price-kind').value='指导价';
  $('#ppt-import-panel').hidden=false; $('#ppt-draft-panel').hidden=false;
  $('#ppt-parse').closest('.row').hidden=true;
  $('#ppt-file-label').textContent='手动填写本品配置';
  $('#ppt-status').textContent='填写车型，添加版型和价格；配置可逐行粘贴，或展开后直接在完整表格中填写。';
  renderDraftColumns(ST.pptDraft); invalidateDraftPreview();
};
$('#ppt-add-trim').onclick=()=>{
  collectDraftColumns();
  ST.pptDraft.columns.push({name:'',base:null,price:null,text:''});
  renderDraftColumns(ST.pptDraft); invalidateDraftPreview();
};
$('#ppt-add-trim').hidden=true;
// Vue owns the draft column cards and keeps the draft model current.
$('#ppt-model').addEventListener('input',invalidateDraftPreview);
$('#ppt-price-kind').addEventListener('change',invalidateDraftPreview);
$('#btn-import-ppt').onclick=async()=>{
  const path=await api('open_file_dialog',['PowerPoint (*.pptx)']);
  if(!path || path.error)return;
  const res=await api('ppt_pages',path);
  ST.pptPath=path;
  $('#ppt-parse').closest('.row').hidden=false;
  $('#ppt-file-label').textContent=path.split(/[\\/]/).pop();
  $('#ppt-page').innerHTML=res.pages.map(p=>`<option value="${p.page}">P${p.page} · ${esc(p.title)}</option>`).join('');
  const suggested=res.pages.find(p=>p.title.includes('配置阶梯'));
  if(suggested)$('#ppt-page').value=suggested.page;
  $('#ppt-import-panel').hidden=false; $('#ppt-draft-panel').hidden=true;$('#ppt-review').hidden=true;
  $('#ppt-status').textContent='请选择需要导入的配置阶梯页。';
};
$('#ppt-parse').onclick=async()=>{
  $('#ppt-status').textContent='正在读取文本与版面…';
  try {
    const {draft}=await api('ppt_parse',ST.pptPath,+$('#ppt-page').value);
    ST.pptDraft=draft;
    $('#ppt-model').value=draft.model; $('#ppt-price-kind').value=draft.price_kind;
    $('#ppt-columns').innerHTML=draft.columns.map((c,i)=>`<div class="ppt-column" data-col="${i}"><label>版型名称<input class="ppt-name" value="${esc(c.name)}"></label><label>比较基准<select class="ppt-base"><option value="">独立基础配置</option>${draft.columns.filter(v=>v.name!==c.name).map(v=>`<option ${v.name===c.base?'selected':''} value="${esc(v.name)}">${esc(v.name)}</option>`).join('')}</select></label><label>页面价格（万元）<input class="ppt-price" type="number" step="0.01" value="${c.price??''}"></label><label>本列配置原文<textarea class="ppt-text">${esc(c.text)}</textarea></label></div>`).join('');
    $('#ppt-draft-panel').hidden=false; $('#ppt-review').hidden=true;
    renderDraftColumns(draft);
    $('#ppt-status').textContent=`已识别${draft.columns.length}个版型，请核对比较基准。` + (draft.warnings||[]).join(' ');
  } catch(e){$('#ppt-status').textContent='解析未完成：'+e.message;}
};
$('#ppt-expand').onclick=async()=>{
  const previous=ST.pptDraft.columns.map(c=>c.name);
  const rows=$$('#ppt-columns .ppt-column');
  const names=rows.map(r=>r.querySelector('.ppt-name').value.trim());
  const rename=Object.fromEntries(previous.map((n,i)=>[n,names[i]]));
  const draft={...ST.pptDraft,model:$('#ppt-model').value.trim(),price_kind:$('#ppt-price-kind').value,
    columns:rows.map((r,i)=>({name:names[i],base:rename[r.querySelector('.ppt-base').value]||null,
      price:r.querySelector('.ppt-price').value||null,text:r.querySelector('.ppt-text').value}))};
  const res=await api('ppt_preview',draft);
  ST.snapshot=res.snapshot;ST.snapshotPath='';
  $('#snapshot-info').textContent='PPT解析草稿 · 尚未保存';
  await renderSnapshot();
  $('#ppt-review').hidden=false;$('#ppt-confirm').checked=false;
  $('#ppt-evidence').textContent=JSON.stringify(res.snapshot.rulings[0],null,2);
  const remaining=res.snapshot.rulings[0]?.remaining||{};
  const unmatched=Object.entries(remaining).flatMap(([name,lines])=>lines.map(line=>`${name}：${line}`));
  $('#ppt-status').style.whiteSpace='pre-line';
  $('#ppt-status').textContent=unmatched.length?'以下原文未完全识别，请在下方对应配置行补充核对：\n'+unmatched.join('\n'):'完整配置已展开在下方，修改后勾选确认并保存。';
};
$('#ppt-save').onclick=async()=>{
  if(!$('#ppt-confirm').checked)return toast('请先核对并勾选确认','err');
  if(!ST.snapshot || ST.snapshot.status!=='待确认')return toast('请先展开PPT配置','err');
  if(!collectSnapshotEdits())return;
  const res=await api('save_ppt_snapshot',ST.snapshot,true);
  ST.snapshot=res.snapshot;ST.snapshotPath=res.path;
  await renderSnapshot();
  $('#snapshot-info').textContent=res.path;
  $('#ppt-status').textContent='已保存，可到竞争力对比选择本品。';
  $('#ppt-review').hidden=true;
  toast('本品配置已保存','ok');
};

// Arrange existing controls without replacing their event handlers.
const compareCard=$('#diff-mode').closest('.card');
const oldRow=$('#diff-mode').parentElement;
const modeRow=document.createElement('div'); modeRow.className='compare-mode';
modeRow.innerHTML='<strong>选择对比方式</strong>'; modeRow.append($('#diff-mode'));
const sides=document.createElement('div'); sides.className='compare-sides';
for(const [title,ids] of [['左侧 · 比较主体',['diff-snapshot','diff-left-vehicle','diff-edit-self','delete-self-file']],['右侧 · 对照车型',['diff-vehicle','diff-ladder','review-competitor']]]) {
  const side=document.createElement('div'); side.className='compare-side';
  const heading=document.createElement('h3'); heading.textContent=title; side.append(heading);
  ids.forEach(id=>side.append(document.getElementById(id))); sides.append(side);
}
const ruleRow=document.createElement('div'); ruleRow.className='compare-rules';
ruleRow.hidden=true;
ruleRow.innerHTML='<label>赋值规则</label>'; ruleRow.append($('#diff-valuation'));
compareCard.prepend(modeRow,sides,ruleRow); oldRow.remove();
const valuationShortcut=$('#diff-toggle-valuation');
const shortcutRow=valuationShortcut.closest('.row');
modeRow.append(valuationShortcut,$('#page-diff [data-goto="snapshot"]'));
if(!shortcutRow.children.length)shortcutRow.remove();
$('#btn-run-diff').closest('.row').classList.add('compare-actions');
$('#btn-run-diff').textContent='开始对比';
$('#btn-export-result').textContent='导出 Markdown';
for(const [anchor,kind] of [['btn-stage-export','ladder'],['btn-export-result','diff']]) {
  const markdown=document.getElementById(anchor);
  const group=document.createElement('div');
  group.className='export-buttons';
  markdown.before(group);
  markdown.textContent='导出 Markdown';
  markdown.classList.remove('primary');
  markdown.classList.add('export-button');
  group.append(markdown);
  const button=document.createElement('button');
  button.textContent='导出 Excel';
  button.className='export-button';
  group.append(button);
  button.onclick=async()=>{
    if(kind==='diff'&&!ST.diff)return toast('请先运行对比','err');
    button.disabled=true;
    try {
      const result=await api('export_excel',kind,kind==='ladder'?stagePlan():ST.diff);
      if(!result.cancelled)toast(result.ok?'Excel 已导出：'+result.path:result.error,result.ok?'ok':'err');
    } finally {button.disabled=false;}
  };
}
$('#page-diff .notice').hidden=true;
$('#page-diff .steps').textContent='01 选择车型　→　02 指定版型配对　→　03 查看并导出结果';
$('#pairs-editor strong').textContent='版型配对';
$('#page-diff .intro').textContent='选择两侧车型，指定版型配对，查看配置差异与赋值结果。';
