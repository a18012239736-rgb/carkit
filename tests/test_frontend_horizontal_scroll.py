import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    harness = r"""
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const source=fs.readFileSync('ui/app.js','utf8'), ids=new Map(), frames=[], mutations=[], resizes=[];
let document;
function events(object) {
  object.listeners={};
  object.addEventListener=(name,callback,options)=>(object.listeners[name] ||= []).push({callback,options});
  return object;
}
function emit(object,name,target=object) {
  for(const {callback} of object.listeners[name]||[])callback({target});
}
function element(tag='div',id='',className='') {
  const el=events({tagName:tag.toUpperCase(),className,hidden:false,style:{},children:[],parentElement:null,
    attrs:{},scrollWidth:1800,clientWidth:600,scrollLeft:0,replacements:0,
    rect:{left:204,right:804,top:100,bottom:600,width:600,height:500}});
  let currentId='';
  Object.defineProperty(el,'id',{get:()=>currentId,set(value){ids.delete(currentId);currentId=value;if(value)ids.set(value,el);}});
  el.id=id;
  for(const property of ['value','max','min','step']) {
    let value='';Object.defineProperty(el,property,{get:()=>value,set(next){value=String(next);}});
  }
  el.classList={contains:name=>el.className.split(/\s+/).includes(name),toggle(name,force){
    const names=new Set(el.className.split(/\s+/).filter(Boolean));
    const add=force===undefined?!names.has(name):force;add?names.add(name):names.delete(name);el.className=[...names].join(' ');
  }};
  el.append=(...children)=>{for(const child of children){child.parentElement=el;el.children.push(child);}};
  el.replaceChildren=(...children)=>{el.replacements++;for(const child of el.children)child.parentElement=null;el.children=[];el.append(...children);};
  el.remove=()=>{el.parentElement.children=el.parentElement.children.filter(child=>child!==el);el.parentElement=null;};
  el.setAttribute=(name,value)=>{el.attrs[name]=String(value);if(name==='id')el.id=value;};
  el.getAttribute=name=>el.attrs[name]??null;
  el.matches=selector=>selector.split(',').some(part=>{
    const s=part.trim();return s.startsWith('.')?el.classList.contains(s.slice(1)):s.startsWith('#')?el.id===s.slice(1):el.tagName===s.toUpperCase();
  });
  el.closest=selector=>{for(let node=el;node;node=node.parentElement)if(node.matches(selector))return node;return null;};
  el.querySelectorAll=selector=>el.children.flatMap(child=>[...(child.matches(selector)?[child]:[]),...child.querySelectorAll(selector)]);
  el.querySelector=selector=>el.querySelectorAll(selector)[0]||null;
  el.getBoundingClientRect=()=>{
    for(let node=el;node;node=node.parentElement)if(node.hidden||node.style.display==='none')return {left:0,right:0,top:0,bottom:0,width:0,height:0};
    return el.rect;
  };
  el.focus=()=>{document.activeElement=el;};
  Object.defineProperty(el,'firstElementChild',{get:()=>el.children[0]||null});
  Object.defineProperty(el,'innerHTML',{set(html){
    for(const match of html.matchAll(/<(span|select|input)\b([^>]*)>([^<]*)/g)) {
      const child=element(match[1]);child.textContent=match[3];
      for(const attr of match[2].matchAll(/([\w-]+)="([^"]*)"/g)) {
        child.setAttribute(attr[1],attr[2]);if(['min','step','type'].includes(attr[1]))child[attr[1]]=attr[2];
      }
      el.append(child);
    }
  }});
  return el;
}
const body=element('body'), main=element('main','main');body.append(main);
main.rect={left:184,right:1260,top:0,bottom:2000,width:1076,height:2000};
document=events({body,activeElement:body,getElementById:id=>ids.get(id)||null,createElement:tag=>element(tag)});
const window=events({innerWidth:1280,innerHeight:800});
class MutationObserver {constructor(callback){this.callback=callback;mutations.push(this);}observe(target,options){this.target=target;this.options=options;}}
class ResizeObserver {constructor(callback){this.callback=callback;this.targets=[];resizes.push(this);}disconnect(){this.targets=[];}observe(target){this.targets.push(target);}}
const context={document,window,MutationObserver,ResizeObserver,requestAnimationFrame:callback=>frames.push(callback)};
vm.createContext(context);
const start=source.indexOf('function mountFloatingScroll()'), end=source.lastIndexOf('\nmountFloatingScroll();');
assert(start>=0&&end>start,'production controller boundaries');
vm.runInContext(source.slice(start,end)+'\nmountFloatingScroll();',context);
function flush(){let count=0;while(frames.length){assert(++count<20,'RAF update loop');frames.shift()();}}
function refresh(){mutations[0].callback([]);flush();}
function region(id='raw-inspector',className='table-wrap',parent=main) {
  const target=element('div',id,className);target.append(element('table'));parent.append(target);return target;
}
flush();
const bar=ids.get('floating-scroll'), select=ids.get('floating-scroll-target'), range=ids.get('floating-scroll-range');
assert(bar&&select&&range);
"""
    result = subprocess.run(['node', '-e', harness + '\n' + script], cwd=ROOT,
                            text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr


def test_range_and_native_scrolling_synchronize_both_directions():
    run_node(r"""
const target=region();target.scrollLeft=135;refresh();
assert(!bar.hidden);assert(select.hidden);assert.strictEqual(Number(range.max),1200);
assert.strictEqual(Number(range.value),135);
range.value=650;emit(range,'input');assert.strictEqual(target.scrollLeft,650);
target.scrollLeft=910;emit(document,'scroll',target);flush();assert.strictEqual(Number(range.value),910);
assert.strictEqual(document.listeners.scroll[0].options,true,'native container scroll is captured');
assert(body.classList.contains('has-floating-scroll'));
""")


def test_named_region_selector_and_content_pointer_or_focus_choose_target():
    run_node(r"""
const first=region(),second=region('detail-table');second.scrollWidth=2400;second.scrollLeft=310;refresh();
assert(!select.hidden);assert.deepStrictEqual(select.children.map(o=>o.textContent),['完整配置','配置判定明细']);
select.value=second.id;emit(select,'change');assert.strictEqual(Number(range.max),1800);
assert.strictEqual(Number(range.value),310);range.value=720;emit(range,'input');
assert.strictEqual(second.scrollLeft,720);assert.strictEqual(first.scrollLeft,0);
emit(main,'pointerdown',first.firstElementChild);assert.strictEqual(select.value,first.id);
emit(main,'focusin',second.firstElementChild);assert.strictEqual(select.value,second.id);
assert.strictEqual(range.getAttribute('aria-controls'),second.id);
""")


def test_no_overflow_hidden_ancestors_and_offscreen_content_hide_toolbar():
    run_node(r"""
assert(bar.hidden);assert(!body.classList.contains('has-floating-scroll'));
const page=element('section');main.append(page);const target=region('raw-inspector','table-wrap',page);refresh();
assert(!bar.hidden);target.scrollWidth=target.clientWidth;refresh();assert(bar.hidden);
target.scrollWidth=1800;page.hidden=true;refresh();assert(bar.hidden);
page.hidden=false;target.rect.top=800;target.rect.bottom=1300;refresh();assert(bar.hidden);
target.rect.top=-600;target.rect.bottom=-100;refresh();assert(bar.hidden);
target.rect.top=100;target.rect.bottom=600;target.rect.left=1300;target.rect.right=1900;refresh();assert(bar.hidden);
target.rect.left=204;target.rect.right=804;refresh();assert(!bar.hidden);
page.hidden=true;refresh();const old=target.scrollLeft;range.value=900;emit(range,'input');
assert.strictEqual(target.scrollLeft,old,'hidden target must no longer receive input');
assert(!body.classList.contains('has-floating-scroll'));
""")


def test_removed_region_is_replaced_by_new_preview_without_stale_scroll_binding():
    run_node(r"""
const old=region('', 'ladder-scroll');refresh();const oldId=old.id;assert(oldId);
range.value=420;emit(range,'input');old.remove();refresh();assert(bar.hidden);
range.value=600;emit(range,'input');assert.strictEqual(old.scrollLeft,420);
const next=region('', 'ladder-scroll');next.scrollWidth=2100;refresh();
assert(!bar.hidden);assert(next.id&&next.id!==oldId);
assert.strictEqual(range.getAttribute('aria-controls'),next.id);assert.strictEqual(Number(range.max),1500);
range.value=330;emit(range,'input');assert.strictEqual(next.scrollLeft,330);assert.strictEqual(old.scrollLeft,420);
assert(!resizes[0].targets.includes(old));assert(resizes[0].targets.includes(next.firstElementChild));
""")


def test_resize_and_content_changes_recalculate_full_range_without_sticky_column_deduction():
    run_node(r"""
const target=region('detail-table');refresh();assert.strictEqual(Number(range.max),1200);
assert(resizes[0].targets.includes(main)&&resizes[0].targets.includes(target)&&resizes[0].targets.includes(target.firstElementChild));
target.scrollWidth=3000;resizes[0].callback([]);flush();assert.strictEqual(Number(range.max),2400);
target.clientWidth=900;emit(window,'resize');flush();assert.strictEqual(Number(range.max),2100);
target.clientWidth=3000;emit(window,'resize');flush();assert(bar.hidden);
target.clientWidth=900;refresh();assert(!bar.hidden);
""")


def test_repeated_updates_keep_user_choice_focus_and_existing_options():
    run_node(r"""
const first=region(),second=region('detail-table');refresh();
select.value=second.id;emit(select,'change');range.value=490;emit(range,'input');range.focus();
const replacements=select.replacements, options=select.children.slice();
for(let i=0;i<3;i++){mutations[0].callback([]);resizes[0].callback([]);emit(document,'scroll',first);}
assert.strictEqual(frames.length,1,'repeated changes coalesce');flush();
assert.strictEqual(select.value,second.id);assert.strictEqual(Number(range.value),490);
assert.strictEqual(document.activeElement,range);assert.strictEqual(select.replacements,replacements);
assert.deepStrictEqual(select.children,options);assert.strictEqual(range.getAttribute('aria-controls'),second.id);
""")


def test_accessible_native_range_and_names_follow_current_region():
    run_node(r"""
const target=region('', 'ladder-scroll');refresh();
assert.strictEqual(bar.getAttribute('role'),'group');assert(bar.getAttribute('aria-label').includes('横向'));
assert(select.getAttribute('aria-label').includes('区域'));
assert.strictEqual(range.type,'range');assert.strictEqual(Number(range.min),0);assert.strictEqual(Number(range.step),1);
assert(range.getAttribute('aria-label').includes('左右'));assert.strictEqual(range.getAttribute('aria-controls'),target.id);
range.value=600;emit(range,'input');assert(range.getAttribute('aria-valuetext').includes('配置阶梯'));
assert(range.getAttribute('aria-valuetext').includes('50%'));
assert.strictEqual(mutations[0].target,main,'toolbar is outside its mutation observer');
assert.deepStrictEqual(Array.from(mutations[0].options.attributeFilter),['hidden','class','style']);
""")
