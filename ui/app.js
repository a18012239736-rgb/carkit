/* carkit 前端逻辑：pywebview js_api 调用 + 表格渲染 */
"use strict";

const ST = {
  checklist: null,
  ladder: null, ladderPath: "",
  snapshot: null, snapshotPath: "",
  valuation: null, valuationPath: "",
  diff: null,
  stage: {trims: [], seriesId: "", model: ""},
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function configurationChoices(no) {
  const base=['✕','[待定]'];
  const choices={
    3:['400V','800V'],
    4:Array.from({length:8},(_,i)=>i+16).flatMap(n=>[`R${n}钢轮毂`,`R${n}铝轮毂`]),
    7:['360影像','540影像'],9:['定速巡航','基础L2','高速NOA','城市NOA'],
    11:['●'],12:['●'],13:['●'],14:['●'],15:['●'],16:['●'],
    17:['卤素大灯','LED大灯'],18:['电动天窗','不可开启全景天窗','可开启全景天窗'],19:['●'],
    20:['电调','折叠','加热','电调+折叠','电调+加热','折叠+加热','电调+折叠+加热'],
    24:['●'],25:['塑料','仿皮','真皮','翻毛皮','NAPPA'],26:['手调','电调'],27:['●'],28:['●'],
    30:['HUD','AR-HUD'],31:['流媒体'],32:Array.from({length:10},(_,i)=>`${i+1}个`),
    33:['1个无线充电','2个无线充电'],39:['单色','多色'],40:['●'],41:['●'],
    5:[2,4,6,7,8,9,10,11,12].map(n=>`${n}气囊`),
    8:[1,2,3,4,5].map(n=>`${n}颗激光雷达`),
    35:['主驾6向电调+副驾4向手调','主驾6向电调+副驾4向电调','主驾8向电调+副驾4向电调','主驾10向电调+副驾6向电调'],
    38:[1,2,3,4].map(n=>`${n}车外扬声器`),
    6:['悬架软硬调节','悬架高低调节','悬架软硬+高低调节'],
    23:['4G','5G'],34:['织物','仿皮','真皮','翻毛皮','NAPPA真皮'],
  };
  return choices[no]?base.concat(choices[no]):null;
}

function addConfigurationChoices(root, snapshotCells=null) {
  const fields=snapshotCells ? root.querySelectorAll('input[data-cell]') : root.querySelectorAll('td[data-no]:not([data-sub])');
  fields.forEach(field=>{
    const no=snapshotCells?snapshotCells[+field.dataset.cell].no:+field.dataset.no;
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
function configurationCellValue(td){
  return td.querySelector('input[data-config-value]')?.value.trim() ?? td.textContent.trim();
}

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
  const res = await api("stage_search", sid, $("#scrape-year").value.trim());
  handleStageResult(res);
});

$("#btn-scrape-capture").addEventListener("click", async () => {
  const res = await api("stage_continue");
  handleStageResult(res);
});

function handleStageResult(res) {
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

function renderStageTrimEditor() {
  $("#stage-trims").hidden = false;
  const trims = ST.stage.trims;
  $("#stage-trim-editor").innerHTML = trims.map((t,i) => `<div class="stage-trim-row"><label><input type="checkbox" class="stage-use" data-i="${i}" checked> ${esc(t.name)}（${t.price_guide ?? '待核'}万）</label><select class="stage-base" data-i="${i}" ${i===0?'disabled':''}><option value="">基本配置</option></select></div>`).join("");
  $$(".stage-base").forEach(sel => { const i=+sel.dataset.i; for(let j=0;j<i;j++) sel.insertAdjacentHTML('beforeend', `<option value="${j}">${esc(trims[j].name)}</option>`); });
  $$(".stage-use").forEach(cb => cb.addEventListener('change', updateStageBases));
  const selected=trims.map((t,i)=>document.querySelector(`.stage-use[data-i="${i}"]`)?.checked?i:null).filter(i=>i!==null);
  $$(".stage-base").forEach(sel => { const i=+sel.dataset.i; sel.innerHTML='<option value="">基本配置</option>'+selected.filter(j=>j<i).map(j=>`<option value="${j}">${esc(trims[j].name)}</option>`).join(''); });
}

function updateStageBases() {
  const selected=new Set($$(".stage-use:checked").map(x=>+x.dataset.i));
  $$(".stage-base").forEach(sel => { const i=+sel.dataset.i; const old=sel.value; sel.innerHTML='<option value="">基本配置</option>'+[...selected].filter(j=>j<i).map(j=>`<option value="${j}">${esc(ST.stage.trims[j].name)}</option>`).join(''); if([...sel.options].some(o=>o.value===old)) sel.value=old; });
}

$("#btn-stage-export").addEventListener("click", async () => {
  const plan=[]; const selected=new Set($$(".stage-use:checked").map(x=>+x.dataset.i));
  $$(".stage-use").forEach(cb=>{const i=+cb.dataset.i;if(selected.has(i)){const sel=document.querySelector(`.stage-base[data-i="${i}"]`);plan.push({target:i,base:sel&&sel.value!==''?+sel.value:null});}});
  const res=await api("stage_export",plan,ST.stage.model+'-配置阶梯');
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

function renderLadderTable(target="#ladder-table-wrap") {
  const lad = ST.ladder;
  if (!lad) return;
  const wrap = $(target);
  let html = '<table class="grid"><thead><tr><th>#</th><th>配置项</th>';
  html += lad.trims.map((t) => `<th>${t.name}<br><span class="dim">${t.price_guide ?? ""}万</span></th>`).join("");
  html += "</tr></thead><tbody>";
  for (const it of lad.items) {
    html += `<tr><td class="no">${it.no}</td><td>${it.name}${it.unmapped ? ' <span class="tag warn">待映射</span>' : ""}</td>`;
    html += it.values.map((v, i) =>
      `<td contenteditable data-no="${it.no}" data-i="${i}" class="${cellCls(v)}">${esc(v)}</td>`).join("");
    html += "</tr>";
    for (const sr of it.subs || []) {
      html += `<tr><td class="no">—</td><td class="dim">${sr.sub}</td>`;
      html += sr.values.map((v, i) =>
        `<td contenteditable data-no="${it.no}" data-sub="${sr.sub}" data-i="${i}" class="${cellCls(v)}">${esc(v)}</td>`).join("");
      html += "</tr>";
    }
  }
  html += "</tbody></table>";
  wrap.innerHTML = html;
  addConfigurationChoices(wrap);
}

function collectLadderEdits(target="#ladder-table-wrap") {
  if (!ST.ladder) return;
  $$(target+" td[data-no]").forEach((td) => {
    const no = +td.dataset.no, i = +td.dataset.i;
    const it = ST.ladder.items.find((x) => x.no === no);
    if (!it) return;
    if (td.dataset.sub) {
      const sr = (it.subs || []).find((s) => s.sub === td.dataset.sub);
      if (sr) sr.values[i] = configurationCellValue(td);
    } else {
      it.values[i] = configurationCellValue(td);
    }
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
  collectSnapshotEdits();
  await api("save_snapshot", ST.snapshotPath, ST.snapshot);
  toast("快照已保存", "ok");
});

async function renderSnapshot() {
  const snap = ST.snapshot;
  if (!snap) return;
  const cl = await loadChecklist();
  const items = cl.items.filter((it) => !it.merged_into);
  // 版型编辑区
  $("#snapshot-trims").innerHTML = snap.trims.map((t, i) => `
    <div class="trim-row">
      <input type="text" data-ti="${i}" data-k="name" value="${esc(t.name)}">
      <input type="text" data-ti="${i}" data-k="price_guide" value="${t.price_guide ?? ""}" style="width:80px" title="指导价(万)" placeholder="指导价">
      <input type="text" data-ti="${i}" data-k="mix" value="${esc(t.mix || "")}" style="width:60px" title="占比">
      <input type="text" data-ti="${i}" data-k="range" value="${esc(t.range || "")}" style="width:70px" title="续航">
      <span class="dim">${t.price_source ? esc(t.price_source)+"："+(t.price_reference??"未写")+"万；指导价请另填" : "万元"}</span>
    </div>`).join("");
  $$("#snapshot-trims input").forEach((inp) =>
    inp.addEventListener("change", () => {
      const t = snap.trims[+inp.dataset.ti];
      if(inp.dataset.k==='name') {
        const old=t.name, name=inp.value.trim();
        if(!name || snap.trims.some(other=>other!==t && other.name===name)){inp.value=old;toast('版型名称不能为空或重复','err');return;}
        collectSnapshotEdits();
        for(const c of snap.cells){c.values[name]=c.values[old];delete c.values[old];}
        t.name=name; renderSnapshot(); return;
      }
      t[inp.dataset.k] = inp.dataset.k === "price_guide" ? (parseFloat(inp.value) || null) : inp.value;
    })
  );
  // 41项表
  const cellByNo = {};
  for (const c of snap.cells) cellByNo[c.no] = c;
  const pendingCount = snap.cells.reduce((n, c) => n + Object.values(c.values || {}).filter(v => {
    if (v && typeof v === 'object') return Object.values(v).some(x => String(x ?? '').includes('[待定]'));
    return String(v ?? '').includes('[待定]') || String(v ?? '').trim() === '?';
  }).length, 0);
  const info = document.querySelector('#snapshot-info');
  if (info && pendingCount) info.textContent = `${snap.model || '本品'} · 还有 ${pendingCount} 个版型配置单元格待确认；可直接点击下方单元格修改`;
  let html = '<table class="grid"><thead><tr><th>#</th><th>配置项</th>';
  html += snap.trims.map((t) => `<th>${esc(t.name)}</th>`).join("");
  html += "<th>依据</th></tr></thead><tbody>";
  for (const it of items) {
    const c = cellByNo[it.no];
    const isSub = c && typeof Object.values(c.values)[0] === "object";
    if (isSub) {
      const subNames = Object.keys(Object.values(c.values)[0]);
      for (const sn of subNames) {
        html += `<tr><td class="no">${it.no}</td><td>${it.name}·${sn}</td>`;
        html += snap.trims.map((t, i) =>
          `<td contenteditable="true" spellcheck="false" title="点击修改；填写 X 表示无配置，填写 [待定] 表示暂未确定" data-no="${it.no}" data-sub="${sn}" data-t="${esc(t.name)}" class="${cellCls(c.values[t.name][sn])}">${esc(c.values[t.name][sn])}</td>`).join("");
        html += `<td class="dim">${esc(c.basis || "")}</td></tr>`;
      }
    } else {
      html += `<tr><td class="no">${it.no}</td><td>${it.name}</td>`;
      html += snap.trims.map((t) => {
        const v = c ? (c.values[t.name] ?? "?") : "?";
          return `<td contenteditable="true" spellcheck="false" title="点击修改；填写 X 表示无配置，填写 [待定] 表示暂未确定" data-no="${it.no}" data-t="${esc(t.name)}" class="${cellCls(v)}">${esc(v)}</td>`;
      }).join("");
      html += `<td class="dim" contenteditable data-basis="${it.no}">${esc(c ? c.basis || "" : "")}</td></tr>`;
    }
  }
  html += "</tbody></table>";
  $("#snapshot-table-wrap").innerHTML = html;
  addConfigurationChoices($('#snapshot-table-wrap'));
}

function collectSnapshotEdits() {
  if (!ST.snapshot) return;
  const cellByNo = {};
  for (const c of ST.snapshot.cells) cellByNo[c.no] = c;
  $$("#snapshot-table-wrap td[contenteditable]").forEach((td) => {
    const no = +td.dataset.no || +td.dataset.basis;
    const c = cellByNo[no];
    if (!c) return;
    if (td.dataset.basis) { c.basis = td.textContent.trim(); return; }
    const v = configurationCellValue(td);
    if (td.dataset.sub) {
      if (typeof c.values[td.dataset.t] !== "object") c.values[td.dataset.t] = {};
      c.values[td.dataset.t][td.dataset.sub] = v;
    } else {
      c.values[td.dataset.t] = v;
    }
  });
}

/* ---------- ④ 赋值表 ---------- */
$("#btn-make-template").addEventListener("click", async () => {
  const res = await api("make_valuation_template");
  if (res.ok) toast("模板已生成：\n" + res.path, "ok");
});

$("#btn-load-valuation").addEventListener("click", async () => {
  const path = await api("open_file_dialog", ["赋值表 (*.xlsx;*.json)"]);
  if (!path || path.error) return;
  const res = await api("load_valuation", path);
  if (res.ok) {
    ST.valuation = res.valuation;
    ST.valuationPath = path.endsWith(".json") ? path : path.replace(/\.xlsx$/, "") + ".json";
    $("#valuation-info").textContent = path;
    renderValuation();
  }
});

$("#btn-save-valuation").addEventListener("click", async () => {
  if (!ST.valuation) return toast("先载入或生成赋值表", "err");
  collectValuationEdits();
  await api("save_valuation", ST.valuationPath, ST.valuation);
  toast("赋值表已保存: " + ST.valuationPath, "ok");
});

async function renderValuation() {
  const v = ST.valuation;
  if (!v) return;
  const cl = await loadChecklist();
  const nameByNo = {};
  for (const it of cl.items) nameByNo[it.no] = it.md_name || it.name;
  const byNo = {};
  for (const it of v.items) byNo[it.no] = it;
  let html = '<table class="grid"><thead><tr><th>#</th><th>配置项</th><th>计价方式</th><th>金额/单价(元)</th><th>分段JSON</th><th>备注</th></tr></thead><tbody>';
  for (const no of Object.keys(nameByNo).map(Number)) {
    const it = byNo[no] || {};
    html += `<tr><td class="no">${no}</td><td>${nameByNo[no]}</td>
      <td contenteditable data-no="${no}" data-k="pricing">${esc(it.pricing || "flat")}</td>
      <td contenteditable data-no="${no}" data-k="val" class="${it.val == null || it.val === "" ? "pending" : ""}">${it.val ?? ""}</td>
      <td contenteditable data-no="${no}" data-k="bands" style="max-width:260px">${esc(it.bands ? JSON.stringify(it.bands) : "")}</td>
      <td contenteditable data-no="${no}" data-k="note">${esc(it.note || "")}</td></tr>`;
  }
  html += "</tbody></table>";
  $("#valuation-table-wrap").innerHTML = html;
}

function collectValuationEdits() {
  if (!ST.valuation) return;
  const byNo = {};
  for (const it of ST.valuation.items) byNo[it.no] = it;
  $$("#valuation-table-wrap td[contenteditable]").forEach((td) => {
    const no = +td.dataset.no, k = td.dataset.k;
    if (!byNo[no]) byNo[no] = { no, name: "", pricing: "flat", val: null, bands: [], note: "" }, ST.valuation.items.push(byNo[no]);
    const raw = td.textContent.trim();
    if (k === "val") byNo[no].val = raw === "" ? null : parseFloat(raw);
    else if (k === "bands") { try { byNo[no].bands = raw ? JSON.parse(raw) : []; } catch { toast(`#${no} 分段JSON 解析失败`, "err"); } }
    else byNo[no][k] = raw;
  });
}

/* ---------- ⑤ 对比 ---------- */
async function refreshDiffSelects() {
  const [snaps, lads, vals] = await Promise.all([
    api("list_files", "快照"), api("list_files", "阶梯"), api("list_files", "赋值"),
  ]);
  fillSelect("#diff-snapshot", snaps.filter(f=>f.endsWith('.json')));
  fillSelect("#diff-valuation", vals.filter(f=>f.endsWith('.json') || f.endsWith('.xlsx')), "内置用户赋值规则（默认）");
  const history = await api('vehicle_history');
  const sel = $('#diff-vehicle'); const previous = sel.value;
  sel.innerHTML = '<option value="">请选择已抓取的竞品</option>'+history.map(r=>`<option value="${esc(r.file)}">${esc(r.label)}</option>`).join('');
  if ([...sel.options].some(o=>o.value===previous)) sel.value=previous;
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
$("#diff-ladder").addEventListener("change", rebuildPairs);

async function rebuildPairs() {
  const box = $("#pairs-editor");
  box.querySelectorAll(".pair-row").forEach((r) => r.remove());
  const [sn, ld] = [$("#diff-snapshot").value, $("#diff-ladder").value];
  if (!sn || !ld) return;
  const sp = await api("workdir_path", "快照", sn);
  const lp = await api("workdir_path", "阶梯", ld);
  const [sres, lres] = [await api("load_snapshot", sp), await api("load_ladder", lp)];
  const st = sres.snapshot.trims.map((t) => t.name);
  const ct = lres.ladder.trims.map((t) => t.name);
  box.dataset.selfTrims = JSON.stringify(st);
  box.dataset.compTrims = JSON.stringify(ct);
  addPairRow(st, ct);
}

$("#btn-add-pair").addEventListener("click", () => {
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
  row.querySelector(".pair-del").addEventListener("click", () => row.remove());
  $("#pairs-editor").appendChild(row);
}

$("#btn-run-diff").addEventListener("click", async () => {
  const sn = $("#diff-snapshot").value, ld = $("#diff-ladder").value;
  if (!sn || !ld) return toast("请先选择快照与竞品阶梯", "err");
  const pairs = $$("#pairs-editor .pair-row").map((r) => ({
    self_trim: r.querySelector(".pair-self").value,
    comp_trim: r.querySelector(".pair-comp").value,
  }));
  if (!pairs.length) return toast("请至少指定一组版型配对（铁律：人工指定）", "err");
  const sp = await api("workdir_path", "快照", sn);
  const lp = await api("workdir_path", "阶梯", ld);
  const vv = $("#diff-valuation").value;
  const vp = vv ? await api("workdir_path", "赋值", vv) : "";
  $("#diff-status").textContent = "计算中…";
  const res = await api("run_diff", sp, lp, pairs, vp);
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
  const nos = [...new Set(res.cells.map((c) => c.no))].sort((a, b) => a - b);
  const nameByNo = {};
  res.cells.forEach((c) => (nameByNo[c.no] = c.name));
  let d = '<table class="grid"><thead><tr><th>#</th><th>配置项</th>';
  d += groups.map((g) => `<th>${g.pair.self_trim}vs${g.pair.comp_trim}</th>`).join("") + "</tr></thead><tbody>";
  for (const no of nos) {
    d += `<tr><td class="no">${no}</td><td>${nameByNo[no]}</td>`;
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
  const dest = await api("save_file_dialog", "赋值对比结果.md", ["Markdown (*.md)"]);
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
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===name));
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
  $('#diff-competitor-editor').hidden=true;
  $('#diff-ladder-table-wrap').innerHTML='';
  selectCompetitor();
});
// Keep both editors inside the comparison workflow.
$('#pairs-editor').before($('#diff-competitor-editor'));
$('#review-competitor').textContent='修改当前竞品配置';
$('#diff-competitor-editor h3').textContent='修改竞品配置';
let comparisonSelf=null, comparisonSelfPath='';
$('#delete-self-file').onclick=async()=>{
  const file=$('#diff-snapshot').value;
  if(!file)return toast('请先选择要删除的本品文件','err');
  if(!window.confirm(`删除本品配置「${file}」？\n文件将移入工作目录的回收站，原始PPT不受影响。`))return;
  await api('remove_imported_snapshot',file);
  comparisonSelf=null;comparisonSelfPath='';
  ST.snapshot=null;ST.snapshotPath='';ST.diff=null;
  $('#diff-self-editor').hidden=true;$('#diff-result').hidden=true;
  $('#snapshot-table-wrap').innerHTML='';$('#snapshot-trims').innerHTML='';$('#snapshot-info').textContent='';
  $('#diff-status').textContent='已移入回收站';
  await refreshDiffSelects();await rebuildPairs();
  toast('已删除；可在工作目录的回收站找回','ok');
};
$('#diff-snapshot').addEventListener('change',()=>{
  $('#diff-self-editor').hidden=true; comparisonSelf=null;
});
$('#diff-edit-self').onclick=async()=>{
  const file=$('#diff-snapshot').value;
  if(!file)return toast('请先选择本品配置','err');
  comparisonSelfPath=await api('workdir_path','快照',file);
  const r=await api('load_snapshot',comparisonSelfPath);
  comparisonSelf=r.snapshot;
  const checklist=await loadChecklist();
  const names=Object.fromEntries(checklist.items.map(x=>[x.no,x.name]));
  let html='<table class="grid"><tr><th>配置项</th>'+comparisonSelf.trims.map(t=>`<th>${esc(t.name)}</th>`).join('')+'</tr>';
  html+='<tr><th>指导价（万元）</th>'+comparisonSelf.trims.map((t,i)=>`<td><input data-price="${i}" type="number" step="0.01" value="${t.price_guide??''}"></td>`).join('')+'</tr>';
  comparisonSelf.cells.forEach((c,i)=>{
    const subs=[...new Set(Object.values(c.values).flatMap(v=>v&&typeof v==='object'?Object.keys(v):[]))];
    (subs.length?subs:[null]).forEach(sub=>{
      html+=`<tr><th>${esc(names[c.no]||String(c.no))}${sub?' · '+esc(sub):''}</th>`;
      html+=comparisonSelf.trims.map((t,j)=>{
        const v=sub?(c.values[t.name]||{})[sub]:c.values[t.name];
        return `<td><input style="min-width:180px;width:95%" data-cell="${i}" data-trim="${j}" data-sub="${esc(sub||'')}" value="${esc(v??'✕')}"></td>`;
      }).join('')+'</tr>';
    });
  });
  $('#diff-self-table').innerHTML=html+'</table>';
  addConfigurationChoices($('#diff-self-table'),comparisonSelf.cells);
  $('#diff-self-editor').hidden=false;
};
$('#diff-save-self').onclick=async()=>{
  if(!comparisonSelf)return;
  $$('#diff-self-table input[data-cell]').forEach(el=>{
    const c=comparisonSelf.cells[+el.dataset.cell], name=comparisonSelf.trims[+el.dataset.trim].name;
    if(el.dataset.sub){
      if(!c.values[name]||typeof c.values[name]!=='object')c.values[name]={};
      c.values[name][el.dataset.sub]=el.value.trim()||'✕';
    }else c.values[name]=el.value.trim()||'✕';
  });
  for(const el of $$('#diff-self-table input[data-price]')){
    const v=el.value===''?null:Number(el.value);
    if(v!==null&&(!Number.isFinite(v)||v<=0))return toast('指导价应为正数，单位万元','err');
    comparisonSelf.trims[+el.dataset.price].price_guide=v;
  }
  await api('save_snapshot',comparisonSelfPath,comparisonSelf);
  $('#diff-result').hidden=true; ST.diff=null;
  toast('本品修正已保存，请运行对比','ok');
};
$('#review-competitor').onclick=()=>{
  if(!ST.ladder || !$('#diff-ladder').value) return toast('请先选择竞品');
  const panel=$('#diff-competitor-editor'); panel.hidden=!panel.hidden;
  if(!panel.hidden) renderLadderTable('#diff-ladder-table-wrap');
};
$('#diff-save-competitor').onclick=async()=>{
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
for(const name of ['snapshot','valuation']){
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
$('#btn-import-ppt').onclick=async()=>{
  const path=await api('open_file_dialog',['PowerPoint (*.pptx)']);
  if(!path || path.error)return;
  const res=await api('ppt_pages',path);
  ST.pptPath=path;
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
    $('#ppt-status').textContent=`已识别${draft.columns.length}个版型，请核对比较基准。`;
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
  $('#ppt-status').textContent='完整配置已展开在下方，修改后勾选确认并保存。';
};
$('#ppt-save').onclick=async()=>{
  if(!$('#ppt-confirm').checked)return toast('请先核对并勾选确认','err');
  if(!ST.snapshot || ST.snapshot.status!=='待确认')return toast('请先展开PPT配置','err');
  collectSnapshotEdits();
  const res=await api('save_ppt_snapshot',ST.snapshot,true);
  ST.snapshot=res.snapshot;ST.snapshotPath=res.path;
  $('#snapshot-info').textContent=res.path;
  $('#ppt-status').textContent='已保存，可到竞争力对比选择本品。';
  $('#ppt-review').hidden=true;
  toast('本品配置已保存','ok');
};
