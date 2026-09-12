"""Configuration ladder with explicit user-defined baselines and lossless evidence."""
from __future__ import annotations
import re
from decimal import Decimal
from .models import Cell, RawTable
from .rules import Rules

EMPTY = {'', '-', '—', '无', '不支持', '✕'}


def parts(cell, optional=False):
    if cell is None: return []
    result=[]
    for c in [cell]+list(cell.subs):
        # Subs in historical HTML may contain the head again; deduplicate.
        text=c.text.strip()
        if c.dot == ('○' if optional else '●') or (not optional and not c.dot and text not in EMPTY and '○' not in text):
            if text in EMPTY and c.dot != '●': continue
            value=text or '有'
            if value not in result: result.append(value)
    return result


def clean(s):
    return s.replace('英寸','寸').replace('●','').replace('（','(').replace('）',')').strip()


def features(raw):
    """Each feature is scalar or a set of independently inheritable subfeatures."""
    out=[]
    consumed=set()
    allowed={n for item in Rules().items for n in item.get('source_rows',[])}
    allowed |= {'手机互联/映射','感应雨刷功能','辅助泊车入位','循迹倒车','外观套件',
                 '芯片总算力','辅助驾驶芯片','哨兵模式/千里眼','内置行车记录仪',
                 '无钥匙进入功能','车窗一键升降功能','车窗防夹手功能','前/后电动车窗',
                 '车内化妆镜','自适应远近光','语音识别控制系统','多功能方向盘',
                 '空调温度控制方式','电动座椅记忆','前排座椅头枕扬声器',
                 '后排座椅头枕扬声器'}
    count=len(raw.trims)
    def get(name,i):
        r=raw.row(name)
        return parts(r.cells[i]) if r else []
    def add(key,values,scalar=False):
        out.append({'key':key,'values':values,'scalar':scalar})
    for row in raw.rows:
        name=row.name
        if name in consumed or name not in allowed: continue
        consumed.add(name)
        values=[parts(c) for c in row.cells]
        if name in {'CLTC纯电续航里程(km)','WLTC纯电续航里程(km)','NEDC纯电续航里程(km)'}:
            chosen=next((n for n in ['CLTC纯电续航里程(km)','WLTC纯电续航里程(km)','NEDC纯电续航里程(km)'] if raw.row(n)),None)
            if name!=chosen: continue
            add(name,[[name[:4]+'纯电续航'+clean(v)+'km' for v in vs] for vs in values],True)
        elif name in {'前轮胎规格','后轮胎规格','轮圈材质'}:
            consumed.update({'前轮胎规格','后轮胎规格','轮圈材质'})
            v=[]
            for i in range(count):
                tire=' '.join(get('前轮胎规格',i)); rear=' '.join(get('后轮胎规格',i)); material=' '.join(get('轮圈材质',i))
                f=re.search(r'R\s*(\d+)',tire,re.I); b=re.search(r'R\s*(\d+)',rear,re.I)
                size=('R'+f[1]) if f else ''
                if f and b and f[1]!=b[1]: size='前R'+f[1]+'后R'+b[1]
                v.append([size+material+'轮毂'] if size or material else [])
            add('轮毂',v,True)
        elif name in {'对外放电','对外交流放电功率(kW)','对外放电功率(kW)'}:
            consumed.update({'对外放电','对外交流放电功率(kW)','对外放电功率(kW)'})
            v=[]
            for i in range(count):
                has = bool(get('对外放电', i))
                power = ' '.join(get('对外交流放电功率(kW)', i) or get('对外放电功率(kW)', i))
                v.append([f'对外放电{clean(power)}kW' if has and power else '对外放电'] if has else [])
            add('对外放电', v, True)
        elif name in {'激光雷达数量','激光雷达品牌'}:
            consumed.update({'激光雷达数量','激光雷达品牌'})
            v=[]
            for i in range(count):
                number=' '.join(get('激光雷达数量', i))
                brand=' '.join(get('激光雷达品牌', i))
                brand=clean(brand).replace('HESAI','').replace('禾赛科技','禾赛').strip()
                if number:
                    count_text=re.sub(r'(个|颗|台)$', '', clean(number))
                    values=[f'{count_text}颗{brand}激光雷达' if brand else f'{count_text}颗激光雷达']
                elif brand:
                    values=[brand+'激光雷达']
                else:
                    values=[]
                v.append(values)
            add('激光雷达', v, True)
        elif name in {'主/副驾驶座安全气囊','前/后排侧气囊','前/后排头部气囊(气帘)'}:
            ns=['主/副驾驶座安全气囊','前/后排侧气囊','前/后排头部气囊(气帘)']
            consumed.update(ns)
            v=[]
            for i in range(count):
                total=0
                for n in ns:
                    text=' '.join(get(n,i))
                    if not text: continue
                    if '头部' in n: total+=2 # Left/right curtain, not four front/rear airbags.
                    elif n.startswith('主'):
                        total+=sum(1 for pos in ['主','副'] if re.search(pos+r'(?:●|(?=/|$))',text))
                    else:
                        total+=sum(2 for pos in ['前','后'] if re.search(pos+r'(?:●|(?=/|$))',text))
                v.append([f'{total}气囊'] if total else [])
            add('气囊',v,True)
        elif name in {'驾驶辅助影像','透明底盘/540度影像'}:
            consumed.update({'驾驶辅助影像','透明底盘/540度影像'})
            add('影像',[['540影像'] if get('透明底盘/540度影像',i) else [clean(x) for x in get('驾驶辅助影像',i)] for i in range(count)],True)
        elif name in {'主座椅调节方式','副座椅调节方式','主/副驾驶座电动调节'}:
            consumed.update({'主座椅调节方式','副座椅调节方式','主/副驾驶座电动调节'})
            for pos, source in [('主驾', '主座椅调节方式'), ('副驾', '副座椅调节方式')]:
                totals = []
                for i in range(count):
                    text = clean(' '.join(get(source, i)))
                    directions = 0
                    # Count standard base movements and support adjustments once.
                    # An explicit direction count overrides the usual two-way pair.
                    pattern = r'(?:前后调节|靠背调节|高低调节|腿部支撑(?:调节)?|腰部支撑(?:调节)?|腿托(?:调节)?|肩部支撑(?:调节)?|头枕(?:调节)?)(?:\((\d+)向\))?'
                    for match in re.finditer(pattern, text):
                        directions += int(match[1] or 2)
                    if not directions:
                        total = re.fullmatch(r'(?:主驾|副驾|座椅)?(\d+)向(?:电动|手动|电调|手调|调节)*', text)
                        if total:
                            directions = int(total[1])
                    totals.append([f'{pos}{directions}向调节'] if directions else ([pos+'座椅调节（'+text+'）'] if text else []))
                add(pos+'座椅调节', totals, True)
        elif name in {'巡航系统','辅助驾驶系统','辅助驾驶等级','辅助驾驶路段'}:
            # The source table splits one ADAS level over four rows. Present it
            # once so the ladder does not repeat the same upgrade four times.
            consumed.update({'巡航系统','辅助驾驶系统','辅助驾驶等级','辅助驾驶路段'})
            v=[]
            for i in range(count):
                cruise=' '.join(get('巡航系统', i))
                level=' '.join(get('辅助驾驶等级', i))
                route=' '.join(get('辅助驾驶路段', i))
                text=' '.join(get('辅助驾驶系统', i))
                if '城市' in route: values=['城市NOA']
                elif '高速' in route: values=['高速NOA']
                else:
                    values=[]
                    if 'L2' in level or 'L2' in text: values.append('基础L2辅助驾驶')
                    if '全速' in cruise: values.append('全速自适应巡航')
                    elif '定速' in cruise: values.append('定速巡航')
                v.append(values)
            add('辅助驾驶', v, True)
        elif name in {'电动后备厢','电动后备厢位置记忆','电动后备箱'}:
            consumed.update({'电动后备厢','电动后备厢位置记忆','电动后备箱'})
            v=[]
            for i in range(count):
                trunk=bool(get('电动后备厢', i) or get('电动后备箱', i))
                memory=bool(get('电动后备厢位置记忆', i))
                values=[]
                if trunk: values.append('电动后备厢')
                if memory: values.append('位置记忆')
                v.append(values)
            add('电动后备厢', v)
        elif name in {'手机无线充电功能','手机无线充电功率'}:
            consumed.update({'手机无线充电功能','手机无线充电功率'})
            v=[]
            for i in range(count):
                scope=' '.join(get('手机无线充电功能', i))
                power=' '.join(get('手机无线充电功率', i))
                if not scope and not power:
                    v.append([])
                else:
                    v.append([f'{clean(scope)}{clean(power)}手机无线充电'.strip()])
            add('手机无线充电', v, True)
        elif name in {'车内环境氛围灯','主动式环境氛围灯'}:
            consumed.update({'车内环境氛围灯','主动式环境氛围灯'})
            v=[]
            for i in range(count):
                color=' '.join(get('车内环境氛围灯', i))
                active=bool(get('主动式环境氛围灯', i))
                values=[]
                if color: values.append(clean(color)+'氛围灯')
                if active: values.append('主动式环境氛围灯')
                v.append(values)
            add('氛围灯', v)
        elif name == '外后视镜功能':
            values=[]
            for vs in [parts(c) for c in row.cells]:
                mapped=[]
                text=' '.join(vs)
                if '电动调节' in text: mapped.append('外后视镜电调')
                if '电动折叠' in text: mapped.append('外后视镜电动折叠')
                if '锁车自动折叠' in text: mapped.append('锁车自动折叠')
                if '加热' in text: mapped.append('外后视镜加热')
                values.append(list(dict.fromkeys(mapped)))
            add(name, values)
        elif name == '车内化妆镜':
            values=[]
            for c in row.cells:
                text=' '.join(parts(c))
                if '主驾' in text and '副驾' in text:
                    values.append(['主副驾化妆镜照明灯'])
                elif '主驾' in text:
                    values.append(['主驾化妆镜照明灯'])
                elif '副驾' in text:
                    values.append(['副驾化妆镜照明灯'])
                else:
                    values.append(['化妆镜照明灯'] if text else [])
            add(name, values)
        elif name == '方向盘位置调节':
            values=[]
            for c in row.cells:
                parts_value = parts(c)
                values.append(['/'.join(clean(value).replace('+', '/') for value in parts_value)] if parts_value else [])
            add(name, values, True)
        elif name in {'方向盘材质','多功能方向盘'}:
            consumed.update({'方向盘材质','多功能方向盘'})
            values=[]
            for i in range(count):
                material=' '.join(get('方向盘材质', i))
                multifunction=bool(get('多功能方向盘', i))
                material=clean(material)
                if material:
                    values.append([material + ('多功能方向盘' if multifunction else '方向盘')])
                elif multifunction:
                    values.append(['多功能方向盘'])
                else:
                    values.append([])
            add('方向盘', values, True)
        elif name in {'前排座椅功能','第二排座椅功能','后排座椅功能'}:
            v=[]
            for vs in values:
                feats=[]
                for item in vs:
                    scope=['主驾'] if re.search('仅驾驶位|仅主驾|主驾驶',item) else ['副驾'] if '副驾驶' in item else ['主驾','副驾'] if name.startswith('前') else ['后排']
                    for f in ['加热','通风','按摩']:
                        if f in item: feats.extend(p+'座椅'+f for p in scope)
                v.append(list(dict.fromkeys(feats)))
            add(name,v)
        else:
            scalar=name in {'中控屏幕尺寸','副驾驶位屏幕尺寸','4G/5G网络','方向盘材质','方向盘位置调节','液晶仪表尺寸','座椅材质','扬声器数量','车外扬声器数量','车内环境氛围灯','天窗类型','近光灯光源','电芯品牌','手机无线充电功率'}
            if name=='远光灯光源' and raw.row('近光灯光源') and all(get(name,i)==get('近光灯光源',i) for i in range(count)): continue
            if name=='中控彩色屏幕' and raw.row('中控屏幕尺寸'): continue
            if name=='车联网' and raw.row('4G/5G网络'): continue
            if name=='行车电脑显示屏幕' and raw.row('液晶仪表尺寸'): continue
            def fmt(value):
                value=clean(value)
                if name=='电池类型': return value if value.endswith('电池') else value+'电池'
                if name=='电芯品牌': return value+'电芯'
                if name=='中控屏幕尺寸': return value+'中控'
                if name=='液晶仪表尺寸': return value+'仪表'
                if name=='扬声器数量': return re.sub(r'个|喇叭','',value)+'扬声器'
                if name=='车外扬声器数量': return re.sub(r'个|喇叭','',value)+'个车外扬声器'
                if name=='近光灯光源': return value+'大灯'
                if name=='感应雨刷功能': return value.replace('式','')+'雨刷'
                if name=='4G/5G网络': return value+'车联网'
                if name=='空调温度控制方式': return value
                if name=='哨兵模式/千里眼': return '哨兵模式'
                if name=='座椅材质': return value+'座椅'
                if name=='方向盘材质': return value+'方向盘'
                if name=='方向盘位置调节': return value
                if name=='内后视镜功能': return value+'内后视镜'
                if name=='USB/Type-C接口数量': return 'USB/Type-C接口'+value
                if name=='语音识别控制系统': return '语音识别'
                if name=='多功能方向盘': return '多功能方向盘'
                if name=='前/后电动车窗': return ('前/后' if value=='有' else value)+'电动车窗'
                if name=='车窗一键升降功能': return ('全车' if value=='有' else value)+'电动车窗一键升降'
                if name=='车窗防夹手功能': return '防夹手'
                if name=='车内化妆镜': return value+'化妆镜照明灯'
                if name=='辅助驾驶芯片': return value+'辅助驾驶芯片'
                if name=='芯片总算力': return value+'算力'
                if name=='手机互联/映射': return value.replace('支持','')
                if name=='无钥匙进入功能': return ('驾驶位' if value=='有' else value)+'无钥匙进入'
                if name=='外观套件': return value+'外观套件'
                if name=='全液晶仪表盘': return '全液晶仪表'
                if name in {'天窗类型','可变悬架功能','辅助驾驶路段'}: return value
                if value=='有': return name
                return name+value
            add(name,[list(dict.fromkeys(fmt(v) for v in vs)) for vs in values],scalar)
    return out


def validate_plan(raw, plan):
    if not isinstance(plan,list) or not plan: raise ValueError('请至少选择一个版型。')
    seen=set()
    for row in plan:
        target=row.get('target'); base=row.get('base')
        if type(target) is not int or not 0<=target<len(raw.trims) or target in seen: raise ValueError('导出版型无效或重复。')
        if base is not None and (type(base) is not int or base not in seen): raise ValueError('比较基准须选择已排在前面的版型，不能自比、循环或引用未导出版型。')
        seen.add(target)
    return plan


def _price(value):
    """Keep prices compact and stable in Markdown, while preserving unknowns."""
    if value is None:
        return '待核'
    try:
        return f'{Decimal(str(value)):.2f}'.rstrip('0').rstrip('.')
    except Exception:
        return str(value)


def _option_lines(raw, trim_index):
    """Return one quoted line per optional row; options never enter standard deltas."""
    result = []
    for row in raw.rows:
        values = parts(row.cells[trim_index], optional=True)
        if not values:
            continue
        text = ' / '.join(clean(value) for value in values)
        result.append(f'{row.name}：{text}')
    return result


_BASE_GROUPS = [
    ('哨兵模式/千里眼', '内置行车记录仪'),
    ('无钥匙进入功能', '主动闭合式进气格栅'),
    ('前/后电动车窗', '车窗一键升降功能', '车窗防夹手功能'),
    ('方向盘', '方向盘材质', '方向盘位置调节', '多功能方向盘'),
    ('4G/5G网络', '语音识别控制系统'),
    ('座椅材质', '主驾座椅调节', '主驾支撑', '副驾座椅调节', '副驾支撑'),
    ('扬声器数量', '车外扬声器数量'),
    ('空调温度控制方式', '后座出风口'),
]


def _change_items(fs, trim_index, base_index):
    """Create normalized line items before applying the visual grouping."""
    items = []
    for feature in fs:
        cur = feature['values'][trim_index]
        prev = feature['values'][base_index] if base_index is not None else []
        if cur == prev:
            continue
        if base_index is None:
            # The one-touch row already conveys the window coverage; keeping
            # the generic front/rear window row would duplicate the same fact.
            if feature['key'] == '前/后电动车窗':
                continue
            if cur:
                items.append((feature['key'], '+'.join(cur)))
            continue
        if feature['scalar'] and cur and prev:
            left, right = ('（', '）') if feature['key'] in {'主驾座椅调节', '副驾座椅调节'} else ('(', ')')
            items.append((feature['key'], '+'.join(cur) + left + '+'.join(prev) + right))
        else:
            additions = [value for value in cur if value not in prev]
            removals = [value for value in prev if value not in cur]
            if additions:
                items.append((feature['key'], '+'.join(additions)))
            # A phone-mirroring set with a removed brand is shown as a value
            # change; ordinary inherited sets stay quiet when they only lose
            # a redundant source-table subvalue.
            if removals and cur and feature['key'] in {'手机互联/映射'}:
                items.append((feature['key'], '+'.join(cur) + '(' + '+'.join(prev) + ')'))
    return items


def _compact_items(items, base_index):
    if base_index is None:
        groups = {key: index for index, group in enumerate(_BASE_GROUPS) for key in group}
        grouped = []
        positions = {}
        for key, value in items:
            group_index = groups.get(key)
            if group_index is None:
                grouped.append(value)
                continue
            if group_index not in positions:
                positions[group_index] = len(grouped)
                grouped.append(value)
            else:
                grouped[positions[group_index]] += '+' + value
        return grouped
    # Upgrade blocks should remain relative to their chosen baseline.  Merge
    # repeated rows only; never pull inherited values back into the line.
    grouped = []
    positions = {}
    for key, value in items:
        if key in positions:
            grouped[positions[key]] += '+' + value
        else:
            positions[key] = len(grouped)
            grouped.append(value)
    return grouped


def _position_line(raw, plan):
    """Build a factual one-line model summary when the source table has it."""
    def first(name):
        row = raw.row(name)
        if not row:
            return ''
        values = parts(row.cells[plan[0]['target']])
        return clean(values[0]) if values else ''
    level = first('级别')
    energy = first('能源类型')
    if energy and level:
        bits = [energy.replace('纯电动', '纯电') + level]
    else:
        bits = [level or energy]
    range_row = next((row for row in raw.rows if '纯电续航里程' in row.name), None)
    ranges = []
    if range_row:
        for entry in plan:
            value = parts(range_row.cells[entry['target']])
            if value and value[0] not in ranges:
                ranges.append(value[0])
    if ranges:
        bits.append('CLTC续航' + '/'.join(clean(value) for value in ranges) + 'km')
    return '，'.join(value for value in bits if value)


def render(raw, plan):
    """Render the user-facing ladder in the accepted 5C paragraph format.

    The raw table remains lossless upstream.  This view is deliberately compact:
    the base trim contains the selected standard equipment, each following block
    contains only its relative delta, and optional equipment is listed once at the
    end instead of being repeated after every trim.
    """
    validate_plan(raw,plan)
    fs=features(raw)
    esc=lambda s: str(s).replace('|','\\|').replace('\n',' ')
    lines=[f'# 5C-看竞争-{esc(raw.model)}','']
    position = _position_line(raw, plan)
    if position:
        lines.append(f'{esc(raw.model)}，{esc(position)}。')
        lines.append('')
    lines.append(f'数据来源：汽车之家主站；抓取时间：{raw.scraped_at or "导入数据未记录"}。')
    if raw.series_id:
        lines.append(f'来源链接：https://www.autohome.com.cn/config/series/{esc(raw.series_id)}.html')
    elif isinstance(raw.source, str) and raw.source.startswith(('http://', 'https://')):
        lines.append(f'来源链接：{esc(raw.source)}')
    lines += ['', '## 版型与价格', '']
    range_row = next((row for row in raw.rows if '纯电续航里程' in row.name), None)
    if range_row:
        by_range = {}
        for entry in plan:
            index = entry['target']
            values = parts(range_row.cells[index])
            label = clean(values[0]) + 'km' if values else '续航待核'
            by_range.setdefault(label, []).append(raw.trims[index].short)
        if by_range:
            lines.extend(['```text'] + [f'{label}：{" / ".join(names)}' for label, names in by_range.items()] + ['```', ''])
    lines += [
              '| 版型 | 指导价/万元 | 比较基准 |', '|---|---:|---|']
    for entry in plan:
        t=raw.trims[entry['target']]; b=entry['base']
        lines.append(f'| {esc(t.short)} | {_price(t.price_guide)} | {esc(raw.trims[b].short) if b is not None else "基本配置"} |')
    lines+=['','## 配置','']
    for entry in plan:
        i,b=entry['target'],entry['base']; t=raw.trims[i]
        if b is None: title=f'基本配置：{t.short}（{_price(t.price_guide)}万）'
        else:
            p=raw.trims[b]
            delta=f'{Decimal(str(t.price_guide))-Decimal(str(p.price_guide)):+.2f}万' if None not in (t.price_guide,p.price_guide) else '价差待核'
            title=f'较{p.short} {delta}:({t.short})'
        lines += [f'**{esc(title)}**','']
        changes = _compact_items(_change_items(fs, i, b), b)
        if b is None:
            lines.extend(esc(c)+'  ' for c in changes)
        else:
            # The ladder is an upgrade view: show additions and explicit value
            # changes only. Inherited rows are already represented by the base.
            # A plus sign is reserved for joining related items within a line;
            # it is not a Markdown line prefix.
            lines.extend(esc(c)+'  ' for c in changes)
        if not changes: lines.append('配置相同，仅价格/续航差异。')
        lines.append('')
    option_blocks=[]
    for entry in plan:
        i=entry['target']; opts=_option_lines(raw, i)
        if opts:
            option_blocks.append((raw.trims[i].short, opts))
    if option_blocks:
        lines += ['## 选装', '']
        for trim_name, opts in option_blocks:
            lines += [f'**{esc(trim_name)}**', '']
            lines.extend('> 选装：' + esc(option) + '  ' for option in opts)
            lines.append('')
    return '\n'.join(lines)+'\n'


def validate_raw(raw):
    if not raw.trims or not raw.rows: raise ValueError('没有配置数据。')
    if any(len(r.cells)!=len(raw.trims) for r in raw.rows): raise ValueError('原始配置列数与版型数不一致。')
    if raw.lossy: raise ValueError('此旧数据丢失了标配和选配子项，请重新抓取完整表。')
    return raw
