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

  const pillFrame = ({x, y, width, height}) => ({
    transform:`translate(${x}px, ${y}px)`, width:`${width}px`, height:`${height}px`
  });

  function slidePill(pill, from, to) {
    const dx = to.x + to.width / 2 - from.x - from.width / 2;
    const dy = to.y + to.height / 2 - from.y - from.height / 2;
    const horizontal = Math.abs(dx) >= Math.abs(dy);
    const distance = Math.abs(horizontal ? dx : dy);
    if (distance < 1) return;
    const stretch = Math.min(32, distance * .5, (horizontal ? to.width : to.height) * .52);
    function pose(position, length, sizeAt = position) {
      const width = from.width + (to.width - from.width) * sizeAt + (horizontal ? length : 0);
      const height = from.height + (to.height - from.height) * sizeAt + (horizontal ? 0 : length);
      return pillFrame({
        x:from.x + from.width / 2 + dx * position - width / 2,
        y:from.y + from.height / 2 + dy * position - height / 2,
        width, height
      });
    }
    return pill.animate([
      {...pillFrame(from), easing:'cubic-bezier(.28,0,.5,1)'},
      {...pose(.38, stretch), offset:.34, easing:'cubic-bezier(.16,.65,.24,1)'},
      {...pose(1 + Math.min(.14, 6 / distance), -Math.min(4, stretch / 5), 1), offset:.76, easing:'ease-out'},
      pillFrame(to)
    ], {duration:340});
  }

  // Follow router state; layout-only changes place the pill without replaying the motion.
  if (typeof ResizeObserver !== 'undefined') {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    document.querySelectorAll('#sidebar, .diff-tabs').forEach(menu => {
      const pill = document.createElement('span');
      pill.className = 'selection-pill';
      pill.setAttribute('aria-hidden', 'true');
      pill.hidden = true;
      menu.prepend(pill);
      let selected, target, animation;
      const syncPill = () => {
        const active = menu.querySelector('button.active');
        const rect = active?.getBoundingClientRect();
        if (!rect?.width) {
          animation?.cancel();
          menu.classList.remove('has-selection-pill');
          pill.hidden = true;
          selected = target = null;
          return;
        }
        const bounds = menu.getBoundingClientRect();
        const box = r => ({
          x:r.left - bounds.left - menu.clientLeft + menu.scrollLeft,
          y:r.top - bounds.top - menu.clientTop + menu.scrollTop,
          width:r.width, height:r.height
        });
        const next = box(rect);
        if (selected === active && Object.keys(next).every(key => Math.abs(next[key] - target[key]) < .25)) return;
        const from = selected && selected !== active && !reducedMotion.matches && typeof pill.animate === 'function'
          ? box(pill.getBoundingClientRect()) : null;
        animation?.cancel();
        Object.assign(pill.style, pillFrame(next));
        pill.hidden = false;
        menu.classList.add('has-selection-pill');
        if (from) animation = slidePill(pill, from, next);
        selected = active;
        target = next;
      };
      reducedMotion.addEventListener?.('change', () => animation?.cancel());
      new MutationObserver(syncPill).observe(menu, {subtree:true, attributes:true, attributeFilter:['aria-current']});
      const size = new ResizeObserver(syncPill);
      size.observe(menu);
      menu.querySelectorAll('.nav-item, .diff-tab').forEach(button => size.observe(button));
      syncPill();
    });
  }
})();
