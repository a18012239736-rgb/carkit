from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from api.bridge import Bridge
from engine.ppt_import import NS, _base_from_marker, _price_value


def test_relative_ladder_import_keeps_all_columns_and_uses_guide_prices(tmp_path):
    names = ['1.4T-标准型', '1.4T-舒适型', '1.4T-豪华型', '1.4T豪华型+选装',
             '1.8T-豪华型', '1.8T-豪华型+选装', '1.3L-标准型', '1.3L-舒适型', '1.3L-舒适型+选装']
    markers = ['核心配置：', '较标准型+：', '较舒适型+：', '较豪华型+：',
               '较1.4T豪华型+：', '较1.8T豪华型+：', '较1.4T标准型+：', '较1.4T舒适型+：', '较1.3L舒适型+：']
    guides = [82300, 88700, 95400, 102600, 101800, 114500, 91700, 98300, 110900]
    tag = lambda prefix, name: '{' + NS[prefix] + '}' + name
    slide = ET.Element(tag('p', 'sld'))
    tree = ET.SubElement(ET.SubElement(slide, tag('p', 'cSld')), tag('p', 'spTree'))

    def shape(x, y, lines, width=1_000_000):
        node = ET.SubElement(tree, tag('p', 'sp'))
        transform = ET.SubElement(ET.SubElement(node, tag('p', 'spPr')), tag('a', 'xfrm'))
        ET.SubElement(transform, tag('a', 'off'), x=str(x), y=str(y))
        ET.SubElement(transform, tag('a', 'ext'), cx=str(width), cy='200000')
        body = ET.SubElement(node, tag('p', 'txBody'))
        for line in lines:
            ET.SubElement(ET.SubElement(body, tag('a', 'p')), tag('a', 't')).text = line

    shape(0, 0, ['DemoM1'])
    shape(0, 500_000, ['指导价'], 600_000)
    shape(0, 800_000, ['结算价'], 600_000)
    for i, (name, marker, guide) in enumerate(zip(names, markers, guides)):
        x = 1_000_000 + i * 1_500_000
        shape(x, 200_000, [name])
        shape(x, 500_000, [str(guide)])
        shape(x, 800_000, [str(guide - 10000)])
        shape(x, 1_200_000, [marker, '6气囊' if i == 0 else '540影像'])
    path = tmp_path / 'relative-ladder.pptx'
    with ZipFile(path, 'w') as archive:
        archive.writestr('ppt/presentation.xml', f'<p:presentation xmlns:p="{NS["p"]}" xmlns:r="{NS["r"]}"><p:sldIdLst><p:sldId id="256" r:id="r1"/></p:sldIdLst></p:presentation>')
        archive.writestr('ppt/_rels/presentation.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="slides/slide1.xml"/></Relationships>')
        archive.writestr('ppt/slides/slide1.xml', ET.tostring(slide))

    bridge = Bridge(str(tmp_path / 'work'))
    try:
        assert bridge.ppt_pages(path)['ok']
        parsed = bridge.ppt_parse(path, 1)
        assert parsed['ok'], parsed
        draft = parsed['draft']
        assert [column['name'] for column in draft['columns']] == names
        assert [column['base'] for column in draft['columns']] == [None, names[0], names[1], names[2], names[2], names[4], names[0], names[1], names[7]]
        assert draft['price_kind'] == '指导价'
        assert [column['price'] for column in draft['columns']] == [price / 10000 for price in guides]
        assert draft['columns'][0]['text'] == '6气囊'
        preview = bridge.ppt_preview(draft)
        assert preview['ok'], preview
        assert [trim['price_guide'] for trim in preview['snapshot']['trims']] == [price / 10000 for price in guides]
    finally:
        bridge.shutdown()


def test_short_relative_base_requires_unambiguous_column_context():
    names = ['1.4T-标准型', '1.4T-舒适型', '1.3L-标准型', '1.3L-舒适型']
    assert _base_from_marker('核心配置：', names) is None
    assert _base_from_marker('较标准型+：', names, names[1]) == names[0]
    assert _base_from_marker('相对标准型＋：', names, names[3]) == names[2]
    assert _base_from_marker('较1.4T标准型+：', names, names[3]) == names[0]
    with pytest.raises(ValueError, match='无法唯一匹配'):
        _base_from_marker('较标准型+：', names)


@pytest.mark.parametrize(('value', 'label', 'expected'), [
    ('82300', '指导价', 8.23), ('82,300元', '指导价', 8.23),
    ('82300', '指导价（元）', 8.23), ('8.23', '指导价（万元）', 8.23),
    ('8.23万元', '指导价', 8.23), ('82300万', '指导价', 82300),
])
def test_ppt_prices_respect_explicit_units_and_normalize_bare_yuan(value, label, expected):
    assert _price_value(value, label) == expected
