/* 竞争力对比内部子页签：对比 / 本品配置 / 赋值规则。
   app.js 的 showPage('snapshot'|'valuation'|'diff') 经 window.showDiffSub 接入；
   子页签按钮与 [data-sub-goto] 按钮在此绑定。 */
(() => {
  'use strict';

  function sync(name) {
    document.querySelectorAll('.diff-sub').forEach(el =>
      el.classList.toggle('active', el.dataset.sub === name));
    document.querySelectorAll('.diff-tab').forEach(button => {
      const on = button.dataset.sub === name;
      button.classList.toggle('active', on);
      if (on) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
  }

  window.showDiffSub = function (name, viaPage) {
    if (!document.querySelector('#page-diff')) return;
    if (name === 'valuation' && ST.plan) {
      if (window.toast) toast('当前使用方案保存的规则；请先退出方案再修改全局规则。', 'err');
      return;
    }
    sync(name);
    if (viaPage) return; // showPage 已负责页面激活、导航态与滚动
    document.querySelectorAll('.page').forEach(p =>
      p.classList.toggle('active', p.id === 'page-diff'));
    document.querySelectorAll('.nav-item').forEach(b => {
      const on = b.dataset.page === 'diff';
      b.classList.toggle('active', on);
      if (on) b.setAttribute('aria-current', 'page');
      else b.removeAttribute('aria-current');
    });
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    if (name === 'valuation' && window.loadCurrentValuation) loadCurrentValuation();
    if (name === 'compare' && window.refreshDiffSelects) refreshDiffSelects();
  };

  document.querySelectorAll('.diff-tab').forEach(button =>
    button.addEventListener('click', () => window.showDiffSub(button.dataset.sub)));
  document.querySelectorAll('[data-sub-goto]').forEach(button =>
    button.addEventListener('click', () => window.showDiffSub(button.dataset.subGoto)));
})();
