import json
import subprocess

from lxml import html as LH

from api.bridge import Bridge
from engine import acquire, rawschema, scrape
from engine.models import Cell, RawRow, RawTable, Trim


def grouped_html():
    def row(name, value):
        return ('<div class="style_row__hash"><div class="style_col__name">' + name
                + '</div><div class="style_col__value">' + value + '</div></div>')

    def title(name, number):
        return (f'<div id="nav{number}" class="style_table_title__hash">'
                '<div class="style_table_title_col__hash">' + name
                + '<div class="style_table_title_prompt__hash"><i class="solid">●</i>标配'
                '<i class="outline">○</i>选配<i>-</i>无</div></div></div>')

    # The real page puts both price rows before nav0 and adds a legend inside some headings.
    return ('<html><body><a class="style_col_spec_name__hash" href="/spec/123/">'
            '测试车 2027款 基础版</a><span>共1款车型</span><div class="tw-relative">'
            + row('厂商指导价(元)', '10.99万') + row('经销商报价', '10.59万起')
            + title('基本参数', 0) + row('厂商', '测试品牌')
            + title('天窗/玻璃', 1) + row('遮阳帘', '电动')
            + title('座椅配置', 2) + row('遮阳帘', '手动')
            + row('前排座椅功能', '<i class="style_col_dot_solid__hash"></i>通风')
            + '</div></body></html>')


def evaluate_browser_html(text, source):
    def node(el):
        return {'tag': el.tag, 'className': el.get('class', ''), 'text': el.text or '',
                'tail': el.tail or '', 'href': el.get('href', ''),
                'children': [node(child) for child in el]}

    script = r'''
const fs = require('fs');
const {tree, source} = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(data) {
    Object.assign(this, data);
    this.children = data.children.map(child => new Element(child));
  }
  get textContent() { return this.text + this.children.map(c => c.textContent + c.tail).join(''); }
  get innerText() { return this.textContent; }
  querySelectorAll(selector) {
    const match = selector.match(/^(\w+)(?:\[class\*="([^"]+)"\])?$/);
    if (!match) return [];
    const found=[];
    for (const child of this.children) {
      if (child.tag === match[1] && (!match[2] || child.className.includes(match[2]))) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  cloneNode() {
    const data = node => ({tag:node.tag, className:node.className, text:node.text,
      tail:node.tail, href:node.href, children:node.children.map(data)});
    return new Element(data(this));
  }
  replaceWith(text) { this.text=text; this.children=[]; }
}
global.document = new Element(tree);
document.body = document.querySelector('body');
global.location = {href:'https://www.autohome.com.cn/config/series/123.html'};
const result = eval('(' + source + ')')();
console.log(typeof result === 'string' ? result : JSON.stringify(result));
'''
    result = subprocess.run(['node', '-e', script],
                            input=json.dumps({'tree': node(LH.fromstring(text)), 'source': source}),
                            text=True, encoding='utf-8', capture_output=True, check=True)
    return json.loads(result.stdout)


def test_live_legacy_html_and_compact_keep_real_categories_and_clean_legends(tmp_path):
    text = grouped_html()
    live = evaluate_browser_html(text, acquire.DOM_JS)
    legacy = evaluate_browser_html(text, scrape.EVALUATE_JS)
    assert [(row['n'], row['group']) for row in live['rows']] == [
        ('厂商指导价(元)', ''), ('经销商报价', ''), ('厂商', '基本参数'),
        ('遮阳帘', '天窗/玻璃'), ('遮阳帘', '座椅配置'), ('前排座椅功能', '座椅配置')]
    assert live['rows'] == legacy['rows']
    path = tmp_path / '配置.html'
    path.write_text(text, encoding='utf-8')
    imported = scrape.parse_saved_html(str(path))
    captured = rawschema.from_compact(live)
    assert [(row.name, row.group, [cell.to_dict() for cell in row.cells]) for row in imported.rows] == [
        (row.name, row.group, [cell.to_dict() for cell in row.cells]) for row in captured.rows]
    assert RawTable.from_dict(captured.to_dict()).to_dict() == captured.to_dict()


def test_stage_categories_keep_source_order_dedupe_only_within_each_group_and_do_not_write(tmp_path):
    bridge = Bridge(str(tmp_path))
    bridge.stage_raw = RawTable(trims=[Trim(0, '基础')], rows=[
        RawRow('厂商指导价(元)', [Cell(text='10.99万')]),
        RawRow('经销商报价', [Cell(text='10.59万起')]),
        RawRow('厂商', [Cell(text='测试品牌')], group='基本参数'),
        RawRow('遮阳帘', [Cell(text='电动')], group='天窗/玻璃'),
        RawRow('遮阳帘', [Cell(text='电动')], group='天窗/玻璃'),
        RawRow('遮阳帘', [Cell(text='手动')], group='座椅配置'),
        RawRow('前排座椅功能', [Cell(dot='●', text='通风')], group='座椅配置'),
        RawRow('未知原始配置', [Cell(dot='●')]),
    ])
    source = bridge.stage_raw.to_dict()
    path = tmp_path / 'raw' / 'capture.json'
    bridge.stage_raw.save(path)
    original = path.read_bytes()
    try:
        result = bridge.stage_display_rules()
        assert result['ok']
        assert result['rows'] == ['厂商指导价(元)', '经销商报价', '厂商', '遮阳帘', '前排座椅功能', '未知原始配置']
        assert result['groups'] == [
            {'name': '价格信息', 'rows': ['厂商指导价(元)', '经销商报价']},
            {'name': '基本参数', 'rows': ['厂商']},
            {'name': '天窗/玻璃', 'rows': ['遮阳帘']},
            {'name': '座椅配置', 'rows': ['遮阳帘', '前排座椅功能']},
            {'name': '未分类（旧数据）', 'rows': ['未知原始配置']},
        ]
        assert bridge.stage_raw.to_dict() == source and path.read_bytes() == original
        assert not (tmp_path / '阶梯展示排除清单.json').exists()
    finally:
        bridge.shutdown()


def test_legacy_compact_without_categories_stays_compatible(tmp_path):
    raw = rawschema.from_compact({'headers': ['测试车 2027款 基础版'], 'rows': [
        {'n': '厂商指导价(元)', 'v': ['10.99万']}, {'n': '厂商', 'v': ['测试品牌']}]})
    assert all(row.group == '' for row in raw.rows)
    bridge = Bridge(str(tmp_path))
    try:
        bridge.stage_raw = raw
        assert bridge.stage_display_rules()['groups'] == [
            {'name': '价格信息', 'rows': ['厂商指导价(元)']},
            {'name': '未分类（旧数据）', 'rows': ['厂商']},
        ]
        bridge.stage_raw = None
        assert bridge.stage_display_rules()['groups'] == []
    finally:
        bridge.shutdown()


def test_old_grouped_import_removes_heading_legend_only_for_display(tmp_path):
    bridge = Bridge(str(tmp_path))
    bridge.stage_raw = RawTable(trims=[Trim(0, '基础')], rows=[
        RawRow('天窗类型', [Cell(text='不可开启全景天窗')], group='天窗/玻璃标配选配-无'),
        RawRow('前排座椅功能', [Cell(dot='●', text='通风')], group='座椅配置 ● 标配 ○ 选配 − 无'),
    ])
    original = bridge.stage_raw.to_dict()
    try:
        assert bridge.stage_display_rules()['groups'] == [
            {'name': '天窗/玻璃', 'rows': ['天窗类型']},
            {'name': '座椅配置', 'rows': ['前排座椅功能']},
        ]
        assert bridge.stage_raw.to_dict() == original
    finally:
        bridge.shutdown()


def test_selection_optional_labels_follow_capture_markers_without_changing_names_or_raw(tmp_path):
    bridge = Bridge(str(tmp_path))
    bridge.stage_raw = RawTable(trims=[Trim(0, '基础'), Trim(1, '升级')], rows=[
        RawRow('纯选配', [Cell(dot='○'), Cell(text='-')]),
        RawRow('部分选配', [Cell(dot='○'), Cell(dot='●')]),
        RawRow('同格混合', [Cell(subs=[Cell(dot='●', text='加热'), Cell(dot='○', text='通风')]), Cell()]),
        RawRow('重复名称', [Cell(dot='○'), Cell()], group='天窗/玻璃'),
        RawRow('重复名称', [Cell(dot='●'), Cell()], group='座椅配置'),
        RawRow('标准功能', [Cell(dot='●'), Cell()]),
        RawRow('选配名称不是标记', [Cell(), Cell()]),
    ])
    original = bridge.stage_raw.to_dict()
    try:
        result = bridge.stage_display_rules()
        assert result['ok']
        assert result['option_status'] == {
            '纯选配': 'optional', '部分选配': 'mixed', '同格混合': 'mixed', '重复名称': 'mixed',
        }
        assert result['rows'] == list(dict.fromkeys(row.name for row in bridge.stage_raw.rows))
        assert bridge.stage_raw.to_dict() == original
        assert not (tmp_path / '阶梯展示排除清单.json').exists()
        bridge.stage_raw = None
        assert bridge.stage_display_rules()['option_status'] == {}
    finally:
        bridge.shutdown()
