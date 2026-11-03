"""Exercise update UI actions against the production controller without a browser."""
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(script):
    harness = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Map(),timers=new Map(),listeners={},calls=[];let timerId=0,page='';
function node(id) {
  if(!nodes.has(id)) {
    const classes=new Set(),el={hidden:false,disabled:false,textContent:'',value:0,listeners:{},
      addEventListener(type,callback){this.listeners[type]=callback;},
      removeAttribute(name){delete this[name];},scrollIntoView(){this.scrolled=true;},
      classList:{toggle(name,on){on?classes.add(name):classes.delete(name);},contains:name=>classes.has(name)}};
    Object.defineProperty(el,'innerHTML',{set(){throw new Error('Remote update content must remain plain text');}});
    nodes.set(id,el);
  }
  return nodes.get(id);
}
let approveInstall=true;
const confirmations=[];
const window={addEventListener(type,callback){listeners[type]=callback;},
  confirm(message){confirmations.push(message);return approveInstall;}};
const context={window,document:{getElementById:node},showPage:name=>page=name,
  setInterval(callback){timers.set(++timerId,callback);return timerId;},clearInterval:id=>timers.delete(id)};
vm.createContext(context);
function load(api,ready=false) {
  if(ready)window.pywebview={api};
  vm.runInContext(fs.readFileSync('ui/app-updates.js','utf8'),context);
  if(!ready&&api){window.pywebview={api};listeners.pywebviewready();}
}
const latest=(extra={})=>({ok:true,current_version:'0.2.3',latest_version:'0.2.4',
  available:true,same_version:false,supported:true,can_download:true,
  release_notes:'<img src=x onerror=alert(1)>',...extra});
const click=id=>node(id).listeners.click();
async function flush(){for(let i=0;i<12;i++)await Promise.resolve();}
"""
    result = subprocess.run(['node', '-e', harness + '\n(async()=>{\n' + script +
                             '\n})().catch(error=>{console.error(error);process.exitCode=1;});'],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_startup_check_is_nonblocking_plain_text_and_never_downloads():
    run_node(r"""
let resolveCheck,count=0;
load({check_app_update(){count++;return new Promise(resolve=>resolveCheck=resolve);},
  download_app_update(){throw new Error('Startup must not download');}});
assert.strictEqual(count,1);assert(node('btn-check-update').disabled);
listeners.pywebviewready();await click('btn-check-update');assert.strictEqual(count,1);
resolveCheck(latest());await flush();
assert(!node('app-update-banner').hidden);assert(!node('btn-download-update').hidden);
assert(!node('btn-check-update').classList.contains('primary'));
assert.strictEqual(node('app-release-notes').textContent,'<img src=x onerror=alert(1)>');
assert(!node('btn-check-update').disabled);
await click('btn-view-update');assert.strictEqual(page,'settings');assert(node('app-update-heading').scrolled);
await click('btn-dismiss-update');assert(node('app-update-banner').hidden);
""")


def test_preview_and_unsupported_runtime_do_not_offer_windows_downloads():
    run_node(r"""
load();assert(node('btn-check-update').disabled);assert(node('btn-open-release').disabled);
assert(node('btn-download-update').hidden);assert(node('app-update-status').textContent.includes('不会联网'));
let opened=0;
window.pywebview={api:{check_app_update:async()=>latest({supported:false,can_download:false}),
  open_app_release_page:async()=>{opened++;return {ok:true};}}};
listeners.pywebviewready();await flush();
assert(node('btn-download-update').hidden);assert(node('app-update-status').textContent.includes('不支持'));
await click('btn-open-release');assert.strictEqual(opened,1);
""")


def test_offline_or_invalid_check_can_retry_and_only_offer_a_newer_version():
    run_node(r"""
let attempt=0;
load({ping:async()=>({ok:true,version:'0.2.3'}),check_app_update:async()=>{
  attempt++;if(attempt===1)throw new Error('网络不可用');
  if(attempt===2)return {ok:true};
  if(attempt===3)return latest({latest_version:'0.2.3',same_version:true,available:false,can_download:false,reason:'当前已是最新版本'});
  return latest();
}});
await flush();assert(node('app-update-status').textContent.includes('检查失败'));
assert.strictEqual(node('app-current-version').textContent,'当前版本：0.2.3');
assert(!node('app-update-status').textContent.includes('已是最新'));assert(node('btn-download-update').hidden);
await click('btn-check-update');assert(node('app-update-status').textContent.includes('检查失败'));
await click('btn-check-update');
assert(node('app-update-banner').hidden);
assert(node('btn-download-update').hidden);
assert(node('app-update-status').textContent.includes('已是最新'));
await click('btn-check-update');
assert(!node('app-update-banner').hidden);
assert(node('app-update-banner-text').textContent.includes('发现新版 0.2.4'));
assert(!node('btn-download-update').hidden);
assert.strictEqual(node('btn-download-update').textContent,'下载新版');
""")


def test_download_progress_double_click_completion_and_open_folder():
    run_node(r"""
let resolveDownload,downloads=0,folders=0;
load({check_app_update:async()=>latest(),download_app_update(){downloads++;return new Promise(resolve=>resolveDownload=resolve);},
  app_update_status:async()=>({ok:true,state:'downloading',downloaded:524288,total:1048576}),
  open_app_update_folder:async()=>{folders++;return {ok:true};}});
await flush();const downloading=click('btn-download-update');
await click('btn-download-update');await click('btn-check-update');assert.strictEqual(downloads,1);
assert(node('btn-download-update').disabled);assert(node('btn-check-update').disabled);
await [...timers.values()][0]();assert.strictEqual(node('app-update-progress').value,50);
assert(node('app-update-progress-text').textContent.includes('0.5 / 1.0 MB'));
resolveDownload({ok:true,path:'C:\\下载\\新版.exe',sha256:'abc'});await downloading;
assert.strictEqual(timers.size,0);assert.strictEqual(node('app-update-progress').value,100);
assert(!node('btn-open-update-folder').hidden);assert(!node('btn-check-update').disabled);
assert(node('app-update-status').textContent.includes('SHA-256'));assert(node('app-update-status').textContent.includes('先保存'));
assert(node('btn-download-update').hidden);
await click('btn-open-update-folder');assert.strictEqual(folders,1);
""")


def test_cancelled_and_failed_download_leave_retry_available():
    run_node(r"""
let attempt=0;
load({check_app_update:async()=>latest(),download_app_update:async()=>{
  attempt++;if(attempt===1)return {ok:true,cancelled:true};
  return {ok:false,error:'校验失败'};
}});
await flush();await click('btn-download-update');
assert(node('app-update-status').textContent.includes('已取消'));assert(node('app-update-progress-wrap').hidden);
await click('btn-download-update');
assert(node('app-update-status').textContent.includes('下载失败'));assert(node('btn-open-update-folder').hidden);
assert(!node('btn-download-update').disabled);assert.strictEqual(timers.size,0);
""")


def test_github_check_and_download_failures_offer_feishu_fallback():
    run_node(r"""
let opened=0,checked=0;
load({ping:async()=>({ok:true,version:'0.3.1'}),
  check_app_update:async()=>{if(++checked===1)throw new Error('网络不可用');return latest();},
  download_app_update:async()=>({ok:false,error:'下载连接中断'}),
  open_internal_release_page:async()=>{opened++;return {ok:true};}});
await flush();
const fallback=node('btn-open-internal-release');
assert.strictEqual(checked,1);
assert(!fallback.disabled && fallback.classList.contains('primary'));
assert(node('app-update-status').textContent.includes('飞书更新页'));
await click('btn-open-internal-release');assert.strictEqual(opened,1);
await click('btn-check-update');assert.strictEqual(checked,2);
assert(!fallback.disabled && !fallback.classList.contains('primary'));
assert(!node('btn-download-update').hidden);
await click('btn-download-update');
assert(fallback.classList.contains('primary'));
assert(node('app-update-status').textContent.includes('飞书更新页'));
""")


def test_installed_update_requires_confirmation_and_disables_retry_after_launch():
    run_node(r"""
let installs=0, resolveInstall;
load({check_app_update:async()=>latest({installer_update:true}),
  install_app_update(){installs++;return new Promise(resolve=>resolveInstall=resolve);},
  app_update_status:async()=>({ok:true,state:'downloading',downloaded:524288,total:1048576})});
await flush();
assert.strictEqual(installs,0);
assert.strictEqual(node('btn-download-update').textContent,'下载并安装');
approveInstall=false;
await click('btn-download-update');
assert(confirmations[0].includes('请先保存当前工作'));
assert.strictEqual(installs,0);
assert(!node('btn-download-update').disabled);
approveInstall=true;
const updating=click('btn-download-update');
await click('btn-download-update');assert.strictEqual(installs,1);
await [...timers.values()][0]();assert.strictEqual(node('app-update-progress').value,50);
resolveInstall({ok:true});await updating;
assert(node('btn-download-update').hidden);
assert(node('btn-check-update').disabled);
assert(node('btn-open-update-folder').hidden);
assert(node('app-update-status').textContent.includes('安装完成后，程序将重新打开'));
assert.strictEqual(timers.size,0);
""")


def test_installer_failure_keeps_retry_and_feishu_fallback():
    run_node(r"""
let installs=0;
load({check_app_update:async()=>latest({installer_update:true}),
  install_app_update:async()=>{
    if(++installs===1)return {ok:true,cancelled:true};
    return {ok:false,error:'安装包签名校验失败'};
  }});
await flush();await click('btn-download-update');
assert(node('app-update-status').textContent.includes('已取消安装更新'));
await click('btn-download-update');
assert(node('app-update-status').textContent.includes('安装包签名校验失败'));
assert(node('btn-open-internal-release').classList.contains('primary'));
assert(!node('btn-download-update').disabled);
assert(node('app-update-progress-wrap').hidden);
assert.strictEqual(timers.size,0);
""")


def test_cached_installer_can_retry_without_downloading_again():
    run_node(r"""
let installs=0;
load({check_app_update:async()=>latest({installer_update:true,can_download:false,downloaded_path:'C:\\更新\\carkit-setup.exe'}),
  install_app_update:async()=>++installs===1 ? {ok:false,error:'无法启动安装程序'} : {ok:true}});
await flush();
const button=node('btn-download-update');
assert(!button.hidden);
assert.strictEqual(button.textContent,'安装并重启');
assert(node('btn-open-update-folder').hidden);
await click('btn-download-update');
assert(confirmations[0].includes('验证已下载的安装包'));
assert(!button.hidden && !button.disabled);
await click('btn-download-update');
assert.strictEqual(installs,2);
assert(button.hidden);
assert(node('app-update-status').textContent.includes('安装完成后，程序将重新打开'));
""")
