"""valuer — 赋值引擎：金额来自 pjy 规定的赋值表（ValuationTable），程序不脑补

公式（拉平口径已由 pjy 手工草稿验证，最终以 pjy 确认为准）：
- 单项金额 = f(赋值表 pricing 类型, 自方值, 对方值)
- 配置优势 = Σ(多项金额) − Σ(少项金额)
- 拉平指导价优势 = 配置优势 + (竞品指导价 − 自产品指导价) × 10000
- 综合竞争力 = 可插拔公式（pjy 未提供前输出 None → 渲染层显示 [待公式]）

任何一项查不到金额 → 该组 config_adv=None 并列出 missing（渲染层显示 待赋值明细表/[待赋值]）。
"""
from __future__ import annotations
import copy
import json
import math
import re

# 综合竞争力公式注册表：pjy 给公式后在此登记
OVERALL_FORMULAS = {}

# Built-in version of the user's "竞争力对比配置清单参考(1).xlsx".
# A slash in the workbook means the item is deliberately zero-valued.
DEFAULT_FLAT = {
    2: 0, 3: 2000, 8: 0, 11: 2000, 12: 1000, 13: 800,
    14: 300, 15: 1000, 16: 500, 19: 0, 24: 0, 27: 200,
    28: 100, 40: 2000, 41: 200, 43: 1000, 44: 100,
}
ZERO_ITEMS = {2, 9, 20, 25}
EXCLUDED_ITEMS = {2, 8, 19, 24}  # Workbook '/' entries, not zero-price base tiers.

# 动态规则的唯一默认值。界面可以把 params 覆盖后持久化，
# 计算与规则说明都从同一份 params 取值。
DEFAULT_DYNAMIC_PARAMS = {
    1: {'threshold_km': 50, 'per_km': 60},
    3: {'platform_800v': 2000},
    4: {'base_inch': 16, 'per_inch': 700, 'alloy_bonus': 500},
    5: {'per_airbag': 350},
    6: {'soft_hard': 1000, 'height_or_air': 8000},
    7: {'reverse_or_360': 1000, 'image_540': 1500},
    9: {'cruise': 500, 'l2': 1000, 'highway_noa': 5000, 'city_noa': 8000},
    12: {'manual': 500, 'electric': 1000},
    17: {'led': 1000},
    18: {'electric': 1000, 'fixed_panorama': 2000, 'opening_panorama': 2500},
    20: {'per_function': 100},
    21: {'threshold_inch': 3, 'price': 500},
    22: {'small_limit': 12.6, 'large_limit': 15.6, 'small': 1000, 'medium': 1500, 'large': 2000},
    23: {'4g': 2000, '5g': 3000},
    25: {'plastic': 0, 'faux': 250, 'leather': 500, 'suede': 600, 'nappa': 700},
    26: {'electric': 800},
    29: {'per_inch': 100, 'lcd_bonus': 200},
    30: {'hud': 1000, 'ar_hud': 2000, 'p_hud': 3000},
    31: {'streaming': 1000},
    32: {'base_count': 3, 'per_port': 50},
    33: {'per_charger': 350},
    34: {'fabric': 0, 'faux': 1500, 'leather': 2500, 'suede': 3000, 'nappa': 3500},
    35: {'per_direction': 50, 'electric_bonus': 400},
    36: {'ventilation': 400, 'heating': 250, 'massage': 600, 'headrest': 100},
    37: {'per_speaker': 100},
    38: {'per_speaker': 100},
    39: {'single': 200, 'multi': 600},
    45: {'per_seat': 100},
}

EDITOR_FIELDS = {
    1: [('threshold_km', '不计价的续航差', 'km'), ('per_km', '超过阈值后每km', '元')],
    3: [('platform_800v', '800V', '元')],
    4: [('base_inch', '基准轮径', '寸'), ('per_inch', '每增加1寸', '元'), ('alloy_bonus', '铝轮毂加价', '元')],
    5: [('per_airbag', '每个气囊', '元')],
    6: [('soft_hard', '软硬调节', '元'), ('height_or_air', '高低/空气悬架', '元')],
    7: [('reverse_or_360', '倒车/360影像', '元'), ('image_540', '540影像', '元')],
    9: [('cruise', '定速巡航', '元'), ('l2', '基础L2', '元'), ('highway_noa', '高速NOA', '元'), ('city_noa', '城市NOA', '元')],
    12: [('manual', '手动前备箱', '元'), ('electric', '电动前备箱', '元')],
    17: [('led', 'LED大灯', '元')],
    18: [('electric', '普通电动天窗', '元'), ('fixed_panorama', '不可开启全景', '元'), ('opening_panorama', '可开启全景', '元')],
    20: [('per_function', '每项后视镜功能', '元')],
    21: [('threshold_inch', '尺寸差阈值', '寸'), ('price', '达到阈值', '元')],
    22: [('small_limit', '小屏上限', '寸'), ('large_limit', '中屏上限', '寸'), ('small', '小屏', '元'), ('medium', '中屏', '元'), ('large', '大屏', '元')],
    23: [('4g', '4G车联网', '元'), ('5g', '5G车联网', '元')],
    25: [('plastic', '塑料', '元'), ('faux', '仿皮', '元'), ('leather', '真皮', '元'), ('suede', '翻毛皮', '元'), ('nappa', 'NAPPA', '元')],
    26: [('electric', '电动调节', '元')],
    29: [('per_inch', '每寸仪表', '元'), ('lcd_bonus', '全液晶加价', '元')],
    30: [('hud', 'HUD', '元'), ('ar_hud', 'AR-HUD', '元'), ('p_hud', 'P-HUD', '元')],
    31: [('streaming', '流媒体后视镜', '元')],
    32: [('base_count', '基础接口数', '个'), ('per_port', '每个接口差', '元')],
    33: [('per_charger', '每个无线充电', '元')],
    34: [('fabric', '织物', '元'), ('faux', '仿皮', '元'), ('leather', '真皮', '元'), ('suede', '翻毛皮', '元'), ('nappa', 'NAPPA', '元')],
    35: [('per_direction', '每个调节方向', '元'), ('electric_bonus', '每个电调座椅加价', '元')],
    36: [('ventilation', '通风/座', '元'), ('heating', '加热/座', '元'), ('massage', '按摩/座', '元'), ('headrest', '头枕音响/座', '元')],
    37: [('per_speaker', '每个车内扬声器', '元')],
    38: [('per_speaker', '每个车外扬声器', '元')],
    39: [('single', '单色氛围灯', '元'), ('multi', '多色氛围灯', '元')],
    45: [('per_seat', '每座座椅记忆', '元')],
}


def editor_schema():
    return {str(no): [{'key': key, 'label': label, 'unit': unit} for key, label, unit in fields]
            for no, fields in EDITOR_FIELDS.items()}


def default_valuation(rules):
    """Return the built-in valuation table, without requiring an xlsx upload."""
    items = []
    for item in rules.items:
        no = item["no"]
        if item.get("merged_into"):
            continue
        rule = "dynamic" if no in {1, 3, 4, 5, 6, 7, 9, 12, 17, 18, 20, 21, 22, 23, 25, 26, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 45} else "flat"
        if no in EXCLUDED_ITEMS:
            rule = 'excluded'
        items.append({"no": no, "name": item.get("md_name") or item["name"],
                      "pricing": "manual", "val": 0 if no in ZERO_ITEMS else DEFAULT_FLAT.get(no),
                      "unit_val": None, "bands": [], "rule": rule,
                      "params": copy.deepcopy(DEFAULT_DYNAMIC_PARAMS.get(no, {})),
                      "note": "内置：竞争力对比配置清单参考(1).xlsx；/按0元处理" if no in ZERO_ITEMS else "内置用户规则"})
    return {"schema": "carkit.valuation/v1", "version": "user-reference-2026-09-12",
            "source": "内置：竞争力对比配置清单参考(1).xlsx + 用户补充规则", "items": items}


def normalize_valuation(data, rules):
    """Merge a saved editor file with the latest built-in schema and validate numbers."""
    base = default_valuation(rules)
    supplied = {int(item['no']): item for item in (data or {}).get('items', []) if item.get('no') is not None}
    for item in base['items']:
        custom = supplied.get(item['no'], {})
        for key in ('pricing', 'val', 'unit_val', 'bands', 'note', 'rule'):
            if key in custom:
                item[key] = custom[key]
        params = dict(item.get('params') or {})
        for key, value in (custom.get('params') or {}).items():
            if key not in params:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise ValueError(f'#{item["no"]} {key} 必须是数字')
            if not math.isfinite(number) or number < 0:
                raise ValueError(f'#{item["no"]} {key} 必须是大于等于0的有限数字')
            params[key] = int(number) if number.is_integer() else number
        item['params'] = params
        if item.get('rule') == 'flat':
            try:
                number = float(item.get('val'))
            except (TypeError, ValueError):
                raise ValueError(f'#{item["no"]} 固定金额必须是数字')
            if not math.isfinite(number) or number < 0:
                raise ValueError(f'#{item["no"]} 固定金额必须大于等于0')
            item['val'] = int(number) if number.is_integer() else number
    base['version'] = (data or {}).get('version') or base['version']
    base['source'] = (data or {}).get('source') or base['source']
    return base


def _num(v, default=None):
    m = re.search(r"[\d.]+", str(v))
    return float(m.group(0)) if m else default


def item_amount(vitem: dict, self_val, comp_val) -> float | None:
    """单个多/少项的金额（正数）。查不到 → None（标 [待赋值]）"""
    if vitem is None:
        return None
    pricing = vitem.get("pricing", "flat")
    if pricing == "flat":
        return vitem.get("val")
    if pricing == "per_unit":
        # 按颗/按个：数量差 × 单价
        unit = vitem.get("unit_val")
        if unit is None:
            return None
        s = _num(self_val, 0) or 0
        c = _num(comp_val, 0) or 0
        return abs(s - c) * unit
    if pricing == "band":
        # 分档查表：各自落档取金额，差值
        sb = _band_val(vitem, self_val)
        cb = _band_val(vitem, comp_val)
        if sb is None or cb is None:
            return None
        return sb - cb
    if pricing == "segmented_per_km":
        s = _num(self_val, 0) or 0
        c = _num(comp_val, 0) or 0
        return _segmented_km(vitem, s) - _segmented_km(vitem, c)
    if pricing == "manual":
        return vitem.get("val")
    return None


def _band_val(vitem, val):
    n = _num(val)
    if n is None:
        # ✕/无 → 0 元档
        return 0.0 if str(val).strip() in ("✕", "-", "", "无") else None
    for b in vitem.get("bands", []):
        lo, hi = b["range"]
        if lo <= n <= hi:
            return float(b["val"])
    return None


def _segmented_km(vitem, km):
    """分段每km计价：0→km 逐段累计"""
    total = 0.0
    for b in vitem.get("bands", []):
        lo, hi = b["range"]
        per = float(b.get("per_km", 0))
        if km > hi:
            total += (hi - lo + 1) * per
        elif km >= lo:
            total += (km - lo + 1) * per
            break
        else:
            break
    return total


def value_pair(more_map: dict, less_map: dict, self_price, comp_price,
               valuation, overall_formula: str | None = None) -> dict:
    """一组配对的三指标。more_map/less_map: {item_no: backup显示串}"""
    missing = []
    total_more = total_less = 0.0
    detail = []
    for no, disp in more_map.items():
        amt = _amount_for(valuation, no, disp, side="more")
        if amt is None:
            missing.append(no)
        else:
            total_more += abs(amt)
            detail.append({"no": no, "name": (valuation.item(no) or {}).get('name', str(no)), "side": "多", "amount": round(abs(amt), 2), "display": disp, "rule": explain_rule(valuation, no)})
    for no, disp in less_map.items():
        amt = _amount_for(valuation, no, disp, side="less")
        if amt is None:
            missing.append(no)
        else:
            total_less += abs(amt)
            detail.append({"no": no, "name": (valuation.item(no) or {}).get('name', str(no)), "side": "少", "amount": round(-abs(amt), 2), "display": disp, "rule": explain_rule(valuation, no)})
    if missing:
        return {"config_adv": None, "flat_adv": None, "overall": None,
                "missing": sorted(set(missing)), "detail": detail}
    config_adv = round(total_more - total_less, 2)
    flat_adv = None
    if config_adv is not None and self_price is not None and comp_price is not None:
        flat_adv = round(config_adv + (comp_price - self_price) * 10000, 2)
    overall = None
    if overall_formula and overall_formula in OVERALL_FORMULAS and flat_adv is not None:
        overall = OVERALL_FORMULAS[overall_formula](config_adv, flat_adv, self_price, comp_price)
    return {"config_adv": config_adv, "flat_adv": flat_adv, "overall": overall,
            "total_more": total_more, "total_less": total_less,
            "missing": [], "detail": detail}


def explain_rule(valuation, no):
    item = valuation.item(no) or {}
    if item.get('rule') != 'dynamic':
        return f"{item.get('pricing', 'flat')}：{item.get('val')} 元；{item.get('note', '')}"
    params = dict(DEFAULT_DYNAMIC_PARAMS.get(no, {}))
    params.update(item.get('params') or {})
    # The rule text mapping below is built eagerly; unrelated rows therefore
    # ask for keys that do not belong to this item. Only the selected row is
    # returned, so missing unrelated keys render as empty placeholders.
    p = lambda key: params.get(key, '')
    rules = {
        1: f'续航差小于{p("threshold_km")}km计0，否则续航差×{p("per_km")}元/km',
        3: f'800V：{p("platform_800v")}元；其他平台：0元',
        4: f'R{p("base_inch")}钢轮毂为0元；每增加1寸加{p("per_inch")}元，铝轮毂另加{p("alloy_bonus")}元',
        5: f'气囊每个{p("per_airbag")}元，侧气帘计2个、中央气囊计1个',
        6: f'软硬调节{p("soft_hard")}元，高低调节或空气悬架{p("height_or_air")}元；两项可叠加',
        7: f'倒车影像或360影像{p("reverse_or_360")}元，540影像{p("image_540")}元，无配置0元',
        9: f'定速巡航{p("cruise")}元，基础L2 {p("l2")}元，高速NOA {p("highway_noa")}元，城市NOA {p("city_noa")}元',
        12: f'手动前备箱{p("manual")}元、电动前备箱{p("electric")}元',
        17: f'LED大灯{p("led")}元，其他灯光0元',
        18: f'普通电动天窗{p("electric")}元，不可开启全景天窗{p("fixed_panorama")}元，可开启全景天窗{p("opening_panorama")}元',
        20: f'电调、折叠、加热各{p("per_function")}元，按功能数量差计价',
        21: f'中控屏尺寸差≥{p("threshold_inch")}寸计{p("price")}元，未达阈值计0元',
        22: f'副驾屏<{p("small_limit")}寸{p("small")}元，{p("small_limit")}～{p("large_limit")}寸{p("medium")}元，>{p("large_limit")}寸{p("large")}元，无屏0元',
        23: f'4G车联网{p("4g")}元，5G车联网{p("5g")}元，无配置0元',
        25: f'方向盘：塑料{p("plastic")}元、仿皮{p("faux")}元、真皮{p("leather")}元、翻毛皮{p("suede")}元、NAPPA {p("nappa")}元',
        26: f'方向盘手调0元，电调{p("electric")}元',
        29: f'仪表尺寸每寸{p("per_inch")}元，全液晶另加{p("lcd_bonus")}元',
        30: f'HUD {p("hud")}元，AR-HUD {p("ar_hud")}元，P-HUD {p("p_hud")}元',
        31: f'手动防眩目0元，流媒体后视镜{p("streaming")}元',
        32: f'USB/Type-C默认{p("base_count")}个为0元，每个接口差额{p("per_port")}元',
        33: f'无线充电每个{p("per_charger")}元，功率不作为数量',
        34: f'座椅：织物{p("fabric")}元、仿皮{p("faux")}元、真皮{p("leather")}元、翻毛皮{p("suede")}元、NAPPA {p("nappa")}元',
        35: f'座椅每向{p("per_direction")}元，每个电调座椅另加{p("electric_bonus")}元；主副驾合计',
        36: f'每座：通风{p("ventilation")}元、加热{p("heating")}元、按摩{p("massage")}元、头枕音响{p("headrest")}元；前排含主副驾',
        37: f'扬声器每个{p("per_speaker")}元',
        38: f'车外扬声器每个{p("per_speaker")}元',
        39: f'无氛围灯0元，单色{p("single")}元，多色{p("multi")}元',
        45: f'座椅记忆每座{p("per_seat")}元，前排主副驾合计{p("per_seat") * 2}元',
    }
    return rules.get(no, '未配置规则说明') + '；按双方配置价值之差计价'


def _amount_for(valuation, no, disp, side):
    """从显示串反解自/对方值算金额。flat/per_unit 直接取表值；
    band/segmented 需要双方数值——从 disp 'A(B)' 解析"""
    vitem = valuation.item(no)
    if vitem is None:
        return None
    if no == 12 or vitem.get("rule") == "dynamic":
        return _default_rule_amount(no, disp, side, vitem.get('params'))
    pricing = vitem.get("pricing", "flat")
    if pricing in ("flat", "manual"):
        return vitem.get("val")
    m = re.match(r"^([^(（]+)[（(]([^)）]+)[)）]$", disp or "")
    if m:
        self_v, comp_v = m.group(1), m.group(2)
    else:
        self_v, comp_v = disp, "✕"
    if pricing == "per_unit":
        return item_amount(vitem, self_v, comp_v)
    if pricing == "band":
        a = item_amount(dict(vitem, pricing="band"), self_v, comp_v)
        return a
    if pricing == "segmented_per_km":
        return item_amount(vitem, self_v, comp_v)
    return None


def _default_rule_amount(no, disp, side, custom_params=None):
    """Calculate the built-in workbook rules from the P21 display string."""
    text = str(disp or "")
    bits = re.match(r"^(.+?)[（(](.+?)[)）]$", text)
    cur, prev = (bits.group(1), bits.group(2)) if bits else (text, "✕")
    def num(v): return _num(v, 0) or 0
    params = dict(DEFAULT_DYNAMIC_PARAMS.get(no, {}))
    params.update(custom_params or {})
    p = lambda key: params[key]
    if no == 12:
        def front(v): return p('manual') if '手动' in v else p('electric') if '电动' in v or v == '●' else 0
        return abs(front(cur)-front(prev))
    if no == 1: return 0 if abs(num(cur) - num(prev)) < p('threshold_km') else abs(num(cur) - num(prev)) * p('per_km')
    if no == 3: return abs((p('platform_800v') if '800' in cur else 0) - (p('platform_800v') if '800' in prev else 0))
    if no == 4:
        def wheel(v): return max(0, num(v) - p('base_inch')) * p('per_inch') + (p('alloy_bonus') if "铝" in v else 0)
        return abs(wheel(cur) - wheel(prev))
    if no == 5: return abs(num(cur) - num(prev)) * p('per_airbag')
    if no == 6:
        def suspension(v): return (p('soft_hard') if "软硬" in v else 0) + (p('height_or_air') if "高低" in v or "空气" in v else 0)
        return abs(suspension(cur) - suspension(prev))
    if no == 7: return abs((p('image_540') if "540" in cur else p('reverse_or_360') if "360" in cur or '倒车影像' in cur else 0) - (p('image_540') if "540" in prev else p('reverse_or_360') if "360" in prev or '倒车影像' in prev else 0))
    if no == 9:
        from .differ import normalize_adas
        def adas(v):
            return {'城市NOA':p('city_noa'),'高速NOA':p('highway_noa'),'基础L2':p('l2'),'定速巡航':p('cruise')}.get(normalize_adas(v), 0)
        return abs(adas(cur) - adas(prev))
    if no == 10: return 0
    if no == 17: return abs((p('led') if 'LED' in cur else 0)-(p('led') if 'LED' in prev else 0))
    if no == 18:
        def roof(v): return p('fixed_panorama') if "不可开启全景" in v else p('opening_panorama') if "可开启全景" in v else p('electric') if "电动" in v else 0
        return abs(roof(cur) - roof(prev))
    if no == 20: return abs(cur.count("电调") + cur.count("折叠") + cur.count("加热") - prev.count("电调") - prev.count("折叠") - prev.count("加热")) * p('per_function')
    if no == 21: return p('price') if abs(num(cur) - num(prev)) >= p('threshold_inch') else 0
    if no == 22:
        def screen(v): return p('large') if num(v) > p('large_limit') else p('small') if num(v) < p('small_limit') and num(v) else p('medium') if num(v) else 0
        return abs(screen(cur) - screen(prev))
    if no == 23: return abs((p('5g') if "5G" in cur else p('4g') if "4G" in cur else 0) - (p('5g') if "5G" in prev else p('4g') if "4G" in prev else 0))
    if no == 25:
        rank = {"塑料": p('plastic'), "仿皮": p('faux'), "真皮": p('leather'), "翻毛皮": p('suede'), "NAPPA": p('nappa')}
        return abs(next((v for k,v in reversed(list(rank.items())) if k in cur),0)-next((v for k,v in reversed(list(rank.items())) if k in prev),0))
    if no == 26: return abs((p('electric') if '电' in cur else 0)-(p('electric') if '电' in prev else 0))
    if no == 27: return 800 if "电调" in cur and "电调" not in prev else 0
    if no == 29:
        def cluster(v): return (p('lcd_bonus') if "全液晶" in v else 0) + num(v)*p('per_inch')
        return abs(cluster(cur) - cluster(prev))
    if no == 30:
        def hud(v): return p('p_hud') if 'P-HUD' in v else p('ar_hud') if 'AR-HUD' in v else p('hud') if 'HUD' in v else 0
        return abs(hud(cur)-hud(prev))
    if no == 31: return p('streaming') if "流媒体" in cur and "流媒体" not in prev else 0
    if no == 32:
        from .usb import usb_total
        return abs((usb_total(cur) or p('base_count')) - ((usb_total(prev) or p('base_count')) if bits else p('base_count'))) * p('per_port')
    if no == 33:
        def chargers(v):
            if v.strip() in ('✕','X','无',''): return 0
            m = re.search(r'(\d+)\s*(?:个|处)', v)
            return int(m[1]) if m else 2 if '双' in v else 1
        return abs(chargers(cur) - chargers(prev)) * p('per_charger')
    if no == 34:
        rank = {"织物": p('fabric'), "仿皮": p('faux'), "真皮": p('leather'), "翻毛皮": p('suede'), "NAPPA": p('nappa')}
        return abs(next((v for k,v in reversed(list(rank.items())) if k in cur),0)-next((v for k,v in reversed(list(rank.items())) if k in prev),0))
    if no == 35:
        def seats(v):
            found = re.findall(r'(?:主驾|副驾)(\d+)向(电调|手调)', v)
            return sum(int(n)*p('per_direction')+(p('electric_bonus') if mode=='电调' else 0) for n,mode in found) if found else num(v)*p('per_direction')+(p('electric_bonus') if '电调' in v else 0)
        return abs(seats(cur)-seats(prev))
    if no == 36:
        difference = re.search(r'差价(\d+)元', text)
        if difference:
            return int(difference[1])
        vals = {"通风":p('ventilation'), "加热":p('heating'), "按摩":p('massage'), "头枕":p('headrest')}
        def seats(v):
            count = 2 if '前排' in v or '主副' in v else 1
            return count * sum(price for feature, price in vals.items() if feature in v)
        return abs(seats(cur)-seats(prev))
    if no in {37, 38}:
        def speakers(v):
            return _num(v, 1 if '扬声器' in v else 0) or 0
        return abs(speakers(cur)-speakers(prev))*p('per_speaker')
    if no == 39:
        from .differ import ambient_level
        prices = [0, p('single'), p('multi')]
        return abs(prices[ambient_level(cur)] - prices[ambient_level(prev)])
    if no == 40: return 2000 if cur not in ("✕","") and prev in ("✕","") else 0
    if no == 41: return 200 if cur not in ("✕","") and prev in ("✕","") else 0
    if no == 45:
        def count(v): return 0 if v in ('✕','') else 2 if '前排' in v or '主副' in v else 1
        return abs(count(cur)-count(prev))*p('per_seat')
    return 0


# ---------- xlsx 模板生成（pjy 填金额用） ----------

def make_template_xlsx(path, rules, existing=None):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "赋值表"
    ws.append(["#", "配置项", "计价方式(flat/segmented_per_km/band/per_unit)",
               "金额(元)或单价", "分段/分档(JSON，可空)", "备注", "内置规则", "动态参数(JSON)"])
    existing = existing or {}
    for item in rules.items:
        no = item["no"]
        ex = existing.get(no, {})
        ws.append([no, item.get("md_name") or item["name"],
                   ex.get("pricing", "flat"), ex.get("val", ""),
                   json.dumps(ex.get("bands", ""), ensure_ascii=False) if ex.get("bands") else "",
                   ex.get("note", ""), ex.get("rule", ""),
                   json.dumps(ex.get("params", {}), ensure_ascii=False) if ex.get("params") else ""])
    ws2 = wb.create_sheet("说明")
    ws2.append(["计价方式说明："])
    ws2.append(["flat", "固定金额：有=金额，无=0（例：800V=2000）"])
    ws2.append(["per_unit", "按数量差×单价（例：激光雷达3000/颗）"])
    ws2.append(["band", "分档查表取差值，分段列填 JSON: [{\"range\":[6,8],\"val\":250},...]"])
    ws2.append(["segmented_per_km", "每km分段累计（例：续航 401-500km 每km 120元），JSON 同上但键为 per_km"])
    ws2.append(["", "留空的项 = [待赋值]，对比结果中该组金额行显示占位，程序不脑补"])
    wb.save(path)
    return path


def load_xlsx(path) -> dict:
    """读回 pjy 填的赋值表 xlsx → ValuationTable JSON dict"""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    ws = wb["赋值表"]
    items = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or row[0] is None:
            continue
        no, name, pricing, val, bands, note, rule, params = (list(row) + [None] * 8)[:8]
        if val in (None, "") and not params and rule != 'dynamic':
            continue    # 留空 = 待赋值
        if str(val).strip() in ('/', '／'):
            rule, pricing, val = 'excluded', 'manual', 0
        bands_list = []
        if bands:
            try:
                bands_list = json.loads(bands)
            except Exception:
                bands_list = []
        params_dict = {}
        if params:
            try:
                params_dict = json.loads(params)
            except Exception:
                params_dict = {}
        items.append({"no": int(no), "name": str(name), "pricing": str(pricing or "flat"),
                      "val": float(val) if val not in (None, "") and (pricing in ("flat", "manual", "per_unit") or not bands_list) else None,
                      "unit_val": float(val) if val not in (None, "") and pricing == "per_unit" else None,
                      "bands": bands_list, "note": str(note or ""), "rule": str(rule or ""),
                      "params": params_dict})
    return {"schema": "carkit.valuation/v1", "version": "", "source": f"pjy 赋值表 {path}",
            "items": items}
