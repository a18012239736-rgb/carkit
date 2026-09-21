"""Local editable-PPTX ladder import; all inferred data is a review draft."""
from __future__ import annotations
import copy
import datetime
import posixpath
import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from .models import Snapshot
from .rules import Rules

NS = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
UNKNOWN = '[待定]PPT未说明'

_BASE_MARKERS = ('基础配置', '标准配置', '入门配置', '全系标配', '标配')

def _is_trim_name(text):
    """判断文本块是否可能是版型名称，避免把“基础型”写死。"""
    text = str(text or '').strip()
    if not text or len(text) > 32 or '+' in text or re.search(r'价格|配置表|车型|轴距|指导价', text):
        return False
    if re.search(r'(型|版|款|系|级|配置|车型)$', text):
        return True
    return bool(re.fullmatch(r'(?:Pro|Max|Ultra|Plus|Air|Lite|Premium|Sport|智享|高配|低配|高功率|低功率|长续航|短续航)', text, re.I)
                or re.fullmatch(r'\d+(?:km|KM|kWh)', text))

def _base_from_marker(marker, trim_names):
    marker = str(marker or '').strip()
    if any(marker.startswith(x) for x in _BASE_MARKERS):
        return None
    m = re.match(r'(.+?)\s*[+＋]', marker)
    if m:
        candidate = m.group(1).strip()
        def key(s):
            return re.sub(r'(型|版)$', '', re.sub(r'\s+', '', s)).casefold()
        matches = [n for n in trim_names if key(n) == key(candidate)]
        if len(matches) != 1:
            raise ValueError('继承版型无法唯一匹配：' + candidate)
        return matches[0]
    m = re.search(r'(?:基于|继承|沿用)\s*(.+?)(?:配置|增加|升级|：|:|$)', marker)
    if m:
        candidate = m.group(1).strip()
        return candidate if candidate in trim_names else None
    return None

def _table_rows(blocks):
    """从图形表格展开出的单元格块中按 y 聚合行。"""
    rows=[]
    for block in blocks:
        if not block.get('w') or not block.get('h'):
            continue
        row=next((r for r in rows if abs(r[0]-block['y']) <= max(block['h']*.35, 1000)), None)
        if row is None:
            row=[block['y'], []]; rows.append(row)
        row[1].append(block)
    return [sorted(cells,key=lambda b:b['x']) for _,cells in sorted(rows,key=lambda r:r[0]) if len(cells)>=2]

def _root(z, name):
    entry = z.getinfo(name)
    if entry.file_size > 20_000_000:
        raise ValueError('PPT页面内容过大，请拆分后导入')
    data = z.read(name)
    if b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        raise ValueError('不支持带外部实体的PPT')
    return ET.fromstring(data)

def _slides(z):
    rels = {n.attrib['Id']: n.attrib['Target'] for n in _root(z, 'ppt/_rels/presentation.xml.rels')
            if n.attrib.get('TargetMode') != 'External'}
    return [posixpath.normpath('ppt/'+rels[n.attrib['{'+NS['r']+'}id']])
            for n in _root(z, 'ppt/presentation.xml').findall('p:sldIdLst/p:sldId', NS)]

def _paragraphs(node):
    result = []
    for paragraph in node.findall('.//a:p', NS):
        # Runs are formatting fragments, not line boundaries.
        text = ''.join(c.text or '' if c.tag == '{'+NS['a']+'}t' else '\n'
                       for c in paragraph.iter() if c.tag in {'{'+NS['a']+'}t', '{'+NS['a']+'}br'})
        result.extend(line.strip() for line in text.splitlines() if line.strip())
    return result

def _blocks(root):
    result=[]
    def walk(parent, ox=0, oy=0, sx=1, sy=1):
        for node in parent:
            kind=node.tag.split('}')[-1]
            if kind=='grpSp':
                x=node.find('p:grpSpPr/a:xfrm',NS)
                if x is None: continue
                def pt(tag, a, default):
                    q=x.find('a:'+tag,NS)
                    return float(q.get(a,default)) if q is not None else default
                scale_x=pt('ext','cx',1)/max(pt('chExt','cx',1),1)
                scale_y=pt('ext','cy',1)/max(pt('chExt','cy',1),1)
                walk(node,ox+sx*(pt('off','x',0)-scale_x*pt('chOff','x',0)),
                     oy+sy*(pt('off','y',0)-scale_y*pt('chOff','y',0)),sx*scale_x,sy*scale_y)
            elif kind in {'sp','graphicFrame'}:
                x=node.find('p:spPr/a:xfrm',NS) if kind=='sp' else node.find('p:xfrm',NS)
                if x is None:continue
                off=x.find('a:off',NS); ext=x.find('a:ext',NS)
                if off is None:continue
                px=ox+sx*float(off.get('x',0)); py=oy+sy*float(off.get('y',0))
                w=sx*float(ext.get('cx',0)) if ext is not None else 0
                h=sy*float(ext.get('cy',0)) if ext is not None else 0
                table=node.find('.//a:tbl',NS)
                if table is not None:
                    widths=[float(c.get('w',0))*sx for c in table.findall('a:tblGrid/a:gridCol',NS)]
                    yy=py
                    for row in table.findall('a:tr',NS):
                        xx=px; rh=float(row.get('h',0))*sy
                        for i,cell in enumerate(row.findall('a:tc',NS)):
                            lines=_paragraphs(cell)
                            cw=widths[i] if i<len(widths) else 0
                            if lines:result.append({'x':xx,'y':yy,'w':cw,'h':rh,'lines':lines})
                            xx+=cw
                        yy+=rh
                else:
                    lines=_paragraphs(node)
                    if lines:result.append({'x':px,'y':py,'w':w,'h':h,'lines':lines})
    tree=root.find('p:cSld/p:spTree',NS)
    if tree is not None:walk(tree)
    return sorted(result,key=lambda b:(b['y'],b['x']))

def list_pages(path):
    with ZipFile(path) as z:
        return [{'page':i+1,'title':' / '.join(b['lines'][0] for b in _blocks(_root(z,s))[:2])[:100] or '无可编辑文本'}
                for i,s in enumerate(_slides(z))]

def parse_page(path,page):
    with ZipFile(path) as z:
        slides=_slides(z)
        if type(page) is not int or not 1<=page<=len(slides):raise ValueError('页码超出范围')
        root=_root(z,slides[page-1])
        blocks=_blocks(root)
    tables = [_parse_native_table(t) for t in root.findall('.//a:tbl', NS)]
    tables = [t for t in tables if t is not None]
    if len(tables) > 1:
        raise ValueError('本页包含多个配置表，请拆分后导入，避免混合车型。')
    if tables:
        result = tables[0]
        result.update(page=page, source=Path(path).name,
                      model=re.split(r'商品|产品', Path(path).stem)[0],
                      source_text='\n'.join('\n'.join(b['lines']) for b in blocks))
        return result
    # First support conventional text-block ladder pages.
    bodies=[b for b in blocks if re.match(r'^(?:基础配置\s*[:：]|.+?\s*[+＋]\s*[:：])',b['lines'][0])]
    if not bodies:
        return _parse_table_page(path, page, blocks)
    bodies.sort(key=lambda b:b['x'])
    columns=[]; used=set()
    # Names are collected before bases are resolved, so names like Pro/Max are valid.
    possible_names=[b['lines'][0].strip() for b in blocks if len(b['lines'])==1 and _is_trim_name(b['lines'][0])]
    for body in bodies:
        center=body['x']+body['w']/2
        candidates=[b for b in blocks if b['y']<body['y'] and len(b['lines'])==1
                    and _is_trim_name(b['lines'][0])
                    and '+' not in b['lines'][0]
                    and abs(b['x']+b['w']/2-center)<max(body['w']*.65,300000)]
        if len(candidates)!=1:raise ValueError('版型列头无法唯一对应，请使用每列上方一个版型名称的配置阶梯页')
        header=candidates[0]; name=header['lines'][0]
        if name in used:raise ValueError('版型名称重复，请先在PPT中区分')
        used.add(name)
        prices=[b for b in blocks if header['y']<b['y']<body['y'] and len(b['lines'])==1
                and re.fullmatch(r'\d+(?:\.\d+)?(?:万元|万)?',b['lines'][0])
                and abs(b['x']+b['w']/2-center)<max(body['w']*.65,300000)]
        price=float(re.sub(r'万元|万','',prices[0]['lines'][0])) if len(prices)==1 else None
        marker=body['lines'][0]
        base=_base_from_marker(marker, possible_names)
        columns.append({'name':name,'base':base,'price':price,'text':'\n'.join(body['lines'][1:])})
    texts='\n'.join('\n'.join(b['lines']) for b in blocks)
    model_candidates=[b['lines'][0] for b in blocks if len(b['lines'])==1 and re.fullmatch(r'[A-Za-z]+[\w -]*\d[\w -]*',b['lines'][0])]
    price_kind='TP价格' if re.search(r'TP\s*价格',texts,re.I) else ('指导价' if '指导价' in texts else '未确定')
    return {'model':model_candidates[0] if len(model_candidates)==1 else Path(path).stem.split('产品')[0],
            'page':page,'source':Path(path).name,'price_kind':price_kind,'columns':columns,
            'source_text':texts,'warnings':['请确认版型与继承关系；未写配置保留待定，不按无配置处理。',
            '仅当明确选择指导价时，价格才用于指导价比较。']}

def _parse_native_table(table):
    """Use OOXML grid indices and spans; empty cells must not shift columns."""
    rows = []
    for row in table.findall('a:tr', NS):
        cells = []
        for index, cell in enumerate(row.findall('a:tc', NS)):
            cells.append({'index': index, 'span': int(cell.get('gridSpan', '1')),
                          'merged': cell.get('hMerge') == '1',
                          'lines': _paragraphs(cell)})
        rows.append(cells)
    header_index = next((i for i, row in enumerate(rows)
                         if row and ''.join(row[0]['lines']).strip() in
                         ('版型', '车型', '配置项目', '配置项', '项目')
                         and sum(bool(c['lines']) and not c['merged'] for c in row[1:]) >= 2), None)
    if header_index is None:
        return None
    headers = [c for c in rows[header_index][1:] if c['lines'] and not c['merged']]
    columns = [{'name': ' '.join(c['lines']).strip(), 'base': None,
                'price': None, 'text': ''} for c in headers]
    names = [c['name'] for c in columns]
    if len(set(names)) != len(names):
        raise ValueError('表格版型名称重复，请先区分。')
    warnings = ['已按表格合并单元格识别，请核对版型、价格及继承关系。']
    price_kind = '未确定'
    previous_label = ''
    for row in rows[header_index + 1:]:
        label = ''.join(row[0]['lines']).strip() or previous_label
        previous_label = label
        if re.search(r'成本|边际|贡献率|售价差|比例|占比', label):
            continue
        price_row = bool(re.search(r'MSRP|指导价|TP\s*价格|售价|价格', label, re.I))
        if price_row:
            price_kind = '指导价' if re.search(r'MSRP|指导价', label, re.I) else ('TP价格' if 'TP' in label.upper() else '未确定')
        for header, column in zip(headers, columns):
            cells = [c for c in row if header['index'] <= c['index'] < header['index'] + header['span'] and not c['merged']]
            lines = [line for c in cells for line in c['lines']]
            if price_row:
                value = ''.join(lines).strip()
                if value:
                    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:万元|万|元)?', value)
                    if match:
                        column['price'] = float(match[1]) / (10000 if '元' in label and '万' not in label else 1)
                    else:
                        warnings.append(f"{column['name']}价格需核对：{value}")
                continue
            for line in lines:
                if re.fullmatch(r'.+?[+＋]\s*[:：]?', line.strip()):
                    column['base'] = _base_from_marker(line, names)
                elif line.strip().rstrip(':：') not in _BASE_MARKERS:
                    column['text'] += ('' if label in ('配置', '基础配置', '配置内容') else label + '：') + line + '\n'
    for column in columns:
        column['text'] = column['text'].strip()
    return {'columns': columns, 'price_kind': price_kind, 'warnings': warnings,
            'parser': '原生表格（合并单元格）'}


def _parse_table_page(path, page, blocks):
    """解析常见横向配置表：首行版型、次行价格、首列配置名称。"""
    rows=_table_rows(blocks)
    if len(rows)<2:
        raise ValueError('未识别到配置阶梯文本或表格，请选择配置阶梯页；图片式页面暂不支持自动识别。')
    header_idx=next((i for i,row in enumerate(rows) if len(row)>=2 and sum(_is_trim_name(c['lines'][0]) for c in row)>=2), None)
    if header_idx is None:
        raise ValueError('未识别到版型列，请确保表格首行包含版型名称（如标准版、Pro、Max）。')
    header=rows[header_idx]
    trim_headers=[c for c in header if len(c['lines'])==1 and _is_trim_name(c['lines'][0])]
    if trim_headers and trim_headers[0] is header[0]:
        trim_headers.sort(key=lambda c:c['x'])
        names=[c['lines'][0].strip() for c in trim_headers]
        columns=[]
        for i,h in enumerate(trim_headers):
            center=h['x']+h['w']/2
            below=[b for b in blocks if b['y']>h['y'] and abs(b['x']+b['w']/2-center)<max(h['w'],600000)]
            prices=[b for b in below if len(b['lines'])==1 and re.fullmatch(r'\d+(?:\.\d+)?(?:万元|万)?',b['lines'][0])]
            body=next((b for b in below if b not in prices and not _is_trim_name(b['lines'][0])),None)
            columns.append({'name':names[i],
                            'base':names[0] if i and re.search(r'基础|入门|标准',names[0]) else None,
                            'price':float(re.sub(r'万元|万','',prices[0]['lines'][0])) if prices else None,
                            'text':'\n'.join(body['lines']) if body else ''})
        return {'model':Path(path).stem.split('产品')[0], 'page':page, 'source':Path(path).name,
                'price_kind':'未确定', 'columns':columns,
                'source_text':'\n'.join(' '.join(b['lines']) for b in blocks),
                'warnings':['已按并排版型卡片识别，请核对版型、价格和继承关系。']}
    names=[c['lines'][0].strip() for c in header[1:] if _is_trim_name(c['lines'][0])]
    if len(names)<2:
        raise ValueError('表格中的版型数量不足，请至少保留两个版型列。')
    col_count=len(names); columns=[{'name':n,'base':None,'price':None,'text_lines':[]} for n in names]
    texts=[]; price_kind='未确定'
    for row in rows[header_idx+1:]:
        cells=[c['lines'] for c in row]
        if not cells: continue
        label=' '.join(cells[0]).strip()
        values=[(' '.join(x).strip() if x else '') for x in cells[1:1+col_count]]
        if re.search(r'指导价|TP价格|价格',label):
            price_kind='TP价格' if 'TP' in label.upper() else ('指导价' if '指导' in label else '未确定')
            for i,v in enumerate(values):
                m=re.search(r'(\d+(?:\.\d+)?)',v)
                if m: columns[i]['price']=float(m.group(1))
        elif label:
            for i,v in enumerate(values):
                if v: columns[i]['text_lines'].append(f'{label}: {v}')
    for c in columns:
        c['text']='\n'.join(c.pop('text_lines'))
    all_text='\n'.join(' '.join(b['lines']) for b in blocks)
    model_candidates=[b['lines'][0] for b in blocks if len(b['lines'])==1 and re.fullmatch(r'[A-Za-z]+[\w -]*\d[\w -]*',b['lines'][0])]
    return {'model':model_candidates[0] if len(model_candidates)==1 else Path(path).stem.split('产品')[0],
            'page':page,'source':Path(path).name,'price_kind':price_kind,'columns':columns,
            'source_text':all_text,'warnings':['已按表格结构识别；请核对版型列、价格和配置映射。',
            '表格未明确继承关系，默认各版型独立配置。']}

def _apply(text, values, evidence, leftovers):
    def put(no,value,line):
        values[no]=value;evidence.setdefault(no,[]).append(line)
    for line in text.splitlines():
        line=line.strip()
        if not line:continue
        # Keep the full sentence for compound scope (mirrors/seats).
        t=line.replace('吋','寸').replace('英寸','寸').replace('（','(').replace('）',')')
        matched=False
        def setv(no,value):
            nonlocal matched
            matched=True;put(no,value,line)
        if re.search(r'选装|待定|暂定|取消|删除|减配|不配|不含|不支持|^无',t):
            # Never let a removal/uncertain upgrade silently retain its inherited value.
            stripped=re.sub(r'选装|待定|暂定|取消|删除|减配|不配|不含|不支持|^无','',t)
            trial=copy.deepcopy(values); touched={}; ignored=[]
            _apply(stripped,trial,touched,ignored)
            for no in touched:
                put(no,'[待定]'+line+'（请确认状态）',line)
            leftovers.append(line+'（需人工确认配置状态）');continue
        m=re.search(r'(\d+)\s*km',t,re.I)
        if m:setv(1,m[1]+'km')
        m=re.search(r'(\d+)\s*V(?:架构|平台|高压)',t,re.I)
        if m:setv(3,m[1]+'V')
        if '热泵' in t:setv(40,'●')
        m=re.search(r'(?:R)?(\d+)寸?(钢|铝(?:合金)?)轮毂',t)
        if m:setv(4,'R'+m[1]+('钢' if m[2]=='钢' else '铝')+'轮毂')
        m=re.search(r'(\d+)气囊',t)
        previous_evidence=list(evidence.get(5,[]))
        if m:setv(5,m[1]+'气囊')
        for component, number in [('侧气帘',2),('中央安全气囊',1)]:
            if component not in t:continue
            previous = re.search(r'(\d+)气囊',str(values.get(5,'')))
            already_counted = bool(re.search(r'(?:含|包含|包括|已含)'+component,t)) or (
                not m and any(component in source for source in previous_evidence))
            if previous and not already_counted:
                setv(5,str(int(previous[1])+number)+'气囊')
            elif not previous:
                setv(5,'[待定]'+component+'已配置，气囊基础数量未明确')
        if '540' in t and ('影像' in t or '全景' in t):setv(7,'540影像')
        elif '360' in t and '影像' in t:setv(7,'360影像')
        for value in ['城市NOA','高速NOA','基础L2']:
            if value in t:setv(9,value);break
        if '激光雷达' in t:
            m=re.search(r'(\d+)[颗个]激光雷达',t)
            setv(8,m[1]+'颗激光雷达' if m else '[待定]有激光雷达，数量未写')
        if 'LED' in t and '灯' in t:setv(17,'LED大灯')
        if '后雨刮' in t or '后雨刷' in t:setv(19,'●')
        if '外后视镜' in t:setv(20,'●'+t.split('外后视镜',1)[1])
        from .screen_config import normalize_screen
        for phrase in re.split(r'[+＋；;]', t):
            screens = [no for no, keyword in ((21,'中控'), (22,'副驾'), (29,'仪表'))
                       if keyword in phrase and (no != 22 or '屏' in phrase)]
            for no in screens:
                setv(no, '[待定]'+phrase if len(screens)>1 else normalize_screen(phrase.strip(), no))
        m=re.search(r'[45]G',t)
        if m:setv(23,m[0])
        if '皮质方向盘' in t:setv(25,'仿皮')
        if '方向盘加热' in t:setv(27,'●')
        if 'HUD' in t.upper():setv(30,'P-HUD' if 'P-HUD' in t.upper() else 'AR-HUD' if 'AR-HUD' in t.upper() else 'HUD')
        if '无线充电' in t:setv(33,'●'+t)
        if '仿皮座椅' in t:setv(34,'仿皮')
        elif '真皮座椅' in t:setv(34,'真皮')
        elif '织物座椅' in t:setv(34,'织物')
        if '座椅电调' in t or re.search(r'[主副]驾\d+向',t):
            # A known power adjustment without a direction count is still unresolved for valuation.
            setv(35,'[待定]'+t+'（请确认主副驾方向数）')
        from .seat_functions import from_text
        subs=copy.deepcopy(values.get(36,{}))
        if not isinstance(subs,dict):subs={}
        if any(feature in t for feature in ('通风','加热','按摩','头枕音响')) and any(scope in t for scope in ('座椅','主驾','副驾','前排','二排','后排','头枕音响')):
            additions=from_text(t if '二排' not in t and '后排' not in t else '', t if '二排' in t or '后排' in t else '', t if '头枕音响' in t else '')
            subs.update({key:value for key,value in additions.items() if value!='✕'})
            setv(36,subs)
        m=re.search(r'(\d+)扬(?:声器|伯牙之音)',t)
        if m:setv(37,m[1]+'扬声器')
        if '车外扬声器' in t:setv(38,'[待定]有车外扬声器，数量未写')
        m=re.search(r'(\d+)色氛围灯',t)
        if m:setv(39,m[1]+'色氛围灯')
        if '后排出风口' in t:setv(41,'●')
        if '冰箱' in t:setv(43,'●')
        if '感应雨刮' in t or '感应雨刷' in t:setv(44,'●')
        if '座椅记忆' in t:
            setv(45,'前排座椅记忆' if '前排' in t or ('主驾' in t and '副驾' in t)
                 else '主驾座椅记忆' if '主驾' in t else '副驾座椅记忆' if '副驾' in t
                 else '[待定]座椅记忆位置未说明')
        if '电动后备箱' in t or '电动后备厢' in t:setv(13,'●')
        for no, aliases in {6:['悬架软硬','可变阻尼','FSD','悬架高低'],11:['电吸门','电动吸合门'],12:['电动前备箱','电动前备厢'],14:['车顶行李架'],15:['主动进气格栅','主动闭合式进气格栅'],16:['对外放电'],18:['全景天窗','全景天幕','电动天窗'],22:['副驾娱乐屏','副驾屏'],24:['KTV'],26:['方向盘调节','方向盘手动'],28:['方向盘记忆'],31:['内后视镜'],32:['USB','Type-C']}.items():
            if no != 22 and any(a.lower() in t.lower() for a in aliases):setv(no,t)
        # Always preserve mixed phrases; unhandled non-checklist details stay visible for review.
        if not matched or re.search(r'APA|芯片|钥匙|怀挡|Carmind|自动空调',t):leftovers.append(line)

def make_snapshot(draft):
    columns=draft.get('columns',[])
    if not columns:raise ValueError('至少需要一个版型')
    names=[str(c['name']).strip() for c in columns]
    if any(not n for n in names) or len(set(names))!=len(names):raise ValueError('版型名称不能为空或重复')
    model=str(draft.get('model','')).strip()
    if not model:raise ValueError('请填写本品车型名称')
    lookup=dict(zip(names,columns)); expanded={}; traces={}; remaining={}; declared={}
    def expand(name,stack):
        if name in expanded:return
        if name in stack:raise ValueError('继承关系存在循环')
        col=lookup[name];base=col.get('base')
        if base and base not in lookup:raise ValueError('比较基准不存在：'+base)
        if base:
            expand(base,stack+[name]); vals=copy.deepcopy(expanded[base]); ev=copy.deepcopy(traces[base])
        else:
            vals={it['no']:'✕' for it in Rules().items if not it.get('merged_into')}
            from .seat_functions import empty
            vals[36]=empty();ev={}
        before={no:len(lines) for no,lines in ev.items()}
        rest=[];_apply(str(col.get('text','')),vals,ev,rest)
        declared[name]={no for no,lines in ev.items() if len(lines)>before.get(no,0)}
        # A range in an upgrade column may be a delta, not the absolute range.
        if base and re.search(r'\d+\s*km续航', str(col.get('text', '')), re.I):
            stated = re.search(r'(\d+)\s*km续航', str(col.get('text', '')), re.I)
            named_range = re.match(r'(\d{3,4})', name)
            if named_range and stated[1] != named_range[1]:
                vals[1] = '[待定]续航原文' + stated[0] + '，请确认总续航或增量'
                rest.append(vals[1])
        expanded[name]=vals;traces[name]=ev;remaining[name]=rest
    for name in names:expand(name,[])
    trims=[]
    for name in names:
        col=lookup[name];price=col.get('price')
        if price not in (None,''):
            price=float(price)
            if not 0<price<10000:raise ValueError('价格应为正数，单位万元')
        else:price=None
        trims.append({'name':name,'price_guide':price if draft.get('price_kind')=='指导价' else None,
                      'price_source':draft.get('price_kind','未确定'),'price_reference':price,'base':col.get('base'),
                      'range':expanded[name][1] if not str(expanded[name][1]).startswith('[待定]') else ''})
    cells=[]
    for it in Rules().items:
        no=it['no']
        if it.get('merged_into'):continue
        ev=[]
        for name in names:
            if no in traces[name]:ev.append(name+'：'+'；'.join(dict.fromkeys(traces[name][no])))
        cells.append({'no':no,'values':{name:expanded[name][no] for name in names},
                      'basis':f"{draft.get('source','PPT')} P{draft.get('page','')} / "+(' | '.join(ev) or '本页未说明')})
    snap=Snapshot(model=model,version='ppt-import-v2',date=datetime.date.today().isoformat(),status='待确认',
        trims=trims,cells=cells,
        pending=[],
        rulings=[{'type':'ppt_import','source':draft.get('source'),'page':draft.get('page'),
                  'draft':copy.deepcopy(draft),'remaining':remaining}])
    from .snapshot import prepare_snapshot
    prepare_snapshot(snap)
    for cell in snap.cells:
        for name in names:
            if cell['no'] in declared[name] and not isinstance(cell['values'][name],dict):
                cell['links'].pop(name,None)
    return snap
