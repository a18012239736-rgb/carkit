import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_feedback_requires_public_consent_previews_only_selected_files_and_never_claims_submission():
    script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),nodes=[];
function element(tag) {
  const node={tagName:tag.toUpperCase(),value:'',checked:false,disabled:false,hidden:false,
    children:[],dataset:{},listeners:{},files:[],textContent:'',open:false,
    addEventListener(name,handler){(this.listeners[name]||=[]).push(handler);},
    setAttribute(name,value){this[name]=value;},focus(){},select(){},
    append(...children){children.forEach(child=>{child.parent=this;this.children.push(child);});},
    replaceChildren(...children){this.children=[];this.append(...children);},
    remove(){this.parent.children=this.parent.children.filter(child=>child!==this);},
    showModal(){this.open=true;},close(){this.open=false;}};
  Object.defineProperty(node,'innerHTML',{set(){throw new Error('Unsafe innerHTML');}});
  nodes.push(node);return node;
}
const body=element('body'),window={},document={body,createElement:element,
 getElementById:id=>nodes.find(node=>node.id===id)||null};
const entries=['btn-open-feedback','btn-open-feedback-sidebar'].map(id=>{const node=element('button');node.id=id;body.append(node);return node;});
let copied='',reads=0;
const navigator={clipboard:{async writeText(value){copied=value;}}};
class FileReader {readAsDataURL(file){reads++;this.result=file.data;this.onload();}}
const context={window,document,navigator,FileReader};vm.createContext(context);
vm.runInContext(fs.readFileSync('ui/feedback.js','utf8'),context);
const button=text=>nodes.find(node=>node.tagName==='BUTTON'&&node.textContent===text);
const fire=(node,event)=>Promise.all((node.listeners[event]||[]).map(handler=>handler({target:node})));
const submit=()=>button('准备反馈并前往GitHub');
(async()=>{
 await fire(entries[0],'click');const dialog=nodes.find(node=>node.tagName==='DIALOG');
 const title=nodes.find(node=>node.tagName==='INPUT'&&node.type==='text');
 const description=nodes.find(node=>node.tagName==='TEXTAREA');
 const consent=nodes.find(node=>node.tagName==='INPUT'&&node.type==='checkbox');
 const file=nodes.find(node=>node.tagName==='INPUT'&&node.type==='file');
 const state=nodes.find(node=>node.className==='feedback-state');
 assert(dialog.open);assert(submit().disabled);assert.strictEqual(reads,0);
 title.value='<img src=x onerror=alert(1)>';description.value='页面文字问题';
 await fire(title,'input');await fire(description,'input');assert(submit().disabled);
 consent.checked=true;await fire(consent,'change');assert(!submit().disabled);
 await fire(submit(),'click');assert(state.dataset.error==='true');assert(state.textContent.includes('浏览器预览'));
 title.value+='已补充';await fire(title,'input');assert.strictEqual(consent.checked,false);assert(submit().disabled);
 consent.checked=true;await fire(consent,'change');assert(!submit().disabled);
 let preparedPayload,resolvePrepare,opens=0,folders=0;
 window.pywebview={api:{
  prepare_feedback(payload){preparedPayload=payload;return new Promise(resolve=>resolvePrepare=resolve);},
  async open_feedback_issue(){opens++;return {ok:true};},
  async open_feedback_folder(){folders++;return {ok:true};}
 }};
 file.files=[{name:'选择的截图.png',size:20,type:'image/png',data:'data:image/png;base64,abc='}];
 await fire(file,'change');assert.strictEqual(reads,1);
 assert.strictEqual(consent.checked,false);assert(submit().disabled);
 consent.checked=true;await fire(consent,'change');assert(!submit().disabled);
 const preview=nodes.find(node=>node.tagName==='IMG');assert.strictEqual(preview.src,'data:image/png;base64,abc=');
 const pending=fire(submit(),'click');assert(submit().disabled);await fire(submit(),'click');
 assert.strictEqual(opens,0);assert.strictEqual(preparedPayload.title,title.value);
 assert.strictEqual(preparedPayload.images.length,1);assert.strictEqual(preparedPayload.images[0].name,'选择的截图.png');
 resolvePrepare({ok:true,has_images:true,requires_paste:true,body:'完整文字<script>not executed</script>'});await pending;
 assert.strictEqual(opens,1);assert(state.textContent.includes('尚未提交'));assert(state.textContent.includes('上传截图'));
 await fire(button('复制反馈正文'),'click');assert.strictEqual(copied,'完整文字<script>not executed</script>');
 await fire(button('打开反馈文件夹'),'click');assert.strictEqual(folders,1);
 description.value='下一次反馈';await fire(description,'input');assert(button('复制反馈正文').hidden);
 assert.strictEqual(consent.checked,false);assert(submit().disabled);
 consent.checked=true;await fire(consent,'change');assert(!submit().disabled);
 const currentImage=nodes.find(node=>node.className==='feedback-images').children[0];
 await fire(currentImage.children.find(node=>node.tagName==='BUTTON'),'click');
 assert.strictEqual(consent.checked,false);assert(submit().disabled);
 assert.strictEqual(nodes.find(node=>node.className==='feedback-images').children.length,0);
 await fire(button('关闭'),'click');assert.strictEqual(dialog.open,false);
 await fire(entries[1],'click');assert(dialog.open);assert.strictEqual(nodes.filter(node=>node.tagName==='DIALOG').length,1);
 assert.strictEqual(consent.checked,false);assert(submit().disabled);
 const previousReads=reads;file.files=[{name:'bad.svg',size:30,type:'image/svg+xml',data:'data:image/svg+xml;base64,abc='}];
 await fire(file,'change');assert.strictEqual(reads,previousReads);assert(state.textContent.includes('PNG/JPEG'));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script], cwd=ROOT, text=True,
                            encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stderr
