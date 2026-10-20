/* Comparison archives and read-only source review. Pricing stays in the engine. */
(() => {
  'use strict';
  const selectors=['#diff-mode','#diff-snapshot','#diff-left-vehicle','#diff-vehicle','#diff-valuation'];
  let plansRevision=0;
  const showTime = value => value ? new Date(value).toLocaleString('zh-CN') : '';
  const evidenceButton = (pair,no) => `<button class="evidence-link" data-evidence-pair="${Number(pair)}" data-evidence-no="${Number(no)}">查看依据</button>`;

  function setPlanStatus(message) {
    ['#comparison-plan-status','#comparison-save-status'].forEach(selector=>{
      const status=$(selector);
      if(status)status.textContent=message;
    });
  }

  function sync() {
    const save=$('#btn-save-plan');
    save.disabled=!!save.dataset.busy || !ST.diff?.comparison_id;
    save.title=ST.diff?.comparison_id?'':'请先完成对比；修改配置后需重新计算再保存';
    const controls=$('#comparison-save-controls');
    if(controls)controls.hidden=!ST.diff;
    selectors.forEach(selector=>$(selector).disabled=!!ST.plan);
    ['#diff-toggle-valuation','#btn-save-valuation','#btn-reset-valuation','#btn-make-template','#btn-load-valuation'].forEach(selector=>$(selector).disabled=!!ST.plan);
    $('#delete-self-file').disabled=!!ST.plan || !$('#diff-snapshot').value;
    $('#comparison-plan-banner').hidden=!ST.plan;
    if (!ST.diff) {
      const status=$('#comparison-save-status');
      if(status)status.textContent='';
      const dialog=$('#comparison-evidence');
      if(dialog.open) dialog.close();
    }
  }

  async function refreshPlans() {
    const revision=++plansRevision, select=$('#comparison-plan-list');
    const result=await api('comparison_plans');
    if(revision!==plansRevision)return;
    const previous=select.value;
    select.innerHTML='<option value="">请选择已保存方案</option>'+result.plans.map(plan=>
      `<option value="${esc(plan.file)}">${esc(plan.name)} · ${esc(showTime(plan.created_at))}</option>`).join('');
    if([...select.options].some(option=>option.value===previous))select.value=previous;
  }

  function setChoice(selector, value, text) {
    $(selector).innerHTML=`<option value="${esc(value)}">${esc(text)}</option>`;
    $(selector).value=value;
  }

  async function openPlan() {
    const file=$('#comparison-plan-list').value, button=$('#btn-open-plan');
    if(!file || button.dataset.busy)return;
    if((!$('#diff-self-editor').hidden || !$('#diff-competitor-editor').hidden ||
        ConfigEditor.isMounted($('#diff-self-table')) || ConfigEditor.isMounted($('#diff-ladder-table-wrap'))) &&
       !window.confirm('打开方案会切换当前配置。若有未保存的修改，请先取消并保存。是否继续？'))return;
    setActionBusy(button,true);
    const revision=invalidateDiff();
    ++ST.competitorRevision; ++ST.pairsRevision;
    hideComparisonEditors();
    try {
      const opened=await api('open_comparison_plan',file);
      if(revision!==ST.diffRevision)return;
      ST.plan=opened;
      const inputs=opened.inputs, competitor=inputs.left_kind==='ladder';
      $('#diff-mode').value=competitor?'competitor':'self';
      $('#diff-left-vehicle').hidden=!competitor;$('#diff-snapshot').hidden=competitor;
      $('#delete-self-file').hidden=competitor;
      $('#diff-edit-self').textContent=competitor?'修改左侧方案配置':'修改本品方案配置';
      $('#diff-save-self').textContent='保存方案工作副本';
      setChoice(competitor?'#diff-left-vehicle':'#diff-snapshot','__plan_left__',inputs.left.model+'（方案副本）');
      setChoice('#diff-vehicle','__plan_right__',inputs.right.model+'（方案副本）');
      setChoice('#diff-ladder','__plan_right__',inputs.right.model);
      setChoice('#diff-valuation','__plan_rules__','方案保存的赋值规则');
      ST.ladder=inputs.right;ST.ladderPath=opened.paths.right;ST.competitorFile='__plan_right__';
      const left=inputs.left.trims.map(trim=>trim.name), right=inputs.right.trims.map(trim=>trim.name);
      const box=$('#pairs-editor');
      box.querySelectorAll('.pair-row').forEach(row=>row.remove());
      box.dataset.selfTrims=JSON.stringify(left);box.dataset.compTrims=JSON.stringify(right);
      for(const pair of inputs.pairs) {
        addPairRow(left,right);
        const row=box.querySelectorAll('.pair-row');const current=row[row.length-1];
        current.querySelector('.pair-self').value=pair.self_trim;
        current.querySelector('.pair-comp').value=pair.comp_trim;
        current.querySelector('.pair-self-floor').value=pair.self_floor_price ?? '';
        current.querySelector('.pair-comp-floor').value=pair.comp_floor_price ?? '';
      }
      $('#comparison-plan-name').value=opened.name;
      $('#comparison-plan-context').textContent=`方案：${opened.name} · 保存于${showTime(opened.created_at)}。当前显示保存时的结果；修改后重新计算只使用方案内规则（算法使用当前程序版本）。如需更换车型或全局规则，请先退出方案。`;
      setPlanStatus('已打开独立工作副本。修改并重新对比后，可另存为新方案；原方案不会被覆盖。');
      ST.diff=opened.result;
      renderDiff(opened.result);
      $('#diff-status').textContent='已载入方案保存时的结果，尚未重新计算。';
    } finally {
      setActionBusy(button,false);
    }
  }

  async function leavePlan() {
    ++ST.competitorRevision;++ST.pairsRevision;
    ST.plan=null;ST.valuation=null;ST.valuationPath='';
    hideComparisonEditors();invalidateDiff();
    ST.ladder=null;ST.ladderPath='';ST.competitorFile='';
    selectors.filter(selector=>selector!=='#diff-mode').forEach(selector=>$(selector).innerHTML='');
    $('#diff-ladder').innerHTML='';
    $('#pairs-editor').querySelectorAll('.pair-row').forEach(row=>row.remove());
    setPlanStatus('已退出方案，原方案及工作副本仍保留在本地。');
    $('#diff-edit-self').textContent=$('#diff-mode').value==='competitor'?'修改左侧竞品配置':'修改当前本品配置';
    $('#diff-save-self').textContent=$('#diff-mode').value==='competitor'?'保存左侧竞品修正':'保存本品修正';
    await refreshDiffSelects();
    sync();
  }

  function render(result) {
    const rows=result.review || [], warnings=rows.filter(row=>row.level==='warning');
    const info=$('#comparison-review-info').checked;
    const selected=rows.filter(row=>info || row.level==='warning');
    const review=$('#comparison-review');
    review.hidden=false;
    review.dataset.hasWarnings=String(warnings.length>0);
    $('#comparison-review-summary').textContent=`${warnings.length?'有'+warnings.length+'项待核':'未发现已知待核项'} · ${rows.length-warnings.length}项来源提示`;
    $('#comparison-review-list').innerHTML=selected.length?
      '<table class="grid"><thead><tr><th>配对</th><th>配置项</th><th>位置</th><th>提示</th><th>依据</th></tr></thead><tbody>'+selected.map(row=>
        `<tr><td>${Number(row.pair)+1}</td><td>${esc(row.name)}</td><td>${esc(row.side==='left'?'左侧':row.side==='right'?'右侧':'双方')}</td><td>${esc(row.message)}</td><td>${evidenceButton(row.pair,row.no)}</td></tr>`).join('')+'</tbody></table>':
      '<p class="dim">未发现需检查的已知项目。此提示不代表配置已全部人工核实。</p>';
  }

  function rawCell(cell) {
    if(!cell)return '';
    return [((cell.dot || '')+(cell.text || '')).trim() || '未填写',
      ...(cell.subs || []).map(rawCell)].join('\n');
  }

  function sourceHtml(side) {
    const lines=items=>items?.length?'<ul>'+items.map(text=>`<li>${esc(text)}</li>`).join('')+'</ul>':'';
    const value=value=>typeof value==='string'?value:JSON.stringify(value,null,2);
    const url=String(side.source_url || '');
    const link=/^https:\/\/(?:www\.)?autohome\.com\.cn\//.test(url)?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">汽车之家来源页面</a>`:'';
    const rows=side.rows || [], inputOnly=!rows.length && side.source_kind==='input';
    return `<section class="evidence-side"><h3>${esc(side.model)} · ${esc(side.trim)}</h3>
      <p>${link}${side.captured_at?' · '+esc(side.captured_at):''}</p>
      <h4>原始依据</h4>${rows.length?rows.map(row=>`<strong>${esc(row.name)}</strong><pre>${esc(rawCell(row.cell))}</pre>`).join(''):inputOnly?'<p class="dim">来源为本品或人工输入配置，未关联汽车之家原表。</p>'+lines(side.notes):'<p class="dim">这份记录未包含可对应的原始配置；下方保留本次计算采用的值。</p>'}
      ${side.source_value!=null?`<h4>原文识别结果</h4><pre>${esc(value(side.source_value))}</pre>`:''}
      <h4>本次计算采用</h4><pre>${esc(value(side.value))}</pre>${lines(side.calculation)}${inputOnly?'':lines(side.notes)}</section>`;
  }

  function showEvidence(pair,no) {
    const entry=ST.diff?.evidence?.find(entry=>entry.pair===pair && entry.no===no);
    if(!entry)return;
    $('#comparison-evidence-title').textContent=`${entry.name} · 第${pair+1}组原文与计算依据`;
    $('#comparison-evidence-content').innerHTML='<div class="evidence-sides">'+sourceHtml(entry.left)+sourceHtml(entry.right)+'</div>'+ 
      `<section class="evidence-rule"><h3>本次赋值依据</h3><p>${esc(entry.rule || '该项未设置赋值规则')}</p><p>${entry.amount==null?'本项未单列计价，或双方无金额差异；以完整计算明细为准。':'本次金额差：'+fmtMoney(entry.amount)+' 元'}</p></section>`;
    const dialog=$('#comparison-evidence');
    if(!dialog.open)dialog.showModal();
  }

  $('#btn-save-plan').onclick=async()=>{
    const result=ST.diff, button=$('#btn-save-plan');
    if(!result?.comparison_id || button.dataset.busy)return;
    setActionBusy(button,true);
    try {
      const saved=await api('save_comparison_plan',$('#comparison-plan-name').value.trim(),result.comparison_id);
      if(result===ST.diff)setPlanStatus(`已另存方案：${saved.name} · ${showTime(saved.created_at)}`);
      else toast(`已保存点击时的方案：${saved.name}；新的配置尚未保存。`,'ok');
      await refreshPlans();
    } finally {setActionBusy(button,false);}
  };
  $('#btn-open-plan').onclick=openPlan;
  $('#btn-leave-plan').onclick=leavePlan;
  $('#btn-refresh-plans').onclick=()=>refreshPlans().catch(()=>{});
  $('#comparison-review-info').onchange=()=>{if(ST.diff)render(ST.diff);};
  $('#comparison-evidence-close').onclick=()=>$('#comparison-evidence').close();
  document.addEventListener('click',event=>{
    const button=event.target.closest('[data-evidence-no]');
    if(button)showEvidence(Number(button.dataset.evidencePair),Number(button.dataset.evidenceNo));
  });
  window.addEventListener('pywebviewready',()=>refreshPlans().catch(()=>{}));
  document.querySelector('.comparison-plans').addEventListener('toggle',event=>{
    if(event.target.open && window.pywebview)refreshPlans().catch(()=>{});
  });
  window.ComparisonTools={sync,render,showEvidence,openPlan,leavePlan,refreshPlans};
  sync();
})();
