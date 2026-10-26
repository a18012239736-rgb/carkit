import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    harness = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('ui/app.js', 'utf8');
let document;
function element(tag = 'div', className = '', textContent = '') {
  const node = {tagName:tag.toUpperCase(),className,textContent,children:[],parentElement:null,
    disabled:false,open:false,scrolls:[],focusOptions:null};
  node.matches = selector => selector.startsWith('.')
    ? node.className.split(/\s+/).includes(selector.slice(1)) : node.tagName === selector.toUpperCase();
  node.querySelectorAll = selector => node.children.flatMap(child =>
    [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
  node.querySelector = selector => node.querySelectorAll(selector)[0] || null;
  node.remove = () => {
    if (!node.parentElement) return;
    const parent = node.parentElement;
    parent.children.splice(parent.children.indexOf(node), 1);node.parentElement = null;
  };
  node.insertBefore = (child, before) => {
    assert(before === null || before.parentElement === node, 'valid insertion target');
    child.remove();
    const index = before === null ? node.children.length : node.children.indexOf(before);
    node.children.splice(index, 0, child);child.parentElement = node;
  };
  node.append = (...children) => children.forEach(child => node.insertBefore(child, null));
  node.prepend = child => node.insertBefore(child, node.children[0] || null);
  node.focus = options => {document.activeElement = node;node.focusOptions = options;};
  node.scrollIntoView = options => node.scrolls.push(options);
  node.click = () => {if (!node.disabled && node.onclick) node.onclick({target:node});};
  for (const [property, offset] of [['previousElementSibling', -1], ['nextElementSibling', 1]]) {
    Object.defineProperty(node, property, {get() {
      if (!node.parentElement) return null;
      return node.parentElement.children[node.parentElement.children.indexOf(node) + offset] || null;
    }});
  }
  return node;
}
document = {activeElement:null, createElement:tag => element(tag)};
const stage = Object.freeze({model:'测试车',trims:Object.freeze(['甲','乙','丙'])});
const plan = Object.freeze([{target:0,base:null},{target:1,base:0},{target:2,base:1}]);
const result = Object.freeze({columns:Object.freeze(['甲','乙','丙'])});
const context = {document,ST:Object.freeze({stage}),
  stagePlan:()=>assert.fail('card moves must not rebuild the trim plan'),
  api:()=>assert.fail('card moves must not write/export/recalculate'),res:result};
vm.createContext(context);
const start = source.indexOf('function enableLadderCardMoves(');
const end = source.indexOf("$('#stage-trim-editor').addEventListener", start);
assert(start >= 0 && end > start, 'production helper boundaries');
vm.runInContext(source.slice(start, end), context);
function preview(count = 3) {
  const panel = element(), columns = element('div', 'ladder-columns');panel.append(columns);
  const cards = Array.from({length:count}, (_, i) => {
    const card = element('article', 'ladder-column' + (i === 0 ? ' is-base' : ''));
    card.name = ['甲','乙','丙','丁'][i];
    const badge = element('span','ladder-badge', i === 0 ? '基础版型' : '差异配置');
    const heading = element('h4','',card.name), price = element('div','ladder-price',String(10+i));
    const basis = element('strong','',i === 0 ? '基本配置：' : ['甲','乙'][i-1] + '+：');
    const item = element('li','',card.name + '配置'), list = element('ul');list.append(item);
    const details = element('details');details.open = i === 1;
    details.append(element('summary','','选装配置'), element('ul','','选配原文'));
    card.append(badge, heading, price, basis, list, details);columns.append(card);
    card.original = {badge, heading, price, basis, list, item, details};
    return card;
  });
  context.enableLadderCardMoves(panel);
  return {panel,columns,cards};
}
const controls = card => card.querySelector('.ladder-card-actions').querySelectorAll('button');
const order = columns => columns.children.map(card => card.name);
const plain = value => JSON.parse(JSON.stringify(value));
"""
    result = subprocess.run(
        ['node', '-e', harness + '\n' + script], cwd=ROOT,
        text=True, encoding='utf-8', capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_left_and_right_moves_swap_only_adjacent_cards_and_refresh_boundaries():
    run_node(r"""
const {columns,cards:[a,b,c]} = preview();
assert(controls(a)[0].disabled);assert(!controls(a)[1].disabled);
assert(!controls(b)[0].disabled && !controls(b)[1].disabled);
assert(!controls(c)[0].disabled && controls(c)[1].disabled);
controls(b)[0].click();assert.deepStrictEqual(order(columns),['乙','甲','丙']);
assert(controls(b)[0].disabled);assert(!controls(a)[0].disabled);
controls(b)[1].click();assert.deepStrictEqual(order(columns),['甲','乙','丙']);
controls(b)[1].click();assert.deepStrictEqual(order(columns),['甲','丙','乙']);
assert(controls(b)[1].disabled);assert(!controls(c)[1].disabled);
controls(b)[0].click();assert.deepStrictEqual(order(columns),['甲','乙','丙']);
controls(a)[0].click();controls(c)[1].click();
assert.deepStrictEqual(order(columns),['甲','乙','丙'],'disabled edges do not move');
""")


def test_card_content_optional_expansion_and_comparison_basis_are_not_rebuilt():
    run_node(r"""
const {columns,cards} = preview();
assert.deepStrictEqual(cards.map(card => card.original.basis.textContent),['基本配置：','甲+：','乙+：']);
const original = cards.map(card => ({children:card.children.slice(),basis:card.original.basis.textContent,
  price:card.original.price.textContent,open:card.original.details.open,className:card.className}));
controls(cards[1])[0].click();controls(cards[1])[1].click();controls(cards[0])[1].click();
cards.forEach((card,i) => {
  assert.deepStrictEqual(card.children,original[i].children,'existing content nodes retained');
  assert.strictEqual(card.original.basis.textContent,original[i].basis);
  assert.strictEqual(card.original.price.textContent,original[i].price);
  assert.strictEqual(card.original.details.open,original[i].open);
  assert.strictEqual(card.original.list.children[0],card.original.item);
  assert.strictEqual(card.className,original[i].className,'base designation is not positional');
});
assert.deepStrictEqual(plain(context.ST.stage),{model:'测试车',trims:['甲','乙','丙']});
assert.deepStrictEqual(plain(plan),[{target:0,base:null},{target:1,base:0},{target:2,base:1}]);
assert.deepStrictEqual(plain(context.res),{columns:['甲','乙','丙']});
""")


def test_preview_uses_compact_basis_labels_and_escapes_trim_names_without_mutation():
    run_node(r"""
const renderStart = source.indexOf('previewButton.onclick = async () => {');
const markupStart = source.indexOf('  const list = ',renderStart);
const markupEnd = source.indexOf("\n  panel.querySelector('.ladder-heading h2')",markupStart);
const markup = source.slice(markupStart,markupEnd).replace('panel.innerHTML = ', 'return ');
const escapeDefinition = source.match(/^const esc = .*;$/m)[0];
vm.runInContext(escapeDefinition,context);
const columns = [
  {name:'基本型',base:null,price:7.48,items:[],options:[]},
  {name:'未指定基准',price:null,items:[],options:[]},
  {name:'升级型',base:'650 舒享版',price:8.48,items:['座椅通风'],options:[]},
  {name:'<新款> & "限定"',base:'<基础> & "版型"',price:9.48,items:[],options:[]},
];
context.res = {model:'测试车',columns};
const before = JSON.stringify(context.res);
const html = vm.runInContext(`(() => {${markup}})()`,context);
const labels = [...html.matchAll(/<strong(?:\s[^>]*)?>(.*?)<\/strong>/g)].map(match => match[1]);
assert.deepStrictEqual(labels,['基本配置：','基本配置：','650 舒享版+：','&lt;基础&gt; &amp; &quot;版型&quot;+：']);
assert(html.includes('&lt;新款&gt; &amp; &quot;限定&quot;'));
assert(!html.includes('相对 '));
assert(!html.includes('<基础>'));assert(!html.includes('<新款>'));
assert.strictEqual(JSON.stringify(context.res),before,'labels do not change comparison bases or export data');
""")


def test_focus_follows_moved_card_and_uses_enabled_control_at_the_edges():
    run_node(r"""
const {cards:[a,b,c]} = preview();
const [left,right] = controls(b);
left.click();assert.strictEqual(document.activeElement,right,'new first card focuses enabled direction');
assert.deepStrictEqual(plain(right.focusOptions),{preventScroll:true});
assert.deepStrictEqual(plain(right.scrolls[0]),{behavior:'smooth',block:'nearest',inline:'nearest'});
right.click();assert.strictEqual(document.activeElement,right,'middle card keeps clicked direction');
right.click();assert.strictEqual(document.activeElement,left,'new last card focuses enabled direction');
assert.deepStrictEqual(plain(left.scrolls[0]),{behavior:'smooth',block:'nearest',inline:'nearest'});
""")


def test_controls_have_accessible_names_and_keep_the_original_badge():
    run_node(r"""
const {cards} = preview();
for(const card of cards) {
  const [left,right] = controls(card);
  assert.strictEqual(left.type,'button');assert.strictEqual(right.type,'button');
  assert(left.ariaLabel.includes(card.name) && left.ariaLabel.includes('左移'));
  assert(right.ariaLabel.includes(card.name) && right.ariaLabel.includes('右移'));
  assert.strictEqual(left.title,left.ariaLabel);assert.strictEqual(right.title,right.ariaLabel);
  assert.strictEqual(card.querySelectorAll('.ladder-badge').length,1);
  assert.strictEqual(card.querySelector('.ladder-badge'),card.original.badge);
}
""")


def test_empty_single_and_replaced_previews_do_not_share_card_state():
    run_node(r"""
for(const count of [0,1]) {
  const {panel,cards} = preview(count);
  assert.strictEqual(panel.querySelectorAll('button').length,0);
  if(count) assert.strictEqual(cards[0].children[0],cards[0].original.badge);
}
const old = preview(), fresh = preview();
controls(old.cards[1])[0].click();
assert.deepStrictEqual(order(old.columns),['乙','甲','丙']);
assert.deepStrictEqual(order(fresh.columns),['甲','乙','丙']);
controls(fresh.cards[1])[1].click();
assert.deepStrictEqual(order(old.columns),['乙','甲','丙']);
assert.deepStrictEqual(order(fresh.columns),['甲','丙','乙']);
""")
