"""Regression tests for Option A UI polish (metrics, KPI cards, ladder deltas, editor dirty state, CSS)."""
from pathlib import Path

from test_frontend_comparison_state import run_node


ROOT = Path(__file__).resolve().parents[1]


def test_backup_metrics_and_kpi_strip_use_semantic_positive_and_negative_classes():
    run_node(r"""
load('const esc =', '/* ---------- ③ 快照');
load('function renderDiff(', '$("#btn-export-result").addEventListener');
const tableRows = Array.from({length: 6}, () => {
  const classes = new Set();
  const tds = [0, 1, 2, 3].map(() => {
    const tdClasses = new Set();
    return {classList: {add: c => tdClasses.add(c), has: c => tdClasses.has(c)}};
  });
  return {
    classList: {add: c => classes.add(c), has: c => classes.has(c)},
    querySelectorAll: sel => (sel === 'td' ? tds : []),
    tds,
  };
});
const backupContainer = {
  innerHTML: '',
  querySelectorAll: sel => (sel === 'table.backup-table tbody tr' ? tableRows : []),
};
const origDollar = context.$;
context.$ = selector => {
  if (selector === '#backup-table') return backupContainer;
  return origDollar(selector);
};
node('#diff-mode').value = 'self';
const groups = [
  {pair: {self_trim: '<胜出>', comp_trim: '对手A'}, self_price: 10, comp_price: 11,
   more: ['座椅加热'], less: [], valuation: {config_adv: 2400, flat_adv: 12400, overall: 3500, detail: []}},
  {pair: {self_trim: '落后型', comp_trim: '对手B'}, self_price: 12, comp_price: 11,
   more: [], less: ['HUD', '激光雷达'], valuation: {config_adv: -1800, flat_adv: -11800, overall: -800, detail: []}},
  {pair: {self_trim: '持平型', comp_trim: '对手C'}, self_price: 10, comp_price: 10,
   more: [], less: [], valuation: {config_adv: 0, flat_adv: 0, overall: 0, detail: []}},
  {pair: {self_trim: '待补型', comp_trim: '对手D'}, self_price: null, comp_price: null,
   more: [], less: [], valuation: {config_adv: null, flat_adv: null, overall: null, detail: []}},
];
context.renderDiff({ok: true, self_model: '本品', comp_model: '竞品', groups, cells: []});

assert(tableRows[5].classList.has('backup-overall-row'));
// Row 3 = config_adv, Row 4 = flat_adv, Row 5 = overall
assert(tableRows[3].tds[0].classList.has('metric-pos'));
assert(tableRows[3].tds[1].classList.has('metric-neg'));
assert(tableRows[3].tds[2].classList.has('metric-zero'));
assert(tableRows[5].tds[0].classList.has('metric-pos'));
assert(tableRows[5].tds[1].classList.has('metric-neg'));
assert(!tableRows[5].tds[1].classList.has('metric-pos'));
assert(tableRows[5].tds[2].classList.has('metric-zero'));
assert(tableRows[5].tds[3].classList.has('metric-pending'));

const kpi = node('#diff-kpi-strip');
assert.strictEqual(kpi.hidden, false);
assert(kpi.innerHTML.includes('class="diff-kpi-card is-pos"'));
assert(kpi.innerHTML.includes('class="diff-kpi-card is-neg"'));
assert(kpi.innerHTML.includes('class="diff-kpi-card is-zero"'));
assert(kpi.innerHTML.includes('class="diff-kpi-card is-pending"'));
assert(kpi.innerHTML.includes('&lt;胜出&gt; vs 对手A'));
assert(!kpi.innerHTML.includes('<胜出>'));
""")


def test_ladder_preview_renders_semantic_items_option_count_and_price_deltas():
    run_node(r"""
function makeEl(tag = 'div', className = '') {
  const el = {
    tagName: tag.toUpperCase(), className, textContent: '', title: '',
    children: [], parentElement: null,
    classList: {
      toggle(c, on) {
        const set = new Set(el.className.split(/\s+/).filter(Boolean));
        if (on) set.add(c); else set.delete(c);
        el.className = [...set].join(' ');
      },
      contains: c => el.className.split(/\s+/).includes(c),
    },
    append(...kids) { kids.forEach(k => { el.children.push(k); k.parentElement = el; }); },
    prepend(k) { el.children.unshift(k); k.parentElement = el; },
    querySelectorAll(sel) {
      if (sel === '.ladder-column') return this._cards || [];
      return [];
    },
    querySelector(sel) {
      if (sel === '.ladder-heading h2') return (this._heading ||= makeEl('h2'));
      if (sel === '.ladder-model') return (this._model ||= makeEl('h3'));
      if (sel === '.ladder-price') return this._priceEl;
      if (sel === '.ladder-badge') return this._badgeEl;
      if (sel === 'h4') return this._h4;
      if (sel === '.close-ladder') return (this._close ||= makeEl('button'));
      if (sel === '.ladder-scroll') return (this._scroll ||= {scrollLeft: 0});
      return null;
    },
    scrollIntoView() {},
    addEventListener() {},
  };
  return el;
}

const renderStart = source.indexOf('previewButton.onclick = async () => {');
const markupStart = source.indexOf('  const list = ', renderStart);
const postLoopEnd = source.indexOf('  enableLadderCardMoves(', markupStart);
const block = source.slice(markupStart, postLoopEnd);

const columns = [
  {name: '基础型', base: null, price: 10.0, items: ['LED大灯', '360影像'], options: ['天窗包']},
  {name: '高配型', base: '基础型', price: 11.0, items: ['座椅加热', '全液晶8.8寸仪表（原4寸仪表）'], removed_items: ['卤素雾灯'], options: ['智驾包', '音响包']},
  {name: '特惠型', base: '基础型', price: 9.5, items: ['配置相同，仅价格/续航差异。'], options: []},
  {name: '平价型', base: '基础型', price: 10.0, items: ['真皮方向盘'], options: []},
];
const cards = columns.map(() => {
  const card = makeEl('article', 'ladder-column');
  card._priceEl = makeEl('div', 'ladder-price');
  card._h4 = makeEl('h4');
  return card;
});
const panel = makeEl('section');
panel._cards = cards;

const ctx = {
  document: {createElement: tag => makeEl(tag)},
  esc: context.esc,
  res: {model: '测试车', columns},
  panel,
};
vm.createContext(ctx);
vm.runInContext(block, ctx);

assert(!panel.innerHTML.includes('ladder-marker'));
assert(panel.innerHTML.includes('class="ladder-item-added"'));
assert(panel.innerHTML.includes('class="ladder-item-upgraded"'));
assert(panel.innerHTML.includes('<span class="ladder-item-old">（原4寸仪表）</span>'));
assert(panel.innerHTML.includes('class="ladder-item-removed"'));
assert(panel.innerHTML.includes('class="ladder-section-removed">基础型-：</strong>'));
assert(panel.innerHTML.includes('<span class="ladder-option-count">2 项</span>'));

const deltaPills = cards.map(c => c._priceEl.children.find(k => k.className.includes('ladder-price-delta')));
assert.strictEqual(deltaPills[0], undefined);
assert.strictEqual(deltaPills[1].textContent, '+1.00 万');
assert(deltaPills[1].className.includes('is-up'));
assert.strictEqual(deltaPills[2].textContent, '-0.50 万');
assert(deltaPills[2].className.includes('is-down'));
assert.strictEqual(deltaPills[3].textContent, '同价');
assert(deltaPills[3].className.includes('is-even'));
""")


def test_config_editor_tracks_dirty_cells_and_group_counts_without_mutating_model():
    run_node(r"""
let definition;
context.Vue = {
  ref: value => ({value}),
  computed: get => ({get value() { return get(); }}),
  watch() {},
  createApp: options => { definition = options; return {mount() {}, unmount() {}}; },
};
vm.runInContext(fs.readFileSync('ui/config-editor.js', 'utf8'), context);
const model = {
  trims: [{name: '基础型', price_guide: 10.5}, {name: '高配型', price_guide: 11.5}],
  cells: [
    {no: 7, values: {基础型: '360影像', 高配型: '540影像'}},
    {no: 36, values: {基础型: {主驾加热: '✕'}, 高配型: {主驾加热: '●'}}},
  ],
};
const root = {classList: {add() {}, remove() {}}};
context.window.ConfigEditor.mount(root, {
  model, kind: 'snapshot', review: true, choices: () => [],
  parseSeatAdjust: async () => ({ok: false}),
  updateSnapshot(m, no, trim, val, sub) {
    const cell = m.cells.find(c => c.no === no);
    if (sub) { cell.values[trim] ||= {}; cell.values[trim][sub] = val; }
    else cell.values[trim] = val;
  },
  cascade: (_, edited) => edited,
  onChange() {},
});
const editor = definition.setup();
assert(definition.template.includes('ce-group-count'));
assert(definition.template.includes("'ce-dirty':isDirty(row,i)"));
assert(definition.template.includes("'ce-dirty':isMetaDirty('price',i)"));
assert(definition.template.includes("'ce-dirty':isMetaDirty('options',i)"));

const row7 = editor.rows.value.find(r => r.cell.no === 7);
const row36 = editor.rows.value.find(r => r.key === '36-加热');
assert.strictEqual(editor.isDirty(row7, 0), false);
assert.strictEqual(editor.isDirty(row36, 0), false);

editor.change(row7.cell, 0, '', '540影像');
assert.strictEqual(editor.isDirty(row7, 0), true);
assert.strictEqual(editor.isDirty(row7, 1), false);

editor.change(row36.cell, 0, '主驾加热', '●');
assert.strictEqual(editor.isDirty(row36, 0), true);

editor.price(1, {target: {value: '11.98', setCustomValidity() {}, reportValidity() {}}});
assert.strictEqual(editor.isMetaDirty('price', 1), true);
assert.strictEqual(editor.isMetaDirty('price', 0), false);

editor.options(0, '天窗选装包');
assert.strictEqual(editor.isMetaDirty('options', 0), true);
assert(!('dirty' in row7.cell) && !('dirty' in model.trims[0]));
""")


def test_css_hierarchy_and_settings_alignment_rules():
    style_css = (ROOT / 'ui' / 'style.css').read_text(encoding='utf-8')
    workspace_css = (ROOT / 'ui' / 'workspace.css').read_text(encoding='utf-8')
    config_css = (ROOT / 'ui' / 'config-editor.css').read_text(encoding='utf-8')

    # Hardcoded green row-6 tint removed; replaced by semantic metric classes.
    assert 'tr:nth-child(6) td { background:var(--accent-soft)' not in style_css
    assert '.metric-pos' in style_css and '.metric-neg' in style_css
    assert '.diff-kpi-card.is-neg' in style_css

    # #main no longer sits inside the frosted glass panel selector.
    assert '#main,.card,' not in workspace_css
    assert '#main {\n  grid-column:1;' in workspace_css
    assert '#page-settings.active { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; align-items:stretch; }' in workspace_css
    assert '.ce-dirty' in config_css and '.ce-group-count' in config_css
