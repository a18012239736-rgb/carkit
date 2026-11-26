import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import cli
from api.bridge import Bridge
from engine import (
    airbags,
    comparison_plan,
    differ,
    mapper,
    ppt_import,
    screen_config,
    storage,
    suspension,
    valuer,
)
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Snapshot, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from test_app_updates_frontend import run_node as run_updates_node
from test_frontend_comparison_state import run_node as run_app_node


ROOT = Path(__file__).resolve().parents[1]


def test_steer_adjust_nappa_case_and_long_chinese_plan_filename(tmp_path):
    rules = Rules()
    # #45: #26 电动调节 vs 电调 -> 同 (0 元)
    l1 = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=26, name='方向盘调节', values=['电动调节'])])
    l2 = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=26, name='方向盘调节', values=['电调'])])
    vt = ValuationTable(items=[ValuationItem(**it) for it in valuer.default_valuation(rules)['items']])
    cell26 = next(c for c in differ.diff(l1, l2, [{'self_trim': 'A', 'comp_trim': 'A'}], rules, vt) if c['no'] == 26)
    assert cell26['verdict'] == '同'

    # #46: #25 and #34 NAPPA case-insensitive valuation
    assert valuer.dynamic_delta(25, 'Nappa真皮', '真皮') > 0
    assert valuer.dynamic_delta(34, 'Nappa真皮', '真皮') > 0

    # #47: 100-char Chinese plan name fits within 255-byte POSIX filename limit and saves cleanly
    long_name = '方' * 100
    fn = storage.unique_filename(long_name, '.json')
    assert len(fn.encode('utf-8')) <= 255
    bridge = Bridge(str(tmp_path / 'work_plan'))
    try:
        snap = ppt_import.make_snapshot({'model': 'S', 'price_kind': '指导价', 'columns': [{'name': 'S1', 'base': None, 'price': 10.0, 'text': 'LED大灯'}]})
        snap.status = '已确认'
        sp = tmp_path / 's.json'
        lp = tmp_path / 'l.json'
        snap.save(str(sp))
        Ladder(model='C', trims=[{'name': 'C1', 'price_guide': 10.0}],
               items=[LadderItem(no=it['no'], name=it['name'], values=['✕']) for it in rules.items]).save(str(lp))
        res = bridge.run_diff(str(sp), str(lp), [{'self_trim': 'S1', 'comp_trim': 'C1'}])
        assert res['ok'] is True
        saved = bridge.save_comparison_plan(long_name, res['comparison_id'])
        assert saved['ok'] is True
        plans = bridge.comparison_plans()['plans']
        assert len(plans) == 1 and plans[0]['name'] == long_name
    finally:
        bridge.shutdown()


def test_mapper_airbags_screen_suspension_and_checklist_edge_cases():
    rules = Rules()
    # #48a: n_high_voltage accepts dotless '800V' and rejects '0'
    raw_hv = RawTable(trims=[Trim(0, 'A'), Trim(1, 'B'), Trim(2, 'C')], rows=[
        RawRow('高压平台', [Cell(dot='', text='800V'), Cell(dot='', text='0'), Cell(dot='●', text='0V')]),
    ])
    assert mapper.n_high_voltage(raw_hv, 0, rules.items_by_no[3]) == '●800V'
    assert mapper.n_high_voltage(raw_hv, 1, rules.items_by_no[3]) == '✕'
    assert mapper.n_high_voltage(raw_hv, 2, rules.items_by_no[3]) == '✕'

    # #48b: airbags._knee_components filters 无 / ? / — / ✕ on dedicated knee rows
    raw_knee = RawTable(trims=[Trim(0, 'A'), Trim(1, 'B'), Trim(2, 'C')], rows=[
        RawRow('主驾膝部气囊', [Cell(dot='●', text='无'), Cell(dot='●', text='?'), Cell(dot='●', text='—')]),
    ])
    for i in range(3):
        assert airbags.from_raw(raw_knee, i) == (0, [])

    # #48c: screen_config preserves (○...选装) and non-leading ○
    assert screen_config.normalize_screen('2.5K 15.6寸(○17.3选装)', 21) == '15.6寸中控屏(○17.3选装)'
    assert screen_config.normalize_screen('2.5K ○15.6寸', 21) == '○15.6寸中控屏'

    # #48d: suspension rejects trailing (选装) and /-separated ○
    assert suspension.components('空气悬架(选装)') == set()
    assert suspension.components('●软硬调节/○高低调节') == {'soft_hard'}

    # #48e: 巡航系统类型 (#9) and 中控屏幕 (#21) mapped without row_absent
    raw_alias = RawTable(trims=[Trim(0, 'A')], rows=[
        RawRow('巡航系统类型', [Cell(dot='●', text='全速自适应巡航')]),
        RawRow('中控屏幕', [Cell(dot='●', text='14.6英寸')]),
    ])
    mapped = mapper.map_raw_to_ladder(raw_alias, rules)
    assert mapped[9]['row_absent'] is False and mapped[9]['values'] == ['全速自适应巡航(无L2)']
    assert mapped[21]['row_absent'] is False and mapped[21]['values'] == ['14.6寸中控']


def test_bridge_cli_scripts_and_frontend_low_severity_fixes(tmp_path, monkeypatch):
    # #49c: export_excel('diff', None) returns clean error; install_app_update keeps real error
    bridge = Bridge(str(tmp_path / 'work'))
    try:
        excel_res = bridge.export_excel('diff', None)
        assert excel_res['ok'] is False and '请先运行对比' in excel_res['error']

        import sys
        monkeypatch.setitem(sys.modules, 'webview', SimpleNamespace(windows=[object()]))
        bridge._installed = True
        bridge._updater._release = {'available': True, 'can_download': True, 'asset_name': 'setup.exe'}
        def fake_download(target):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.with_suffix('.part').write_bytes(b'locked')
            return {'ok': False, 'error': '网络中断'}
        monkeypatch.setattr(bridge._updater, 'download_to', fake_download)
        upd_res = bridge.install_app_update()
        assert upd_res == {'ok': False, 'error': '网络中断'}
    finally:
        bridge.shutdown()

    # #49d: signing scripts compatible with Python 3.10 (no hashlib.file_digest)
    for rel in ('scripts/sign_feishu_update.py', 'scripts/sign_installer_update.py'):
        assert 'file_digest' not in (ROOT / rel).read_text(encoding='utf-8')

    # #49e: cli cmd_snapshot resolves JSON snapshots; cmd_diff validates --pairs
    snap = ppt_import.make_snapshot({'model': 'M', 'price_kind': '指导价', 'columns': [
        {'name': '基础', 'base': None, 'price': 10.0, 'text': 'LED大灯'},
        {'name': '高配', 'base': '基础', 'price': 11.0, 'text': '同基础'},
    ]})
    sp = tmp_path / 'raw_snap.json'
    out_snap = tmp_path / 'resolved_snap.json'
    snap.save(str(sp))
    cli.cmd_snapshot(SimpleNamespace(json=str(sp), o=str(out_snap)))
    loaded = Snapshot.load(str(out_snap))
    assert loaded.cells[0]['values']['高配'] != '同基础'

    lp = tmp_path / 'lad.json'
    Ladder(model='C', trims=[{'name': 'B'}],
           items=[LadderItem(no=it['no'], name=it['name'], values=['✕']) for it in Rules().items]).save(str(lp))
    with pytest.raises(SystemExit):
        cli.cmd_diff(SimpleNamespace(snapshot=str(out_snap), ladder=str(lp), pairs='bad_pair', valuation=None, o=None, json=None))

    # #49a: app-updates.js sets downloaded_path after non-installer download
    run_updates_node(r"""
load({
  check_app_update: async () => latest(),
  download_app_update: async () => ({ok:true, path:'/tmp/carkit.dmg'}),
  save_update_reminder: async () => ({ok:true}),
});
await flush();
await click('btn-skip-update');
await click('btn-download-update');
await flush();
await click('btn-restore-update');
assert(node('app-update-banner').hidden,'restoring reminder after download must not show stale download banner');
assert(node('app-update-status').textContent.includes('/tmp/carkit.dmg'));
""")

    # #49b: feedback.js clears prepared when second submit fails
    fb_script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),nodes=[];
function element(tag){
  const node={tagName:tag.toUpperCase(),value:'',checked:false,disabled:false,hidden:false,children:[],dataset:{},listeners:{},files:[],textContent:'',open:false,
    addEventListener(n,h){(this.listeners[n]||=[]).push(h);},setAttribute(n,v){this[n]=v;},focus(){},select(){},
    append(...c){c.forEach(x=>{x.parent=this;this.children.push(x);});},replaceChildren(...c){this.children=[];this.append(...c);},
    showModal(){this.open=true;},close(){this.open=false;}};
  nodes.push(node);return node;
}
const body=element('body'),window={},document={body,createElement:element,getElementById:id=>nodes.find(n=>n.id===id)||null};
const entry=element('button');entry.id='btn-open-feedback';body.append(entry);
const context={window,document,navigator:{clipboard:{writeText:async()=>{}}},FileReader:class{}};
vm.createContext(context);vm.runInContext(fs.readFileSync('ui/feedback.js','utf8'),context);
const fire=(n,e)=>Promise.all((n.listeners[e]||[]).map(h=>h({target:n})));
const btn=t=>nodes.find(n=>n.tagName==='BUTTON'&&n.textContent===t);
(async()=>{
  await fire(entry,'click');
  const title=nodes.find(n=>n.tagName==='INPUT'&&n.type==='text');
  const desc=nodes.find(n=>n.tagName==='TEXTAREA');
  const consent=nodes.find(n=>n.tagName==='INPUT'&&n.type==='checkbox');
  title.value='问题';desc.value='步骤';await fire(title,'input');await fire(desc,'input');
  consent.checked=true;await fire(consent,'change');
  let fail=false;
  window.pywebview={api:{
    async prepare_feedback(){if(fail)throw new Error('网络错误');return {ok:true,has_images:false,requires_paste:false};},
    async open_feedback_issue(){return {ok:true};},
  }};
  await fire(btn('准备反馈并前往GitHub'),'click');
  assert(!btn('打开反馈文件夹').hidden);
  fail=true;
  await fire(btn('准备反馈并前往GitHub'),'click');
  assert(btn('打开反馈文件夹').hidden);
})();
"""
    proc = subprocess.run(['node', '-e', fb_script], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr

    # #49f: legacy renderLadderTable escapes HTML in trim/item names
    run_app_node(r"""
context.window.ConfigEditor=null;
context.esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
context.configurationDisplayOrder=items=>items;
context.cellCls=()=>'';
context.addConfigurationChoices=()=>{};
load('function renderLadderTable(', 'function collectLadderEdits(');
context.renderLadderTable('#ladder-table-wrap',{
  trims:[{name:'<img src=x>',price_guide:'<b>10</b>'}],
  items:[{no:3,name:'<script>bad</script>',values:['<svg>'],subs:[]}],
});
const html=node('#ladder-table-wrap').innerHTML;
assert(!html.includes('<img') && !html.includes('<script>'));
assert(html.includes('&lt;img src=x&gt;'));
assert(html.includes('&lt;script&gt;bad&lt;/script&gt;'));
""")
