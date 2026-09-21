import copy
from engine.ppt_import import make_snapshot, UNKNOWN
from engine.differ import _is_pending
from api.bridge import Bridge
import pytest

def draft():
    return {'model':'测试车型','page':20,'source':'test.pptx','price_kind':'TP价格','columns':[
        {'name':'基础型','base':None,'price':8.99,'text':'500km续航+800V架构+热泵空调\n主副驾座椅电调\n12扬声器+头枕音响'},
        {'name':'舒适型','base':'基础型','price':9.79,'text':'前排座椅通风加热\n18寸铝轮毂'},
        {'name':'长续航基础型','base':'基础型','price':9.79,'text':'600km续航'},
        {'name':'豪华型','base':'舒适型','price':11.29,'text':'600km续航\n城市NOA（带激光雷达）\n17扬伯牙之音\n前排座椅按摩'}]}

def test_branch_inheritance_and_tp_price():
    snap=make_snapshot(draft())
    cells={c['no']:c['values'] for c in snap.cells}
    assert all(t['price_guide'] is None for t in snap.trims)
    assert snap.trims[0]['price_reference']==8.99
    assert cells[1]['豪华型']=='600km'
    assert all(cells[36]['豪华型'][seat+feature]=='●' for seat in ('主驾','副驾') for feature in ('通风','加热','按摩'))
    assert cells[36]['长续航基础型']['主驾通风']=='✕'
    assert cells[37]['豪华型']=='17扬声器'
    assert cells[37]['长续航基础型']=='12扬声器'
    assert _is_pending(cells[35]['基础型'])
    assert _is_pending(cells[8]['豪华型'])
    assert _is_pending(cells[36]['豪华型']['主驾头枕音响'])  # 原PPT未说明头枕属于哪一座位
    assert cells[2]['基础型']=='✕'

def test_side_curtains_add_two_without_double_counting():
    d=draft()
    d['columns'][0]['text']='4气囊'
    d['columns'][1]['text']='侧气帘'
    d['columns'][2]['text']='侧气帘\n侧气帘'
    d['columns'][3]['text']='6气囊（含侧气帘）'
    cells={c['no']:c['values'] for c in make_snapshot(d).cells}
    assert cells[5]['基础型']=='4气囊'
    assert cells[5]['舒适型']=='6气囊'
    assert cells[5]['长续航基础型']=='6气囊'
    assert cells[5]['豪华型']=='6气囊'
    d['columns'][0]['text']='侧气帘'
    cells={c['no']:c['values'] for c in make_snapshot(d).cells}
    assert _is_pending(cells[5]['基础型'])

def test_old_import_missing_values_are_reparsed_without_losing_edits():
    from engine.snapshot import resolve
    d=draft(); d['columns'][0]['text']+='\n对外放电'
    snap=make_snapshot(d);snap.version='ppt-import-v1'
    for c in snap.cells:
        if c['no'] in (2,16):c['values']['基础型']=UNKNOWN
        if c['no']==40:c['values']['基础型']='[待定]方案讨论中'
    updated=resolve(snap)
    cells={c['no']:c['values'] for c in updated.cells}
    assert cells[2]['基础型']=='✕'
    assert cells[16]['基础型']=='对外放电'
    assert cells[40]['基础型']=='[待定]方案讨论中'

def test_import_validation_and_confirmation(tmp_path):
    d=draft();d['columns'][0]['base']='豪华型'
    with pytest.raises(ValueError,match='循环'):make_snapshot(d)
    d=draft();d['columns'][1]['base']='不存在'
    with pytest.raises(ValueError,match='不存在'):make_snapshot(d)
    bridge=Bridge(str(tmp_path))
    res=bridge.ppt_preview(draft())
    assert res['ok']
    assert not list((tmp_path/'快照').glob('*'))
    assert not bridge.save_ppt_snapshot(res['snapshot'],False)['ok']
    saved=bridge.save_ppt_snapshot(res['snapshot'],True)
    assert saved['ok']
    assert bridge.load_snapshot(saved['path'])['snapshot']['trims'][0]['price_guide'] is None

def test_uncertain_or_removed_upgrade_does_not_inherit_as_standard():
    d=draft();d['columns'][1]['text']='取消热泵空调\n选装600km续航'
    snap=make_snapshot(d)
    cells={c['no']:c['values'] for c in snap.cells}
    assert _is_pending(cells[40]['舒适型'])
    assert _is_pending(cells[1]['舒适型'])
    assert cells[40]['基础型']=='●'

def test_xml_run_fragments_and_presentation_page_order(tmp_path):
    from zipfile import ZipFile
    from engine.ppt_import import parse_page, list_pages
    from xml.etree import ElementTree as E
    from engine.ppt_import import NS
    def tag(prefix,name):return '{'+NS[prefix]+'}'+name
    slide=E.Element(tag('p','sld'));tree=E.SubElement(E.SubElement(slide,tag('p','cSld')),tag('p','spTree'))
    def shape(x,y,paragraphs):
        node=E.SubElement(tree,tag('p','sp'));xf=E.SubElement(E.SubElement(node,tag('p','spPr')),tag('a','xfrm'))
        E.SubElement(xf,tag('a','off'),x=str(x),y=str(y));E.SubElement(xf,tag('a','ext'),cx='1000000',cy='200000')
        body=E.SubElement(node,tag('p','txBody'))
        for fragments in paragraphs:
            p=E.SubElement(body,tag('a','p'))
            for fragment in fragments:E.SubElement(E.SubElement(p,tag('a','r')),tag('a','t')).text=fragment
    shape(0,0,[['基础型']]);shape(0,300000,[['8','.99']]);shape(0,600000,[['基础配置：'],['500','km续航']])
    shape(2000000,0,[['高配型']]);shape(2000000,300000,[['9.99']]);shape(2000000,600000,[['基础型','+：'],['600km续航']])
    shape(-2000000,300000,[['TP价格：']])
    path=tmp_path/'test.pptx'
    with ZipFile(path,'w') as z:
        z.writestr('ppt/presentation.xml',f'<p:presentation xmlns:p="{NS["p"]}" xmlns:r="{NS["r"]}"><p:sldIdLst><p:sldId id="256" r:id="rel1"/></p:sldIdLst></p:presentation>')
        z.writestr('ppt/_rels/presentation.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rel1" Target="slides/slide99.xml"/></Relationships>')
        z.writestr('ppt/slides/slide99.xml',E.tostring(slide))
    assert len(list_pages(path))==1
    d=parse_page(path,1)
    assert d['columns'][0]['price']==8.99
    assert d['columns'][0]['text']=='500km续航'
    assert d['columns'][1]['base']=='基础型'
    assert d['price_kind']=='TP价格'
    with pytest.raises(ValueError,match='页码'):parse_page(path,20)

def test_side_by_side_trim_cards_are_not_treated_as_label_column():
    from engine.ppt_import import _parse_table_page
    def block(x,y,text,w=1_500_000,h=300_000):
        return {'x':x,'y':y,'w':w,'h':h,'lines':text.split('\n')}
    blocks=[block(1_000_000,1_000_000,'500km 基础型'),block(4_000_000,1_000_000,'500km 舒适型'),
            block(1_000_000,2_000_000,'7.58'),block(4_000_000,2_000_000,'8.28'),
            block(1_000_000,3_000_000,'4气囊\n6扬声器',1_800_000,1_200_000),
            block(4_000_000,3_000_000,'6气囊\n8扬声器',1_800_000,1_200_000)]
    draft=_parse_table_page('T13T产品策略.pptx',1,blocks)
    assert [c['name'] for c in draft['columns']]==['500km 基础型','500km 舒适型']
    assert [c['price'] for c in draft['columns']]==[7.58,8.28]
    assert draft['columns'][1]['base']=='500km 基础型'
    assert draft['columns'][1]['text']=='6气囊\n8扬声器'
