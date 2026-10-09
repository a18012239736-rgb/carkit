import subprocess
from pathlib import Path

from engine.valuer import editor_schema


def test_range_editor_labels_explain_full_difference_pricing():
    fields = editor_schema()['1']
    assert fields[0]['label'] == '续航差计价阈值'
    assert fields[1]['label'] == '达阈值后全续航差单价'
    assert fields[1]['unit'] == '元/km'


def test_editor_explanations_follow_params_and_price_source():
    script = r"""
const assert=require('assert'), fs=require('fs'), vm=require('vm');
let component;
const context={window:{}, Vue:{ref:value=>({value}),computed:fn=>({get value(){return fn();}}),watch(){},
  createApp:definition=>{component=definition;return {mount(){},unmount(){}};}}};
vm.createContext(context);
vm.runInContext(fs.readFileSync('ui/valuation-editor.js','utf8'),context);
const item={no:1,rule:'dynamic',params:{threshold_km:50,per_km:60}};
context.window.ValuationEditor.mount({classList:{add(){}}},{items:[item]},{},{1:'续航'});
const rules=component.setup();
assert.match(rules.rangeExplanation(item),/续航差≥50km/);
assert.match(rules.rangeExplanation(item),/80km×60元\/km＝4800元/);
assert.match(rules.rangeExplanation(item),/不扣除阈值/);
rules.setParam(item,'threshold_km','70');
rules.setParam(item,'per_km','80');
assert.match(rules.rangeExplanation(item),/续航差≥70km/);
assert.match(rules.rangeExplanation(item),/100km×80元\/km＝8000元/);
rules.setParam(item,'per_km','');
assert.match(rules.rangeExplanation(item),/请填写/);
assert.match(component.template,/本轮对比不纳入；原始配置仍可查看/);

vm.runInContext(fs.readFileSync('ui/config-editor.js','utf8'),context);
context.window.ConfigEditor.mount({classList:{add(){},remove(){}}},{kind:'snapshot',model:{trims:[],cells:[]}});
const config=component.setup();
const guide=config.priceSource({price_source:'指导价',price_reference:10.99,price_guide:10.99});
assert.match(guide,/10.99万元/);
assert.match(guide,/已填入，请核对/);
assert.doesNotMatch(guide,/另填/);
const tp=config.priceSource({price_source:'TP价格',price_reference:8.99,price_guide:null});
assert.match(tp,/仅作参考/);
assert.match(tp,/指导价请另填/);
assert.match(config.priceSource({price_source:'未确定',price_reference:8.99}),/口径未确定；请确认/);
assert.match(config.priceSource({price_source:'指导价',price_guide:null}),/请核对后填写/);
"""
    result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
