import json
import subprocess

from lxml import html as LH

from api.bridge import Bridge
from engine import acquire, rawschema, scrape, stage_one
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


def test_stage_categories_keep_source_order_dedupe_only_within_each_group_and_do_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_one, 'DEFAULT_EXCLUDED_ROWS', ())
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
        result = bridge.stage_display_rules()
        assert result['rows'] == ['厂商指导价(元)', '厂商']
        assert category_names(result, '厂商') == ['基本参数']
        assert category_names(result, '厂商指导价(元)') == ['价格信息']
        bridge.stage_raw = None
        result = bridge.stage_display_rules()
        assert result['rows'] == []
        assert {name for group in result['groups'] for name in group['rows']} == set(stage_one.DEFAULT_EXCLUDED_ROWS)
    finally:
        bridge.shutdown()


def test_old_grouped_import_removes_heading_legend_only_for_display(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_one, 'DEFAULT_EXCLUDED_ROWS', ())
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


def category_names(result, name):
    return [group['name'] for group in result['groups'] if name in group['rows']]


def test_all_current_defaults_have_catalogue_categories_without_a_vehicle(tmp_path):
    bridge = Bridge(str(tmp_path))
    try:
        result = bridge.stage_display_rules()
        assert result['ok'] and result['rows'] == []
        assert all(category_names(result, name) for name in stage_one.DEFAULT_EXCLUDED_ROWS)
        assert not {'未分类（旧数据）', '其他车型/已保存'}.intersection(group['name'] for group in result['groups'])
        assert category_names(result, '电池容量(kWh)') == ['电池/充电']
        assert category_names(result, '电动机(kW)') == ['电动机']
        assert category_names(result, '电池快充时间(小时)') == ['基本参数', '电池/充电']
        assert not (tmp_path / '阶梯展示排除清单.json').exists()
    finally:
        bridge.shutdown()


def test_default_and_saved_items_keep_categories_after_restoring_defaults(tmp_path, monkeypatch):
    defaults = ('电池容量(kWh)', '电动机(kW)', '后电动机最大功率(kW)')
    monkeypatch.setattr(stage_one, 'DEFAULT_EXCLUDED_ROWS', defaults)
    bridge = Bridge(str(tmp_path))
    bridge.stage_raw = RawTable(trims=[Trim(0, '基础')], rows=[
        RawRow('当前车型独有项', [Cell(dot='●')], group='原始分类'),
    ])
    original = bridge.stage_raw.to_dict()
    try:
        assert bridge.save_stage_display_rules([*defaults, '座椅材质', '未知外来项'])['ok']
        path = tmp_path / '阶梯展示排除清单.json'
        saved = path.read_bytes()
        result = bridge.stage_display_rules()
        assert result['rows'] == ['当前车型独有项']
        assert result['groups'] == [
            {'name': '原始分类', 'rows': ['当前车型独有项']},
            {'name': '电动机', 'rows': ['电动机(kW)', '后电动机最大功率(kW)']},
            {'name': '电池/充电', 'rows': ['电池容量(kWh)']},
            {'name': '座椅配置', 'rows': ['座椅材质']},
            {'name': '其他车型/已保存', 'rows': ['未知外来项']},
        ]
        assert path.read_bytes() == saved and bridge.stage_raw.to_dict() == original
        assert bridge.save_stage_display_rules(['座椅材质', '未知外来项'])['excluded_rows'] == ['座椅材质', '未知外来项']
        assert bridge.stage_display_rules()['groups'] == result['groups']
    finally:
        bridge.shutdown()


def test_original_groups_override_catalogue_and_keep_shared_names_and_source_order(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_one, 'DEFAULT_EXCLUDED_ROWS', ('后电动机最大功率(kW)', '电池快充时间(小时)'))
    bridge = Bridge(str(tmp_path))
    bridge.stage_raw = RawTable(trims=[Trim(0, '基础')], rows=[
        RawRow('厂商', [Cell(text='测试品牌')]),
        RawRow('后电动机最大功率(kW)', [Cell(text='100')], group='座椅配置'),
        RawRow('厂商', [Cell(text='测试品牌')], group='基本参数'),
        RawRow('后电动机最大功率(kW)', [Cell(text='100')], group='原表第二分类'),
        RawRow('后电动机最大功率(kW)', [Cell(text='100')], group='原表第二分类'),
    ])
    try:
        result = bridge.stage_display_rules()
        assert [group['name'] for group in result['groups']] == [
            '座椅配置', '基本参数', '原表第二分类', '电池/充电',
        ]
        assert category_names(result, '后电动机最大功率(kW)') == ['座椅配置', '原表第二分类']
        assert category_names(result, '电池快充时间(小时)') == ['基本参数', '电池/充电']
        assert all(len(group['rows']) == len(set(group['rows'])) for group in result['groups'])
        assert result['groups'][1]['rows'] == ['厂商', '电池快充时间(小时)']
    finally:
        bridge.shutdown()


def test_history_exact_names_restore_missing_categories_skip_bad_files_and_do_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(stage_one, 'DEFAULT_EXCLUDED_ROWS', ('历史默认项', '电池容量(kWh)'))
    bridge = Bridge(str(tmp_path))
    raw_dir = tmp_path / 'raw'
    (raw_dir / '00-broken.json').write_text('{broken', encoding='utf-8')
    old = RawTable(trims=[Trim(0, '历史车型')], rows=[
        RawRow('历史默认项', [Cell(dot='●')], group='座椅配置'),
        RawRow('历史外来项', [Cell(dot='●')], group='外观/防盗'),
        RawRow('历史当前项', [Cell(dot='●')], group='驾驶功能 ● 标配 ○ 选配 − 无'),
        RawRow('电池容量(kWh)', [Cell(text='50')], group='历史真实电池分类'),
    ])
    old.save(raw_dir / '01-history.json')
    bridge.stage_raw = RawTable(trims=[Trim(0, '当前车型')], rows=[
        RawRow('历史当前项', [Cell(dot='●')]),
        RawRow('未知原始配置', [Cell(dot='●')]),
        RawRow('厂商', [Cell(text='测试品牌')]),
    ])
    original = bridge.stage_raw.to_dict()
    try:
        assert bridge.save_stage_display_rules([*stage_one.DEFAULT_EXCLUDED_ROWS, '历史外来项', '未知外来项'])['ok']
        before = {path: path.read_bytes() for path in [*raw_dir.glob('*.json'), tmp_path / '阶梯展示排除清单.json']}
        result = bridge.stage_display_rules()
        assert result['ok']
        assert category_names(result, '历史默认项') == ['座椅配置']
        assert category_names(result, '历史外来项') == ['外观/防盗']
        assert category_names(result, '历史当前项') == ['驾驶功能']
        assert category_names(result, '电池容量(kWh)') == ['历史真实电池分类']
        assert category_names(result, '厂商') == ['基本参数']
        assert category_names(result, '未知原始配置') == ['未分类（旧数据）']
        assert category_names(result, '未知外来项') == ['其他车型/已保存']
        assert bridge.stage_raw.to_dict() == original
        assert all(path.read_bytes() == content for path, content in before.items())
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
