"""Configuration ladder with explicit user-defined baselines and lossless evidence."""
from __future__ import annotations
import re
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from .models import Cell, RawTable
from .airbags import SOURCE_ROWS as AIRBAG_ROWS, from_raw as airbag_count

EMPTY = {'', '-', '—', '无', '不支持', '✕'}
RANGE_ROWS = ('CLTC纯电续航里程(km)', 'WLTC纯电续航里程(km)', 'NEDC纯电续航里程(km)')

# 阶梯默认不展示配置只维护此处：每行填写汽车之家原始配置行名，保留引号和逗号。
# 清单内默认不展示，界面可取消勾选并保存以恢复展示；同名条目重复添加按一项处理。
# 修改后重启程序，再重新查看或导出阶梯即可，无需先升级清单；不影响赋值计算。
DEFAULT_EXCLUDED_ROWS = (
    '电池容量(kWh)',
    '电池快充时间(小时)',
    '电池慢充时间(小时)',
    '电池快充电量范围(%)',
    '百公里耗电量(kWh/100km)',
    '整备质量(kg)',
    '最大满载质量(kg)',
    '长*宽*高(mm)',
    '长度(mm)',
    '宽度(mm)',
    '高度(mm)',
    '轴距(mm)',
    '前轮距(mm)',
    '后轮距(mm)',
    '最大功率(kW)',
    '最大扭矩(N·m)',
    '缸径(mm)',
    '行程(mm)',
    '电动机(kW)',
    '系统综合功率(kW)',
    '最大功率转速(rpm)',
    '最大扭矩转速(rpm)',
    '电动机(Ps)',
    '电动机总功率(kW)',
    '电动机总马力(Ps)',
    '电动机总扭矩(N·m)',
    '前电动机最大功率(kW)',
    '前电动机最大扭矩(N·m)',
    '后电动机最大功率(kW)',
    '后电动机最大扭矩(N·m)',
    '变速箱',
    '简称',
    '挡位个数',
    '变速箱类型',
    '整车质保',
    '电池组质保',
    '三电首任车主质保政策',
    '前制动器类型',
    '后制动器类型',
    '驻车制动类型',
    '备胎规格',
    '外观颜色',
    '内饰颜色',
    '快充功能',
    '快充功率(kW)',
    '厂商',
    '级别',
    '能源类型',
    '环保标准',
    '上市时间',
    'WLTC纯电续航里程(km)',
    '电池慢充电量范围(%)',
    '车身结构',
    '发动机',
    '官方0-100km/h加速(s)',
    '官方0-50km/h加速(s)',
    '最高车速(km/h)',
    'WLTC综合油耗(L/100km)',
    '最低荷电状态油耗(L/100km)WLTC',
    '最低荷电状态油耗(L/100km)NEDC',
    '电能当量燃料消耗量(L/100km)',
    '油电综合燃料消耗量(L/100km)',
    '接近角(°)',
    '离去角(°)',
    '最小转弯半径(m)',
    '扬声器品牌名称',
    '主动式环境氛围灯',
    '触摸式阅读灯',
    '多媒体/充电接口',
    '发动机型号',
    '排量(mL)',
    '排量(L)',
    '进气形式',
    '发动机布局',
    '气缸排列形式',
    '气缸数(个)',
    '每缸气门数(个)',
    '压缩比',
    '配气机构',
    '最大马力(Ps)',
    '最大净功率(kW)',
    '燃油标号',
    '供油方式',
    '缸盖材料',
    '缸体材料',
    '前电动机品牌',
    '后电动机品牌',
    '前电动机型号',
    '后电动机型号',
    '电机类型',
    '驱动电机数',
    '电机布局',
    '电池类型',
    '电芯品牌',
    '电池特有技术',
    '电池冷却方式',
    '电池快充时间(分钟)',
    '慢充接口位置',
    '快充接口位置',
    '对外交流放电功率(kW)',
    '驱动方式',
    '前悬架类型',
    '后悬架类型',
    '助力类型',
    '车体结构',
    '驾驶模式切换',
    '能量回收系统',
    '自动驻车',
    '上坡辅助',
    '前/后驻车雷达',
    '芯片总算力',
    '前方感知摄像头',
    '摄像头数量',
    '前方感知摄像头像素',
    '车内摄像头数量',
    '超声波雷达数量',
    '毫米波雷达数量',
    '倒车车侧预警系统',
    '卫星导航系统',
    '导航路况信息显示',
    '地图品牌',
    '并线辅助',
    '车道保持辅助系统',
    '车道居中保持',
    '道路交通标识识别',
    '防侧翻系统',
    '辅助泊车入位',
    '遥控泊车',
    '辅助变道',
    '辅助匝道自动驶出(入)',
    '方向盘离手检测',
    '发动机电子防盗',
    '车内中控锁',
    '钥匙类型',
    '无钥匙启动系统',
    '无钥匙进入功能',
    '远程启动功能',
    '电池预加热',
    '远光灯光源',
    'LED日间行车灯',
    '自适应远近光',
    '自动头灯',
    '车前雾灯',
    '大灯高度可调',
    '大灯延时关闭',
    '前/后电动车窗',
    '车窗一键升降功能',
    '车窗防夹手功能',
    '后排侧隐私玻璃',
    '中控屏幕类型',
    '蓝牙/车载电话',
    '语音识别控制系统',
    '语音助手唤醒词',
    '语音分区域唤醒识别',
    '语音连续识别',
    '可见即可说',
    '应用商店',
    '车载智能系统',
    '车机系统内存(GB)',
    '车机系统存储(GB)',
    '车联网',
    'OTA升级',
    'Wi-Fi热点',
    '手机APP远程功能',
    '换挡形式',
    '多功能方向盘',
    '行车电脑显示屏幕',
    'HUD抬头尺寸',
    'ETC装置',
    '运动风格座椅',
    '副驾驶位后排可调节按钮',
    '第二排座椅调节',
    '后排座椅放倒形式',
    '前/后中央扶手',
    '后排杯架',
    'ABS防抱死',
    '制动力分配(EBD/CBC等)',
    '刹车辅助(EBA/BAS/BA等)',
    '牵引力控制(ASR/TCS/TRC等)',
    '车身稳定控制(ESC/ESP/DSC等)',
    '胎压监测功能',
    '安全带未系提醒',
    'ISOFIX儿童座椅接口',
    '车道偏离预警系统',
    '主动刹车/主动安全系统',
    '疲劳驾驶提示',
    'DOW开门预警',
    '前方碰撞预警',
    '后方碰撞预警',
    '哨兵模式/千里眼',
    '低速行车警告',
    '内置行车记录仪',
    '道路救援呼叫',
    '厂商指导价(元)',
    '经销商报价',
    '车门开启方式',
    '车门数(个)',
    '座位数(个)',
    '油箱容积(L)',
    '前备厢容积(L)',
    '后备厢容积(L)',
    '风阻系数(Cd)',
    '高精定位',
    '记忆泊车',
    '循迹倒车',
    '信号灯识别',
    '隐藏电动门把手',
    '主动降噪',
    'USB/Type-C最大充电功率',
    '对外直流放电功率(kW)',
    '行李厢12V电源接口',
    '陡坡缓降',
    '起步提醒',
    '语音免唤醒词',
    '面部识别',
    '激光雷达线数',
    '系统综合马力(Ps)',
    '发动机启停技术',
    '发动机特有技术',
    '三电系统质保',
    '备胎放置方式',
    'NEDC综合油耗(L/100km)',
    'NEDC综合续航(km)',
    '四驱形式',
    '中央差速器结构',
    '灯光特色功能',
    '满载最小离地间隙(mm)',
    '爆胎稳行系统',
    '环境感知摄像头像素',
    '环视摄像头像素',
    '中控屏幕分辨率'
)


def display_raw(raw, excluded_rows=None):
    """A filtered view, not a mutation of the original capture or calculation data."""
    excluded = set(DEFAULT_EXCLUDED_ROWS if excluded_rows is None else excluded_rows)
    return replace(raw, rows=[row for row in raw.rows if row.name not in excluded])


def parts(cell, optional=False):
    if cell is None: return []
    result=[]
    marker = '○' if optional else '●'
    for c in (cell, *cell.subs):
        # Subs in historical HTML may contain the head again; deduplicate.
        text=c.text.strip()
        if c.dot == marker or (not optional and not c.dot and text not in EMPTY and '○' not in text):
            if text in EMPTY and c.dot not in {'●', '○'}: continue
            value=text or '有'
            if value not in result: result.append(value)
    return result


def clean(s):
    return s.replace('英寸','寸').replace('●','').replace('（','(').replace('）',')').strip()


def _detail(value):
    """Presence alone provides no type, size, location or other attribute."""
    value = clean(value)
    return '' if value in {'有', '支持', '是', '标配'} else value


_VALUE_SUFFIXES = {
    '电芯品牌': '电芯',
    '中控屏幕尺寸': '中控',
    '近光灯光源': '大灯',
    '4G/5G网络': '车联网',
    '座椅材质': '座椅',
    '方向盘材质': '方向盘',
    '内后视镜功能': '内后视镜',
    '前/后电动车窗': '电动车窗',
    '车窗一键升降功能': '电动车窗一键升降',
    '车内化妆镜': '化妆镜照明灯',
    '辅助驾驶芯片': '辅助驾驶芯片',
    '芯片总算力': '算力',
    '无钥匙进入功能': '无钥匙进入',
    '零重力座椅': '零重力座椅',
    '外观套件': '外观套件',
}


def _format_value(name, value):
    """Format a source value without adding details to presence-only cells."""
    value = _detail(value)
    if not value:
        return {'哨兵模式/千里眼': '哨兵模式', '车窗防夹手功能': '防夹手'}.get(name, name)
    if name in _VALUE_SUFFIXES:
        return value + _VALUE_SUFFIXES[name]
    if name == '电池类型':
        return value if value.endswith('电池') else value + '电池'
    if name == '扬声器数量':
        return re.sub(r'个|喇叭', '', value) + '扬声器'
    if name == '车外扬声器数量':
        return re.sub(r'个|喇叭', '', value) + '个车外扬声器'
    if name == '感应雨刷功能':
        return value.replace('式', '') + '雨刷'
    if name == '哨兵模式/千里眼':
        return '哨兵模式'
    if name == 'USB/Type-C接口数量':
        return 'USB/Type-C接口' + value
    if name == '多功能方向盘':
        return '多功能方向盘'
    if name == '车窗防夹手功能':
        return '防夹手'
    if name == '手机互联/映射':
        return value.replace('支持', '')
    if name in {'空调温度控制方式', '方向盘位置调节', '天窗类型', '可变悬架功能', '辅助驾驶路段'}:
        return value
    return name + value


def mirror_description(values):
    """One concise label; keep automatic folding distinct for comparison."""
    aliases = (
        ('电调', r'电动调节|电调'),
        ('锁车自动折叠', r'锁车自动折叠'),
        ('折叠', r'电动折叠|自动折叠|折叠'),
        ('加热', r'加热'),
        ('记忆', r'记忆'),
        ('倒车下翻', r'倒车自动下翻|倒车下翻'),
    )
    mapped=[]
    for value in values:
        text = re.sub(r'(?:外)?后视镜(?:功能[：:]?)?', '', clean(value))
        for label, pattern in aliases:
            if re.search(pattern, text):
                mapped.append(label)
                text = re.sub(pattern, '+', text)
        text = re.sub(r'\(\s*\)', '', text)
        mapped.extend(token for token in re.split(r'[+/、\s]+', text) if _detail(token))
    comparison = sorted(set(mapped)) if mapped else ['外后视镜功能'] if values else []
    displayed = ['折叠' if token == '锁车自动折叠' else token for token in mapped]
    known = [label for label in ('电调', '折叠', '加热', '记忆', '倒车下翻') if label in displayed]
    extra = list(dict.fromkeys(token for token in displayed if token not in known))
    summary = '外后视镜' + '+'.join(known + extra) if mapped else '外后视镜功能'
    return summary, comparison


def features(raw, excluded_rows=None):
    """Each feature is scalar or a set of independently inheritable subfeatures."""
    out=[]
    consumed=set()
    captured_electric = raw.row('主/副驾驶座电动调节') is not None
    raw = display_raw(raw, excluded_rows)
    from .seat_adjust import _SUPPORTS, support_from_raw, support_source_rows
    support_rows = {row.name for feature in _SUPPORTS for row in support_source_rows(raw, feature)}
    consumed.update(support_rows - {'主座椅调节方式', '副座椅调节方式', '前排座椅功能'})
    # Preserve RawTable.row's first-match semantics for duplicate source rows.
    rows_by_name = {}
    for row in raw.rows:
        rows_by_name.setdefault(row.name, row)
    values_by_name = {
        name: [parts(cell) for cell in row.cells]
        for name, row in rows_by_name.items()
    }
    range_row = next((rows_by_name[name] for name in RANGE_ROWS if name in rows_by_name), None)
    name_counts = Counter(row.name for row in raw.rows)
    occurrences = Counter()
    count=len(raw.trims)
    def get(name,i):
        return values_by_name[name][i] if name in values_by_name else []
    def add(key,values,scalar=False):
        out.append({'key':key,'values':[[value if _detail(value) else key for value in vs] for vs in values],'scalar':scalar})
    for row in raw.rows:
        name=row.name
        occurrence = occurrences[(row.group, name)]
        occurrences[(row.group, name)] += 1
        values = values_by_name[name] if row is rows_by_name[name] else [parts(c) for c in row.cells]
        if name in consumed or name in RANGE_ROWS:
            first = rows_by_name[name]
            if name_counts[name] > 1 and row is not first and row.cells != first.cells:
                add((row.group, name, occurrence), [[name+_detail(value) for value in vs] for vs in values])
                continue
            if name in consumed: continue
        if name in RANGE_ROWS:
            if row is not range_row: continue
            add(name,[[name[:4]+'纯电续航'+(_detail(v)+'km' if _detail(v) else '') for v in vs] for vs in values],True)
        elif name in {'前轮胎规格','后轮胎规格','轮圈材质'}:
            consumed.update({'前轮胎规格','后轮胎规格','轮圈材质'})
            v=[]
            for i in range(count):
                tire=' '.join(get('前轮胎规格',i)); rear=' '.join(get('后轮胎规格',i)); material=_detail(' '.join(get('轮圈材质',i)))
                f=re.search(r'R\s*(\d+)',tire,re.I); b=re.search(r'R\s*(\d+)',rear,re.I)
                size=('R'+f[1]) if f else ''
                if f and b and f[1]!=b[1]: size='前R'+f[1]+'后R'+b[1]
                v.append([size+material+'轮毂'] if tire or rear or get('轮圈材质',i) else [])
            add('轮毂',v,True)
        elif name in {'对外放电','对外交流放电功率(kW)','对外放电功率(kW)'}:
            consumed.update({'对外放电','对外交流放电功率(kW)','对外放电功率(kW)'})
            v=[]
            for i in range(count):
                has = bool(get('对外放电', i))
                source = next((n for n in ('对外交流放电功率(kW)', '对外放电功率(kW)') if get(n, i)), '')
                power = _detail(' '.join(get(source, i))) if source else ''
                v.append([f'对外放电{clean(power)}kW' if power else '对外放电'] if has else [source+power] if source else [])
            add('对外放电', v, True)
        elif name in {'激光雷达数量','激光雷达品牌'}:
            consumed.update({'激光雷达数量','激光雷达品牌'})
            v=[]
            for i in range(count):
                number=_detail(' '.join(get('激光雷达数量', i)))
                brand=_detail(' '.join(get('激光雷达品牌', i)))
                brand=clean(brand).replace('HESAI','').replace('禾赛科技','禾赛').strip()
                if number:
                    count_text=re.sub(r'(个|颗|台)$', '', clean(number))
                    values=[f'{count_text}颗{brand}激光雷达' if brand else f'{count_text}颗激光雷达']
                elif brand:
                    values=[brand+'激光雷达']
                else:
                    values=['激光雷达'] if get('激光雷达数量', i) or get('激光雷达品牌', i) else []
                v.append(values)
            add('激光雷达', v, True)
        elif name in AIRBAG_ROWS:
            consumed.update(AIRBAG_ROWS)
            v=[]
            for i in range(count):
                total, _ = airbag_count(raw, i)
                v.append([f'{total}气囊'] if total else [n for n in AIRBAG_ROWS if get(n, i)])
            add('气囊',v,True)
        elif name in {'驾驶辅助影像','透明底盘/540度影像'}:
            consumed.update({'驾驶辅助影像','透明底盘/540度影像'})
            add('影像',[['540影像'] if get('透明底盘/540度影像',i) else [clean(x) for x in get('驾驶辅助影像',i)] for i in range(count)],True)
        elif name in {'主座椅调节方式','副座椅调节方式','主/副驾驶座电动调节'}:
            consumed.update({'主座椅调节方式','副座椅调节方式','主/副驾驶座电动调节'})
            from .seat_adjust import parse, raw_details
            details = [raw_details(raw, i, include_terms=False) for i in range(count)]
            electric_hidden = captured_electric and '主/副驾驶座电动调节' not in rows_by_name
            for j, (pos, source) in enumerate([('主驾', '主座椅调节方式'), ('副驾', '副座椅调节方式')]):
                totals = []
                for i in range(count):
                    text = _detail(' '.join(get(source, i)))
                    counts, modes, _ = details[i]
                    directions = counts[j]
                    mode = modes[j]
                    if electric_hidden:
                        mode = parse(text if text.startswith(('主', '副')) else pos+text.removeprefix('座椅'))['seats'][j]['mode']
                    if directions:
                        value = f'{pos}{directions}向'+(mode or '调节')
                    elif get(source, i) or mode == '电调':
                        value = pos+(mode or '座椅调节')
                    else:
                        value = ''
                    totals.append([value] if value else [])
                add(pos+'座椅调节', totals, True)
        elif name in {'高压平台','800V高压平台','高压平台（V）','高压平台(V)','高压快充'}:
            sources = ['高压平台','800V高压平台','高压平台（V）','高压平台(V)','高压快充']
            consumed.update(sources)
            v=[]
            presence = {'有','支持','是','标配','高压平台','800V高压平台','高压快充'}
            for i in range(count):
                values = [(source, clean(value)) for source in sources for value in get(source, i) if clean(value) not in EMPTY]
                voltage = next((match[1]+'V' for _, value in values
                                if (match := re.fullmatch(r'(\d+(?:\.\d+)?)\s*[Vv]?', value)) and float(match[1]) > 0), '')
                details = [source+value for source, value in values if value not in presence]
                platform_option = any(parts(row.cells[i], optional=True)
                                      for source in sources[:-1] if (row := rows_by_name.get(source)))
                if voltage:
                    v.append([voltage])
                elif details:
                    v.append(list(dict.fromkeys(details)))
                else:
                    v.append(['800V'] if values and not platform_option else [])
            add('高压平台', v, True)
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
                    if not values and any(get(source, i) for source in ('巡航系统','辅助驾驶系统','辅助驾驶等级','辅助驾驶路段')):
                        values=['辅助驾驶']
                v.append(values)
            add('辅助驾驶', v, True)
            for source in ('辅助驾驶系统', '辅助驾驶等级', '辅助驾驶路段'):
                details=[]
                for i in range(count):
                    values=[]
                    for value in get(source, i):
                        text=_detail(value)
                        if not text: continue
                        if source == '辅助驾驶系统' and text in {'L1', 'L2', '基础L2辅助驾驶', '辅助驾驶', '辅助驾驶系统'}: continue
                        if source == '辅助驾驶等级' and re.fullmatch(r'L2(?:级|辅助驾驶)?', text): continue
                        if source == '辅助驾驶路段' and re.fullmatch(r'(?:(?:城市|高速)(?:路段|道路|公路)?[+/、\s]*)+', text): continue
                        values.append(source+text)
                    details.append(values)
                add(source, details, True)
        elif name in {'电动后备厢','电动后备厢位置记忆','电动后备箱'}:
            consumed.update({'电动后备厢','电动后备厢位置记忆','电动后备箱'})
            v=[]
            for i in range(count):
                trunk=bool(get('电动后备厢', i) or get('电动后备箱', i))
                memory=bool(get('电动后备厢位置记忆', i))
                values=[]
                if trunk: values.append('电动后备厢')
                if memory: values.append('位置记忆' if trunk else '电动后备厢位置记忆')
                v.append(values)
            add('电动后备厢', v)
        elif name in {'手机无线充电功能','手机无线充电功率'}:
            from .wireless import source_label
            consumed.update({'手机无线充电功能','手机无线充电功率'})
            v=[]
            for i in range(count):
                scope=' '.join(get('手机无线充电功能', i))
                power=' '.join(get('手机无线充电功率', i))
                if not scope and (not power or '手机无线充电功能' in rows_by_name):
                    v.append([])
                else:
                    v.append([source_label(_detail(scope) or '●', _detail(power))])
            add('手机无线充电', v, True)
        elif name in {'车内环境氛围灯','主动式环境氛围灯'}:
            from .mapper import n_ambient
            consumed.update({'车内环境氛围灯','主动式环境氛围灯'})
            v=[]
            for i in range(count):
                color=' '.join(get('车内环境氛围灯', i))
                active=bool(get('主动式环境氛围灯', i))
                values=[]
                if color:
                    label = n_ambient(raw, i, {})
                    values.append((label if label in {'单色', '多色'} else '')+'氛围灯')
                if active: values.append('主动式环境氛围灯')
                v.append(values)
            add('氛围灯', v)
        elif name == '外后视镜功能':
            source_values = values
            values=[]
            comparison_values=[]
            for vs in source_values:
                summary, comparison = mirror_description(vs)
                comparison_values.append(comparison)
                values.append([summary] if vs else [])
            add(name, values, True)
            out[-1]['comparison_values'] = comparison_values
        elif name == '车内化妆镜':
            source_values = values
            values=[]
            for vs in source_values:
                text=' '.join(vs)
                label = '化妆镜照明灯' if '照明' in text else '化妆镜'
                if '主驾' in text and '副驾' in text:
                    values.append(['主副驾'+label])
                elif '主驾' in text:
                    values.append(['主驾'+label])
                elif '副驾' in text:
                    values.append(['副驾'+label])
                else:
                    values.append([label] if text else [])
            add(name, values)
        elif name == '方向盘位置调节':
            values = [['/'.join(clean(value).replace('+', '/') for value in vs)] if vs else [] for vs in values]
            add(name, values, True)
        elif name in {'方向盘材质','多功能方向盘'}:
            consumed.update({'方向盘材质','多功能方向盘'})
            values=[]
            for i in range(count):
                material=' '.join(get('方向盘材质', i))
                multifunction=bool(get('多功能方向盘', i))
                has_material=bool(material)
                material=_detail(material)
                if material:
                    values.append([material + ('多功能方向盘' if multifunction else '方向盘')])
                elif multifunction:
                    values.append(['多功能方向盘'])
                else:
                    values.append(['方向盘材质'] if has_material else [])
            add('方向盘', values, True)
        elif name in {'电动座椅记忆','座椅记忆功能','电动座椅记忆功能'}:
            sources = ['电动座椅记忆','座椅记忆功能','电动座椅记忆功能']
            consumed.update(sources)
            from .mapper import n_seat_memory
            memory=[]
            memory_source = next(source for source in sources if source in rows_by_name)
            for i in range(count):
                value = n_seat_memory(raw, i, {'source_rows':sources})
                seats = ['主驾座椅记忆','副驾座椅记忆'] if value == '前排座椅记忆' else [value] if value.startswith(('主驾','副驾')) else []
                if any('[待' not in text and re.search(r'后排(?![○✕×-])', text) for text in get(memory_source, i)):
                    seats.append('后排座椅记忆')
                memory.append(seats or (['电动座椅记忆'] if value.startswith('[待定]') else []))
            add('电动座椅记忆', memory)
        elif name in {'前排座椅功能','第二排座椅功能','后排座椅功能'}:
            v=[]
            for vs in values:
                feats=[]
                for item in vs:
                    if not _detail(item):
                        feats.append(name)
                        continue
                    scope=['主驾'] if re.search('仅驾驶位|仅主驾|主驾驶',item) else ['副驾'] if '副驾驶' in item else ['主驾','副驾'] if name.startswith('前') else ['后排']
                    for token in re.split(r'[+/、]', item):
                        matched = [f for f in ['加热','通风','按摩','头枕扬声器','头枕音响'] if f in token.replace('头枕加热', '')]
                        feats.extend(p+'座椅'+f for f in matched for p in scope)
                        remainder=clean(token)
                        for feature in matched:
                            remainder=re.sub(r'(?<!头枕)加热', '', remainder) if feature == '加热' else remainder.replace(feature, '')
                        if name == '前排座椅功能':
                            for pattern in _SUPPORTS.values():
                                remainder = re.sub(r'(?:电动|手动)?(?:'+pattern+r')(?:调节)?(?:\(\d+向\))?', '', remainder)
                        remainder=re.sub(r'\((?:仅)?(?:驾驶位|主驾驶|副驾驶|主驾|副驾|主副驾|前排|后排)\)', '', remainder).strip()
                        if _detail(remainder):
                            feats.append(name+'：'+(clean(token) if remainder.startswith('(') else remainder))
                v.append(list(dict.fromkeys(feats)))
            add(name,v)
        elif name in {'全液晶仪表盘','液晶仪表尺寸'}:
            consumed.update({'全液晶仪表盘','液晶仪表尺寸'})
            v=[]
            for i in range(count):
                full = get('全液晶仪表盘', i)
                known = {'全液晶','全液晶仪表','全液晶仪表盘'}
                full_lcd = any(not _detail(value) or clean(value) in known for value in full)
                sizes = [_detail(value) for value in get('液晶仪表尺寸', i) if _detail(value)]
                descriptions = [('全液晶' if full_lcd else '') + size + ('寸' if re.fullmatch(r'\d+(?:\.\d+)?', size) else '') + '仪表' for size in sizes]
                if not descriptions:
                    descriptions = ['全液晶仪表'] if full_lcd else ['液晶仪表尺寸'] if get('液晶仪表尺寸', i) else []
                descriptions.extend('全液晶仪表盘'+_detail(value) for value in full if _detail(value) and clean(value) not in known)
                v.append(list(dict.fromkeys(descriptions)))
            add('仪表',v,True)
        else:
            scalar=name in {'中控屏幕尺寸','副驾驶位屏幕尺寸','4G/5G网络','方向盘材质','方向盘位置调节','座椅材质','扬声器数量','车外扬声器数量','车内环境氛围灯','天窗类型','近光灯光源','电芯品牌','手机无线充电功率'}
            if name=='远光灯光源' and '近光灯光源' in rows_by_name and all(get(name,i)==get('近光灯光源',i) for i in range(count)): continue
            parameter={'中控彩色屏幕':'中控屏幕尺寸', '车联网':'4G/5G网络', '行车电脑显示屏幕':'液晶仪表尺寸'}.get(name)
            if parameter:
                values=[[] if get(parameter,i) else vs for i,vs in enumerate(values)]
            # Row identity matters when different sections share a name. Older
            # captures have no group; a per-name occurrence keeps both rows
            # without depending on the position of unrelated source rows.
            key = (row.group, name, occurrence) if name_counts[name] > 1 else name
            add(key,[list(dict.fromkeys(_format_value(name, v) for v in vs)) for vs in values],scalar)
    supports = []
    for feature in _SUPPORTS:
        values = []
        for i in range(count):
            label = support_from_raw(raw, i, feature)
            values.append(['主驾'+feature, '副驾'+feature] if label == '前排'+feature else [] if label == '✕' else label.split('+'))
        if any(values):
            supports.append({'key': '座椅'+feature, 'values': values, 'scalar': False})
    position = next((i+1 for i in range(len(out)-1, -1, -1)
                     if out[i]['key'] in {'主驾座椅调节', '副驾座椅调节'}), len(out))
    out[position:position] = supports
    return out


def validate_plan(raw, plan):
    if not isinstance(plan, list) or not plan:
        raise ValueError('请至少选择一个版型。')
    seen = set()
    for row in plan:
        if not isinstance(row, dict):
            raise ValueError('导出版型无效或重复。')
        target, base = row.get('target'), row.get('base')
        if type(target) is not int or not 0 <= target < len(raw.trims) or target in seen:
            raise ValueError('导出版型无效或重复。')
        if 'base' not in row:
            raise ValueError('请为每个导出版型指定比较基准，基本配置选择空基准。')
        if base is not None and (type(base) is not int or base not in seen):
            raise ValueError('比较基准须选择已排在前面的版型，不能自比、循环或引用未导出版型。')
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


def _option_lines(raw, trim_index, excluded_rows=None):
    """Return one quoted line per optional row; options never enter standard deltas."""
    result = []
    for row in display_raw(raw, excluded_rows).rows:
        values = parts(row.cells[trim_index], optional=True)
        if not values:
            continue
        text = ' / '.join(value for value in map(_detail, values) if value)
        result.append(f'{row.name}：{text}' if text else row.name)
    return result


_BASE_GROUPS = [
    ('哨兵模式/千里眼', '内置行车记录仪'),
    ('无钥匙进入功能', '主动闭合式进气格栅'),
    ('前/后电动车窗', '车窗一键升降功能', '车窗防夹手功能'),
    ('方向盘', '方向盘材质', '方向盘位置调节', '多功能方向盘'),
    ('主驾座椅调节', '副驾座椅调节'),
    ('扬声器数量', '车外扬声器数量'),
    ('空调温度控制方式', '后座出风口'),
]
_BASE_GROUP_INDEX = {key: index for index, group in enumerate(_BASE_GROUPS) for key in group}
_SEAT_TOKENS = {
    position + '座椅' + function: (position, function)
    for position in ('主驾', '副驾', '后排')
    for function in ('通风', '加热', '按摩', '记忆')
}


def _change_items(fs, trim_index, base_index):
    """Create normalized line items before applying the visual grouping."""
    items = []
    for feature in fs:
        cur = feature['values'][trim_index]
        prev = feature['values'][base_index] if base_index is not None else []
        comparison = feature.get('comparison_values', feature['values'])
        if comparison[trim_index] == (comparison[base_index] if base_index is not None else []):
            continue
        if base_index is None:
            # The one-touch row already conveys the window coverage; keeping
            # the generic front/rear window row would duplicate the same fact.
            if feature['key'] == '前/后电动车窗' and any(f['key']=='车窗一键升降功能' and f['values'][trim_index] for f in fs):
                continue
            if cur:
                items.append((feature['key'], '+'.join(cur)))
            continue
        if feature['key'] in {'外后视镜功能', '高压平台'}:
            # This row is a single current-equipment summary, not a repeated baseline.
            items.append((feature['key'], '+'.join(cur) if cur else '无（' + '+'.join(prev) + '）'))
            continue
        if feature['scalar'] and cur and prev:
            left, right = ('（', '）') if feature['key'] in {'主驾座椅调节', '副驾座椅调节'} else ('(', ')')
            items.append((feature['key'], '+'.join(cur) + left + '+'.join(prev) + right))
        else:
            additions = [value for value in cur if value not in prev]
            removals = [value for value in prev if value not in cur]
            if removals:
                # Compact each side before comparing, so removed seat functions
                # cannot be mistaken for current equipment by the later join.
                current = '+'.join(_compact_items([(feature['key'], '+'.join(cur))], base_index)) if cur else '无'
                previous = '+'.join(_compact_items([(feature['key'], '+'.join(prev))], base_index))
                items.append((feature['key'], current + '（' + previous + '）'))
            elif additions:
                items.append((feature['key'], '+'.join(additions)))
    return items


_NUMERIC_DISPLAY_FEATURES = set(RANGE_ROWS) | {
    '电池能量(kWh)', '电池容量(kWh)', '电池容量(kW·h)', '气囊', '激光雷达',
    '中控屏幕尺寸', '副驾驶位屏幕尺寸', '中控屏幕分辨率', '副驾驶位屏幕分辨率',
    '扬声器数量', '车外扬声器数量', '对外放电', '手机无线充电', '4G/5G网络',
    'USB/Type-C接口数量', '车机系统内存(GB)', '车机系统存储(GB)', '芯片总算力',
    '高压平台', '辅助驾驶系统内存(GB)', '辅助驾驶系统存储(GB)',
    '摄像头数量', '车内摄像头数量', '前方感知摄像头像素', '环境感知摄像头像素', '环视摄像头像素',
    '超声波雷达数量', '毫米波雷达数量', '激光雷达线数',
}
_DISPLAY_LEVELS = {
    '影像': (('倒车影像',), ('360', '全景'), ('540',)),
    '辅助驾驶': (('定速巡航',), ('全速自适应巡航', 'L2'), ('高速NOA',), ('城市NOA',)),
    '近光灯光源': (('卤素',), ('氙气',), ('LED',)),
    '远光灯光源': (('卤素',), ('氙气',), ('LED',)),
    '方向盘位置调节': (('手动', '手调'), ('电动', '电调')),
    '方向盘': (('塑料',), ('仿皮', '皮质'), ('真皮',), ('翻毛皮',), ('NAPPA',)),
    '空调温度控制方式': (('手动',), ('自动',)),
    '氛围灯': (('单色',), ('多色',)),
    '座椅材质': (('织物',), ('仿皮', '皮质'), ('真皮',), ('翻毛皮',), ('NAPPA',)),
}


def _display_reduced(feature, trim_index, base_index):
    """Only order known specifications; model names and brands have no numeric rank."""
    comparison = feature.get('comparison_values', feature['values'])
    if set(comparison[trim_index]) < set(comparison[base_index]):
        return True
    name = feature['key'][1] if isinstance(feature['key'], tuple) else feature['key']
    current, previous = ('+'.join(feature['values'][i]) for i in (trim_index, base_index))
    levels = _DISPLAY_LEVELS.get(name)
    if levels:
        ranks = [max((rank for rank, tokens in enumerate(levels)
                      if any(token.casefold() in text.casefold() for token in tokens)), default=None)
                 for text in (current, previous)]
        if name == '方向盘':
            pairs = [(ranks[0], ranks[1])] if all(rank is not None for rank in ranks) else []
            pairs.append(tuple(int('多功能' in text) for text in (current, previous)))
            return all(a <= b for a, b in pairs) and any(a < b for a, b in pairs)
        return all(rank is not None for rank in ranks) and ranks[0] < ranks[1]
    if name in {'主驾座椅调节', '副驾座椅调节'}:
        from .seat_adjust import parse
        index = 0 if name.startswith('主') else 1
        seats = [parse(text)['seats'][index] for text in (current, previous)]
        pairs = [(seats[0]['count'], seats[1]['count'])]
        if all(seat['mode'] in {'手调', '电调'} for seat in seats):
            pairs.append(tuple(int(seat['mode'] == '电调') for seat in seats))
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    elif name == '轮毂':
        sizes = [re.findall(r'R\s*(\d+)', text) for text in (current, previous)]
        sizes = [values * 2 if len(values) == 1 else values for values in sizes]
        if not sizes[0] or len(sizes[0]) != len(sizes[1]):
            return False
        pairs = list(zip(map(int, sizes[0]), map(int, sizes[1])))
        if all('铝' in text or '钢' in text for text in (current, previous)):
            pairs.append(tuple(int('铝' in text) for text in (current, previous)))
    elif name == '仪表':
        sizes = [re.search(r'(\d+(?:\.\d+)?)寸', text) for text in (current, previous)]
        if not all(sizes):
            return False
        pairs = [(Decimal(sizes[0][1]), Decimal(sizes[1][1])),
                 tuple(int('全液晶' in text) for text in (current, previous))]
    elif name == '车内化妆镜':
        if not all('主' in text or '副' in text for text in (current, previous)):
            return False
        pairs = [tuple(int(token in text) for text in (current, previous)) for token in ('主', '副', '照明')]
    elif name == '天窗类型':
        return ('不可开启全景' in current and '可开启全景' in previous and '不可开启' not in previous)
    elif name in _NUMERIC_DISPLAY_FEATURES:
        number = r'\d+(?:\.\d+)?'
        if re.sub(number, '#', current) != re.sub(number, '#', previous):
            return False
        pairs = list(zip(map(Decimal, re.findall(number, current)), map(Decimal, re.findall(number, previous))))
    else:
        return False
    return bool(pairs) and all(a <= b for a, b in pairs) and any(a < b for a, b in pairs)


def _display_change_groups(fs, changes, trim_index, base_index):
    present, removed = [], []
    by_key = {feature['key']: feature for feature in fs}
    for key, value in changes:
        if base_index is None:
            present.append((key, value))
            continue
        feature = by_key[key]
        name = key[1] if isinstance(key, tuple) else key
        current, previous = (feature['values'][i] for i in (trim_index, base_index))
        reduced = bool(current) and _display_reduced(feature, trim_index, base_index)
        if not current:
            removed.append((key, '+'.join(previous)))
        elif name == '外后视镜功能':
            comparison = feature['comparison_values']
            added = [v for v in comparison[trim_index] if v not in comparison[base_index]]
            lost = [v for v in comparison[base_index] if v not in comparison[trim_index]]
            if added:
                present.append((key, '外后视镜'+'+'.join(added)))
            if lost:
                removed.append((key, '外后视镜'+'+'.join(lost)))
        elif not feature['scalar'] and (name in {'手机互联/映射', '前排座椅功能', '第二排座椅功能', '后排座椅功能', '电动后备厢', '电动座椅记忆', '座椅腿托', '座椅腰托'}
                                         or (not reduced and (len(current) > 1 or len(previous) > 1))):
            added = [v for v in current if v not in previous]
            lost = [v for v in previous if v not in current]
            if added:
                present.append((key, '+'.join(added)))
            if lost:
                removed.append((key, '+'.join(lost)))
        elif reduced:
            removed.append((key, value))
        else:
            present.append((key, value))
    return present, removed


def _compact_seats(lines):
    result = []
    functions_order = ('通风', '加热', '按摩', '记忆')
    found = {position: set() for position in ('主驾', '副驾', '后排')}
    insertion = None
    for line in lines:
        if '(' in line or '（' in line:
            result.append(line)
            continue
        rest = []
        for token in line.split('+'):
            seat = _SEAT_TOKENS.get(token)
            if seat:
                position, function = seat
                found[position].add(function)
                if insertion is None:
                    insertion = len(result)
            else:
                rest.append(token)
        if rest:
            result.append('+'.join(rest))
    common = found['主驾'] & found['副驾']
    labels = []
    for position, funcs in [('前排', common), ('主驾', found['主驾'] - common),
                            ('副驾', found['副驾'] - common), ('后排', found['后排'])]:
        if funcs:
            labels.append(position + ''.join(function for function in functions_order if function in funcs))
    if labels:
        result.insert(insertion if insertion is not None else len(result), '+'.join(labels))
    return result


def _compact_items(items, base_index):
    if base_index is None:
        grouped = []
        positions = {}
        for key, value in items:
            group_index = _BASE_GROUP_INDEX.get(key)
            if group_index is None:
                grouped.append(value)
                continue
            if group_index not in positions:
                positions[group_index] = len(grouped)
                grouped.append(value)
            else:
                grouped[positions[group_index]] += '+' + value
        return _compact_seats(grouped)
    # Merge repeated rows and the two seat summaries. Comparison parentheses
    # retain the chosen baseline; unchanged rows stay omitted.
    grouped = []
    positions = {}
    seat_changes = []
    for key, value in items:
        if key in {'主驾座椅调节', '副驾座椅调节'}:
            seat_changes.append(value)
            key = ('主驾座椅调节', '副驾座椅调节')
        if key in positions:
            grouped[positions[key]] += '+' + value
        else:
            positions[key] = len(grouped)
            grouped.append(value)
    if seat_changes:
        from .seat_adjust import difference_label
        comparisons = [None if value.startswith('无（') else re.fullmatch(r'([^（）]+)（([^（）]+)）', value)
                       for value in seat_changes]
        paired = [match for match in comparisons if match]
        if paired:
            difference = difference_label('+'.join(match[1] for match in paired),
                                          '+'.join(match[2] for match in paired))
            if difference is not None:
                labels, emitted = [], False
                for value, match in zip(seat_changes, comparisons):
                    if not match:
                        labels.append(value)
                    elif not emitted:
                        labels.append(difference)
                        emitted = True
                grouped[positions[('主驾座椅调节', '副驾座椅调节')]] = '+'.join(label for label in labels if label)
    return _compact_seats(grouped)


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
    range_row = raw.row(*RANGE_ROWS)
    ranges = []
    if range_row:
        for entry in plan:
            value = parts(range_row.cells[entry['target']])
            if value and value[0] not in ranges:
                ranges.append(value[0])
    if ranges:
        bits.append(range_row.name[:4] + '续航' + '/'.join(clean(value) for value in ranges) + 'km')
    return '，'.join(value for value in bits if value)


def render(raw, plan, excluded_rows=None):
    """Render the user-facing ladder in the accepted 5C paragraph format.

    The raw table remains lossless upstream.  This view is deliberately compact:
    the base trim contains the selected standard equipment, each following block
    contains only its relative delta, and optional equipment is listed once at the
    end instead of being repeated after every trim.
    """
    validate_plan(raw,plan)
    fs=features(raw, excluded_rows)
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
    range_row = raw.row(*RANGE_ROWS)
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
        # A plus sign joins related items within a line, not Markdown prefixes.
        lines.extend(esc(c)+'  ' for c in changes)
        if not changes: lines.append('配置相同，仅价格/续航差异。')
        lines.append('')
    option_blocks=[]
    for entry in plan:
        i=entry['target']; opts=_option_lines(raw, i, excluded_rows)
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
