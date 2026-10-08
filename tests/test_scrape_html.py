import json
import subprocess

import pytest
from lxml import html as LH

from engine import scrape


def saved_table(missing_column=False):
    headers = ''.join(
        f'<div class="style_col__header"><a class="style_col_spec_name__hash">测试车型 2026款 第{i + 1}版型完整名称超过旧表头截断长度的版本</a><span>对比</span></div>'
        for i in range(9)
    )

    def row(name, values):
        return '<div class="style_row__hash"><div class="style_col__name">' + name + '</div>' + ''.join(
            '<div class="style_col__value">' + value + '</div>' for value in values
        ) + '</div>'

    screens = [
        f'<div class="style_col_sub__wrapper"><div class="style_col_sub__standard"><i class="style_col_dot_solid__hash"></i>14.{i}英寸</div>'
        f'<div class="style_col_sub__option"><i class="style_col_dot_outline__hash"></i>15.{i}英寸</div></div>'
        for i in range(9)
    ]
    if missing_column:
        screens.pop()
    return '<html><body><div class="style_col__noise">侧栏内容</div><header>' + headers + '</header>' + (
        row('厂商指导价(元)', [f'{10 + i}.88万' for i in range(9)])
        + row('中控屏幕尺寸', screens)
        + row('座椅加热', ['主<i class="style_col_dot_solid__hash">●</i>/副<i class="style_col_dot_outline__hash">○</i>'] * 8 + [''])
    ) + '</body></html>'


def assert_complete(raw):
    assert len(raw.trims) == 9
    assert raw.trims[-1].full == '测试车型 2026款 第9版型完整名称超过旧表头截断长度的版本'
    assert raw.trims[-1].price_guide == 18.88
    assert all(len(row.cells) == 9 for row in raw.rows)
    screen = raw.row('中控屏幕尺寸').cells[-1]
    assert (screen.dot, screen.text) == ('●', '14.8英寸')
    assert [(cell.dot, cell.text) for cell in screen.subs] == [('○', '15.8英寸')]
    assert raw.row('座椅加热').cells[0].text == '主●/副○'
    assert raw.row('座椅加热').cells[-1].absent


def test_saved_html_keeps_all_headers_columns_and_nested_options(tmp_path):
    path = tmp_path / '配置.html'
    path.write_text(saved_table(), encoding='utf-8')
    raw = scrape.parse_saved_html(str(path), series_id='1234')
    assert_complete(raw)
    assert raw.series_id == '1234'
    assert raw.source == 'html'


@pytest.mark.parametrize('change,message', [
    ('missing_column', '配置列数与版型不一致：中控屏幕尺寸'),
    ('missing_header', '完整版型表头'),
    ('duplicate_header', '版型列头重复'),
])
def test_saved_html_rejects_unreliable_column_binding(tmp_path, change, message):
    text = saved_table(missing_column=change == 'missing_column')
    if change == 'missing_header':
        text = text.replace('style_col_spec_name__hash', 'unrelated_link')
    elif change == 'duplicate_header':
        text = text.replace('第9版型', '第8版型')
    path = tmp_path / '配置.html'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ValueError, match=message):
        scrape.parse_saved_html(str(path))


def evaluate_dom(text):
    # Run the actual browser extractor with only the DOM operations it uses.
    def node(el):
        return {'tag': el.tag, 'className': el.get('class', ''), 'text': el.text or '',
                'tail': el.tail or '', 'children': [node(child) for child in el]}

    script = r'''
const fs = require('fs');
const {tree, source} = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(data, parent=null) {
    Object.assign(this, data); this.parent = parent;
    this.children = data.children.map(child => new Element(child, this));
  }
  get textContent() { return this.text + this.children.map(c => c.textContent + c.tail).join(''); }
  querySelectorAll(selector) {
    const match = selector.match(/^(\w+)(?:\[class\*="([^"]+)"\])?$/);
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
      tail:node.tail, children:node.children.map(data)});
    return new Element(data(this));
  }
  replaceWith(text) { this.text=text; this.children=[]; }
}
global.document = new Element(tree);
console.log(eval('(' + source + ')')());
'''
    result = subprocess.run(['node', '-e', script], input=json.dumps({'tree': node(LH.fromstring(text)), 'source': scrape.EVALUATE_JS}),
                            text=True, encoding='utf-8', capture_output=True, check=True)
    return json.loads(result.stdout)


def test_legacy_browser_capture_keeps_all_nine_columns(monkeypatch):
    class Page:
        def wait_for_selector(self, *args, **kwargs):
            pass

        def evaluate(self, source):
            assert source == scrape.EVALUATE_JS
            return evaluate_dom(saved_table())

    monkeypatch.setitem(scrape._SESSION, 'page', Page())
    monkeypatch.setitem(scrape._SESSION, 'series_id', '1234')
    assert_complete(scrape.scrape_capture())


def test_legacy_browser_capture_rejects_missing_column(monkeypatch):
    class Page:
        def wait_for_selector(self, *args, **kwargs):
            pass

        def evaluate(self, source):
            return evaluate_dom(saved_table(missing_column=True))

    monkeypatch.setitem(scrape._SESSION, 'page', Page())
    with pytest.raises(ValueError, match='配置列数与版型不一致：中控屏幕尺寸'):
        scrape.scrape_capture()
