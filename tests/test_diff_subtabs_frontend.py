"""Exercise subtab routes with the production page router and lexical app state."""
import subprocess
from pathlib import Path

from lxml import html


ROOT = Path(__file__).resolve().parents[1]


def run_navigation(script):
    harness = r"""
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const context={assert};context.window=context;vm.createContext(context);
const app=fs.readFileSync('ui/app.js','utf8');
const start=app.indexOf('function showPage(name) {');
const router=app.slice(start,app.indexOf('async function selectCompetitor()',start));
const setup=`
const ST={plan:null}, calls={rules:0,compare:0,scroll:0}, notices=[];
function element(id,dataset={},active=false) {
  const classes=new Set(active?['active']:[]);
  return {id,dataset,attributes:{},listeners:{},
    classList:{contains:key=>classes.has(key),toggle(key,on){on?classes.add(key):classes.delete(key);}},
    setAttribute(key,value){this.attributes[key]=value;},
    removeAttribute(key){delete this.attributes[key];},
    addEventListener(type,fn){this.listeners[type]=fn;}};
}
const pages=['scrape','diff','settings'].map(name=>element('page-'+name,{},name==='scrape'));
const subs=['compare','snapshot','valuation'].map(name=>element('diff-sub-'+name,{sub:name},name==='compare'));
const tabs=['compare','snapshot','valuation'].map(name=>element('',{sub:name},name==='compare'));
const navs=['scrape','diff','settings'].map(name=>element('',{page:name},name==='scrape'));
const importButton=element('',{subGoto:'snapshot'});
const selectors={'.page':pages,'.diff-sub':subs,'.diff-tab':tabs,'.nav-item':navs,'[data-sub-goto]':[importButton]};
const document={querySelectorAll:s=>selectors[s]||[],querySelector:s=>s==='#page-diff'?pages[1]:null};
const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
function toast(message){notices.push(message);}
function loadCurrentValuation(){calls.rules++;}
function refreshDiffSelects(){calls.compare++;}
window.scrollTo=()=>calls.scroll++;
`;
vm.runInContext(setup+router+fs.readFileSync('ui/diff-subtabs.js','utf8')+process.argv[1],context);
"""
    result = subprocess.run(
        ['node', '-e', harness, script], cwd=ROOT,
        capture_output=True, text=True, encoding='utf-8',
    )
    assert result.returncode == 0, result.stderr


def test_import_and_return_routes_keep_comparison_page_and_navigation_active():
    run_navigation(r"""
importButton.listeners.click();
assert(pages[1].classList.contains('active'));
assert(!pages[0].classList.contains('active'));
assert(subs[1].classList.contains('active'));
assert.strictEqual(navs[1].attributes['aria-current'],'page');
assert.strictEqual(tabs[1].attributes['aria-current'],'true');
showPage('diff');
assert(subs[0].classList.contains('active'));
assert(!subs[1].classList.contains('active'));
assert.strictEqual(tabs[0].attributes['aria-current'],'true');
assert(!('aria-current' in tabs[1].attributes));
showPage('snapshot');
assert(subs[1].classList.contains('active'));
showPage('settings');
assert(pages[2].classList.contains('active'));
showPage('diff');
assert(pages[1].classList.contains('active'));
assert(subs[0].classList.contains('active'));
""")


def test_rules_tab_and_existing_rules_route_respect_saved_plan_state():
    run_navigation(r"""
assert.strictEqual(window.ST,undefined); // App state is a global lexical const.
ST.plan={session:'saved-plan'};
tabs[2].listeners.click();
assert(subs[0].classList.contains('active'));
assert(!subs[2].classList.contains('active'));
assert(pages[0].classList.contains('active'));
assert.strictEqual(calls.rules,0);
assert(notices[0].includes('先退出方案'));
showPage('valuation');
assert(!subs[2].classList.contains('active'));
assert.strictEqual(calls.rules,0);
ST.plan=null;
showPage('valuation');
assert(pages[1].classList.contains('active'));
assert(subs[2].classList.contains('active'));
assert.strictEqual(calls.rules,1);
tabs[0].listeners.click();
assert(subs[0].classList.contains('active'));
assert.strictEqual(calls.compare,1);
""")


def test_nested_panels_and_return_button_have_unique_ids_and_load_after_router():
    root = html.fromstring((ROOT / 'ui/index.html').read_text(encoding='utf-8'))
    identifiers = root.xpath('//*[@id]/@id')
    assert len(identifiers) == len(set(identifiers))
    for panel in ('snapshot', 'valuation'):
        matches = root.xpath(f'//*[@id="diff-sub-{panel}"]')
        assert len(matches) == 1
        assert matches[0].xpath('ancestor::*[@id="page-diff"]')
    back = root.xpath('//*[@id="diff-close-valuation"]')
    assert len(back) == 1
    assert back[0].xpath('ancestor::*[@id="diff-sub-valuation"]')
    scripts = [src.split('?')[0] for src in root.xpath('//script/@src')]
    assert scripts.index('app.js') < scripts.index('diff-subtabs.js')
