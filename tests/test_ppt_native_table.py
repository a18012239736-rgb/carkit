from xml.etree import ElementTree as ET
from engine.ppt_import import NS, _parse_native_table, make_snapshot


def test_merged_headers_blank_cells_and_short_base_names():
    table = ET.Element('{'+NS['a']+'}tbl')
    def row(values):
        r = ET.SubElement(table, '{'+NS['a']+'}tr')
        for text, attrs in values:
            c = ET.SubElement(r, '{'+NS['a']+'}tc', attrs)
            for line in text.split('\n'):
                p = ET.SubElement(c, '{'+NS['a']+'}p')
                ET.SubElement(p, '{'+NS['a']+'}t').text = line
    row([('版型', {}), ('400 基本型', {'gridSpan':'2'}), ('', {'hMerge':'1'}), ('500豪华型', {})])
    row([('MSRP（万）', {}), ('8.99', {'gridSpan':'2'}), ('', {'hMerge':'1'}), ('10.99', {})])
    row([('比例', {}), ('80%', {}), ('', {}), ('20%', {})])
    row([('配置', {}), ('', {}), ('', {}), ('400基本+', {})])
    row([('', {'vMerge':'1'}), ('LED大灯', {}), ('后排出风口', {}), ('100km续航\n电动前备箱', {})])
    draft = _parse_native_table(table)
    a,b = draft['columns']
    assert a['price'] == 8.99 and b['price'] == 10.99
    assert b['base'] == a['name']
    assert a['text'] == 'LED大灯\n后排出风口'
    assert '20%' not in b['text']
    draft['model'] = 'Test'
    snap = make_snapshot(draft)
    assert next(c for c in snap.cells if c['no'] == 1)['values'][b['name']].startswith('[待定]')
