import json
import subprocess
from pathlib import Path

from api.bridge import Bridge
from engine import differ, ladder as ladder_mod, mapper, ppt_import, rawschema, stage_one, tailgate, valuer, wireless
from engine.models import Cell, Ladder, LadderItem, RawRow, RawTable, Snapshot, Trim, ValuationItem, ValuationTable
from engine.rules import Rules
from engine.seat_functions import from_text
from engine.snapshot import resolve
from test_config_editor_mapping import run_editor
from test_frontend_comparison_state import run_node


ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden'


def test_mirror_valuation_and_golden_diff_consistency():
    assert valuer.dynamic_delta(20, '●三项全', '电调+折叠+加热') == 0
    assert valuer.dynamic_delta(20, '电动调节+电动折叠+锁车自动折叠', '电调+折叠') == 0
    assert valuer.dynamic_delta(20, '电动调节', '✕') == 100
    assert valuer.dynamic_delta(20, '●三项全', '✕') == 300

    rules = Rules()
    raw = rawschema.detect_and_load(str(GOLDEN / 'raw-Q05-汽车之家全表-2026-09-11.json'), series_id='8241')
    comp_lad = ladder_mod.build_ladder(raw, rules, model='启源Q05', series_id='8241', date='2026-09-11')
    self_lad = resolve(Snapshot.load(str(GOLDEN / 'T19NG-snapshot.json'))).to_ladder(rules.checklist['items'])
    vt = ValuationTable(items=[ValuationItem(**it) for it in valuer.default_valuation(rules)['items']])
    pairs = [
        {'self_trim': '基础型', 'comp_trim': '405Max'},
        {'self_trim': '舒适型', 'comp_trim': '506Max'},
        {'self_trim': '豪华型', 'comp_trim': '506激光极智'},
    ]
    cells = differ.diff(self_lad, comp_lad, pairs, rules, valuation=vt)
    for pi in range(3):
        c20 = next(c for c in cells if c['pair'] == pi and c['no'] == 20)
        c38 = next(c for c in cells if c['pair'] == pi and c['no'] == 38)
        assert c20['verdict'] == '同'
        assert valuer.dynamic_delta(20, c20['self_config'], c20['comp_config']) == 0
        if pi in (1, 2):
            assert c38['verdict'] == '同'
            assert valuer.dynamic_delta(38, c38['self_config'], c38['comp_config']) == 0
        else:
            assert c38['verdict'] == '少'
            assert valuer.dynamic_delta(38, c38['self_config'], c38['comp_config']) == -100.0


def test_external_speaker_presence_and_tire_rim_valuation():
    assert valuer.dynamic_delta(38, '●', '1') == 0
    assert valuer.dynamic_delta(38, '●', '2') == 0
    assert valuer.dynamic_delta(38, '●', '✕') == 100
    assert valuer.dynamic_delta(38, '2', '1') == 100
    assert valuer._default_rule_amount(38, '车外扬声器', 'less') == 100
    assert valuer.dynamic_delta(4, '215/55 R17铝轮毂', 'R18铝轮毂') == -700


def test_optional_subitems_never_become_standard_across_parsers():
    # n_mirror: optional sub-items dropped, standard sub-items after optional head kept
    raw = RawTable(trims=[Trim(0, 'A'), Trim(1, 'B')], rows=[
        RawRow(name='外后视镜功能', cells=[
            Cell(dot='●', text='电动调节', subs=[Cell(dot='○', text='电动折叠'), Cell(dot='○', text='后视镜加热')]),
            Cell(dot='○', text='电动折叠', subs=[Cell(dot='●', text='电动调节')]),
        ])
    ])
    assert mapper.n_mirror(raw, 0, {}) == '电调'
    assert mapper.n_mirror(raw, 1, {}) == '电调'

    # tailgate
    for absent_or_opt in ('电动后备箱(选装)', '感应电动后备箱(选装)', '无配置', '不支持', 'X', '不适用', '选装', '选配'):
        assert tailgate.components(absent_or_opt) == (False, False)
    assert tailgate.components('电动后备箱(○感应选装)') == (True, False)
    assert tailgate.components('感应电动后备箱(带位置记忆)') == (True, True)

    # wireless
    assert wireless.units('前排50W+○后排50W') == [('前排', 1, 'fast')]
    assert wireless.units('前排50W/○后排15W') == [('前排', 1, 'fast')]
    assert wireless.units('前排50W(选装)') == []
    assert wireless.units('○前排50W') == []

    # seat_functions
    s1 = from_text(front='加热+通风+按摩(选装)')
    assert s1['主驾加热'] == s1['副驾加热'] == s1['主驾通风'] == s1['副驾通风'] == '●'
    assert s1['主驾按摩'] == s1['副驾按摩'] == '✕'

    s2 = from_text(front='加热+○通风')
    assert s2['主驾加热'] == s2['副驾加热'] == '●'
    assert s2['主驾通风'] == s2['副驾通风'] == '✕'

    s3 = from_text(front='主驾加热/副驾通风')
    assert s3['主驾加热'] == '●' and s3['副驾加热'] == '✕'
    assert s3['副驾通风'] == '●' and s3['主驾通风'] == '✕'

    s4 = from_text(front='主驾加热，副驾通风')
    assert s4['主驾加热'] == '●' and s4['副驾加热'] == '✕'
    assert s4['副驾通风'] == '●' and s4['主驾通风'] == '✕'

    s5 = from_text(front='加热(仅主驾) 通风')
    assert s5['主驾加热'] == '●' and s5['副驾加热'] == '✕'
    assert s5['主驾通风'] == s5['副驾通风'] == '●'

    s6 = from_text(headrest='前排+后排')
    assert s6['主驾头枕音响'] == s6['副驾头枕音响'] == s6['二排头枕音响'] == '●'

    s7 = from_text(front='加热/通风/按摩(仅主驾)')
    assert s7['主驾加热'] == s7['主驾通风'] == s7['主驾按摩'] == '●'
    assert s7['副驾加热'] == s7['副驾通风'] == s7['副驾按摩'] == '✕'


def test_stage_one_front_seat_scope_splitting():
    def run_front(text):
        raw = RawTable(trims=[Trim(0, 'A')], rows=[RawRow(name='前排座椅功能', cells=[Cell(dot='●', text=text)])])
        feats = {f['key']: f['values'][0] for f in stage_one.features(raw, [])}
        return feats.get('前排座椅功能', [])

    assert run_front('加热(副驾)') == ['副驾座椅加热']
    assert run_front('加热(仅主驾)+通风') == ['主驾座椅加热', '主驾座椅通风', '副驾座椅通风']
    assert run_front('加热(主驾驶)/按摩(副驾驶)') == ['主驾座椅加热', '副驾座椅按摩']
    assert run_front('加热(主驾驶/副驾驶)') == ['主驾座椅加热', '副驾座椅加热']


def test_autohome_dom_js_filters_nested_style_col_sub():
    dom_js = (ROOT / 'engine' / 'autohome_dom.js').read_text(encoding='utf-8')
    script = f"""
const assert = require('assert');
const extract = {dom_js};
function makeEl(className, {{text='', iClass='', subs=[]}} = {{}}) {{
  const el = {{
    className,
    textContent: text,
    children: [],
    querySelector(sel) {{
      if (sel.includes('style_col_sub')) return subs.length ? subs[0] : null;
      return null;
    }},
    querySelectorAll(sel) {{
      if (sel.includes('style_col_sub')) {{
        const out = [];
        for (const s of subs) {{
          out.push(s);
          out.push(...s.querySelectorAll(sel));
        }}
        return out;
      }}
      if (sel === 'i') return iClass ? [{{className: iClass, replaceWith(tok){{ el.textContent = tok + el.textContent; }}}}] : [];
      return [];
    }},
    cloneNode() {{ return makeEl(className, {{text, iClass, subs}}); }},
  }};
  return el;
}}
const leaf1 = makeEl('style_col_sub__std', {{text: '14.6英寸', iClass: 'solid'}});
const leaf2 = makeEl('style_col_sub__opt', {{text: '15.6英寸', iClass: 'outline'}});
const wrapper = makeEl('style_col_sub__wrap', {{subs: [leaf1, leaf2]}});
const colVal = makeEl('style_col__v', {{subs: [wrapper]}});
const colName = makeEl('style_col__n', {{text: '中控屏幕尺寸'}});
const rowEl = makeEl('style_row__abc');
rowEl.children = [colName, colVal];
const headEl = {{textContent: 'Test 2026款 A', href: 'https://www.autohome.com.cn/spec/123/'}};
global.location = {{href: 'https://www.autohome.com.cn/config/series/123.html'}};
global.document = {{
  body: {{innerText: '共 1 款车型'}},
  querySelectorAll(sel) {{
    if (sel.includes('style_col_spec_name')) return [headEl];
    if (sel === 'label') return [];
    if (sel === 'div') return [rowEl];
    return [];
  }},
}};
const res = extract();
assert.strictEqual(res.rows[0].v[0], '●14.6英寸 | ○15.6英寸');
"""
    proc = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_rawschema_and_cell_from_dict_consistent_for_embedded_markers():
    compact = {
        'headers': ['测试 2026款 A'],
        'rows': [
            {'n': '电动前备箱', 'v': ['主●/副○']},
            {'n': '方向盘材质', 'v': ['前○/后○']},
        ],
    }
    raw_mem = rawschema.from_compact(compact)
    raw_disk = RawTable.from_dict(raw_mem.to_dict())
    assert raw_mem.to_dict() == raw_disk.to_dict()
    assert stage_one.parts(raw_mem.rows[0].cells[0], optional=False) == ['主●/副○']
    assert stage_one.parts(raw_mem.rows[1].cells[0], optional=True) == ['前○/后○']
    assert mapper._solid(raw_mem.rows[0].cells[0]) is True


def test_ppt_import_negation_speed_and_seat_routing():
    draft = {
        'model': 'TestCar',
        'price_kind': '指导价',
        'source': '手动填写',
        'columns': [
            {
                'name': '基础版',
                'base': None,
                'price': 10.0,
                'text': '\n'.join([
                    '无线充电50W',
                    '无钥匙进入',
                    '510km纯电续航',
                    '最高车速180km/h',
                    '0-100km/h加速7.5s',
                    '主驾6向电调+方向盘加热',
                    '前排座椅通风加热+二排座椅加热',
                ]),
            },
            {
                'name': '减配版',
                'base': '基础版',
                'price': 9.5,
                'text': '取消无线充电',
            },
        ],
    }
    snap = ppt_import.make_snapshot(draft)
    by_no = {c['no']: c['values'] for c in snap.to_dict()['cells']}
    assert by_no[1]['基础版'] == '510km'
    assert by_no[27]['基础版'] == '●'
    assert by_no[33]['基础版'] == '●无线充电50W'
    assert '[待定]' in by_no[33]['减配版']
    assert by_no[36]['基础版'] == {
        '主驾通风': '●', '副驾通风': '●', '二排通风': '✕',
        '主驾加热': '●', '副驾加热': '●', '二排加热': '●',
        '主驾按摩': '✕', '副驾按摩': '✕', '二排按摩': '✕',
        '主驾头枕音响': '✕', '副驾头枕音响': '✕', '二排头枕音响': '✕',
    }
    # Steering wheel heating should not fabricate seat heating on a seat-adjustment line
    snap2 = ppt_import.make_snapshot({
        'model': 'TestCar2',
        'price_kind': '指导价',
        'source': '手动填写',
        'columns': [{'name': 'A', 'base': None, 'price': 10.0, 'text': '主驾6向电调+方向盘加热'}],
    })
    by_no2 = {c['no']: c['values'] for c in snap2.to_dict()['cells']}
    assert by_no2[27]['A'] == '●'
    assert by_no2[36]['A']['主驾加热'] == '✕'
    assert by_no2[36]['A']['副驾加热'] == '✕'
    # 无钥匙进入 should not be flagged as negation leftover
    assert not any('无钥匙进入' in line for line in snap.to_dict()['rulings'][0]['remaining'].get('基础版', []))


def test_bridge_load_ladder_returns_path_and_frontend_saves_left_plan_edit(tmp_path):
    lad = Ladder(trims=[{'name': 'A'}], items=[LadderItem(no=3, name='高压架构', values=['400V'])])
    p = tmp_path / 'lad.json'
    lad.save(str(p))
    bridge = Bridge(str(tmp_path / 'work'))
    try:
        res = bridge.load_ladder(str(p))
        assert res['ok'] is True
        assert res['path'] == str(p)
    finally:
        bridge.shutdown()

    run_node(r"""
load("$('#diff-edit-self').onclick", "$('#back-to-diff').onclick");
context.loadChecklist=async()=>({items:[]});
context.mountConfigurationEditor=(root,model)=>{root.model=model;};
context.renderLadderTable=(selector,model)=>{node(selector).model=model || ST.ladder;};
context.collectLadderEdits=()=>{};
node('#diff-self-editor').hidden=true;
node('#diff-competitor-editor').hidden=true;
node('#diff-mode').value='competitor';
node('#diff-left-vehicle').value='Left.json';
ST.plan={session:'p1',paths:{left:'session/left.json',right:'session/right.json'}};
const saved=[];
context.api=async(method,...args)=>{
  if(method==='load_ladder')return {ok:true,ladder:{model:'L',trims:[{name:'A'}],items:[]}};
  if(method==='save_ladder_edit'){saved.push(args);return {ok:true};}
  throw new Error('Unexpected '+method);
};
await node('#diff-edit-self').onclick();
assert.strictEqual(ST.leftLadderPath,'session/left.json');
await node('#diff-save-self').onclick();
assert.strictEqual(saved.length,1);
assert.strictEqual(saved[0][0],'session/left.json');
""")


def test_ppt_expand_empty_base_does_not_self_inherit():
    run_node(r"""
const colRow={querySelector:sel=>({'.ppt-name':{value:'基础型'},'.ppt-base':{value:''},'.ppt-price':{value:'10'},'.ppt-text':{value:'510km'},'.ppt-options':{value:''}}[sel])};
context.$$=(sel)=>sel==='#ppt-columns .ppt-column'?[colRow]:[];
context.renderSnapshot=async()=>{};
node('#ppt-model').value='ModelX';
node('#ppt-price-kind').value='指导价';
node('#ppt-status').style={};
ST.pptDraft={model:'ModelX',price_kind:'指导价',columns:[{name:'',base:null,price:null,text:''}]};
load("$('#ppt-expand').onclick=", "$('#ppt-save').onclick=");
let sentDraft=null;
context.api=async(method,draft)=>{
  if(method==='ppt_preview'){sentDraft=draft;return {snapshot:{rulings:[{remaining:{}}]}};}
  throw new Error('Unexpected '+method);
};
await node('#ppt-expand').onclick();
assert.strictEqual(sentDraft.columns[0].name,'基础型');
assert.strictEqual(sentDraft.columns[0].base,null);
""")


def test_config_editor_simple_count_backspace_and_seat_count_validation():
    run_editor(r"""
const rng=makeCell('620km',1);
assert.strictEqual(rng.cell.simpleCount.value,true);
assert.strictEqual(rng.cell.count.value,'620');
rng.cell.countInput('');
assert.strictEqual(rng.cell.simpleCount.value,true);
assert.strictEqual(rng.cell.count.value,'');
assert.deepStrictEqual(rng.emitted,[]);
rng.cell.countInput('510');
assert.deepStrictEqual(rng.emitted,['510km']);
rng.cell.countInput('');
rng.cell.countCommit('');
assert.deepStrictEqual(rng.emitted,['510km','[待定]']);

const seat=makeCell('主驾6向电调+副驾4向手调',35);
await seat.settle();
assert.strictEqual(seat.cell.seatDetail.value.editable,true);
for(const bad of ['0','-2','6.5','31']) {
  let msg='', reported=false;
  seat.cell.seatChange(0,'count',bad,{target:{setCustomValidity(m){msg=m;},reportValidity(){reported=true;}}});
  assert(msg && reported, 'should reject '+bad);
  assert.deepStrictEqual(seat.emitted,[]);
}
seat.cell.seatChange(0,'count','8',{target:{setCustomValidity(){},reportValidity(){}}});
assert.strictEqual(seat.emitted.length,1);
assert(seat.emitted[0].includes('主驾8向电调'));
""", ['主驾6向电调+副驾4向手调'])


def test_bridge_export_5c(tmp_path):
    raw = RawTable(
        series_id='8241',
        model='测试车型',
        scraped_at='2026-11-25',
        trims=[Trim(0, '基础版', price_guide=9.98), Trim(1, '高配版', price_guide=10.98)],
        rows=[
            RawRow('级别', [Cell(text='紧凑型SUV'), Cell(text='紧凑型SUV')]),
            RawRow('纯电续航里程(km)', [Cell(text='405'), Cell(text='505')]),
            RawRow('全景天窗', [Cell(dot='○', text='选装'), Cell(dot='●', text='')]),
        ],
    )
    rules = Rules()
    lad = ladder_mod.build_ladder(raw, rules, model='测试车型', series_id='8241')
    lad_path = tmp_path / 'ladder.json'
    lad.save(str(lad_path))

    lad_no_raw = Ladder(model='无原文', trims=[{'name': 'A', 'price_guide': 10}], items=[])
    no_raw_path = tmp_path / 'no_raw.json'
    lad_no_raw.save(str(no_raw_path))

    bridge = Bridge(str(tmp_path / 'work'))
    try:
        res = bridge.export_5c(str(lad_path))
        assert res['ok'] is True
        md = Path(res['path']).read_text(encoding='utf-8')
        assert '# 5C-看竞争-测试车型' in md
        assert '**基本配置（基础版）：**' in md
        assert '全景天窗' in md

        err = bridge.export_5c(str(no_raw_path))
        assert err['ok'] is False
        assert '原始' in err['error']
    finally:
        bridge.shutdown()
