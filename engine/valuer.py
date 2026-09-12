"""valuer — 赋值引擎：金额来自 pjy 规定的赋值表（ValuationTable），程序不脑补

公式（拉平口径已由 pjy 手工草稿验证，最终以 pjy 确认为准）：
- 单项金额 = f(赋值表 pricing 类型, 自方值, 对方值)
- 配置优势 = Σ(多项金额) − Σ(少项金额)
- 拉平指导价优势 = 配置优势 + (竞品指导价 − 自产品指导价) × 10000
- 综合竞争力 = 可插拔公式（pjy 未提供前输出 None → 渲染层显示 [待公式]）

任何一项查不到金额 → 该组 config_adv=None 并列出 missing（渲染层显示 待赋值明细表/[待赋值]）。
"""
from __future__ import annotations
import json
import re

# 综合竞争力公式注册表：pjy 给公式后在此登记
OVERALL_FORMULAS = {}

# Built-in version of the user's "竞争力对比配置清单参考(1).xlsx".
# A slash in the workbook means the item is deliberately zero-valued.
DEFAULT_FLAT = {
    2: 0, 3: 2000, 8: 0, 11: 2000, 12: 1000, 13: 800,
    14: 300, 15: 1000, 16: 500, 19: 0, 24: 0, 27: 200,
    28: 100, 40: 800, 41: 200,
}
ZERO_ITEMS = {2, 9, 20, 25}
EXCLUDED_ITEMS = {2, 8, 19, 24}  # Workbook '/' entries, not zero-price base tiers.


def default_valuation(rules):
    """Return the built-in valuation table, without requiring an xlsx upload."""
    items = []
    for item in rules.items:
        no = item["no"]
        if item.get("merged_into"):
            continue
        rule = "dynamic" if no in {1, 3, 4, 5, 6, 7, 9, 17, 18, 20, 21, 22, 23, 25, 26, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39} else "flat"
        if no in EXCLUDED_ITEMS:
            rule = 'excluded'
        items.append({"no": no, "name": item.get("md_name") or item["name"],
                      "pricing": "manual", "val": 0 if no in ZERO_ITEMS else DEFAULT_FLAT.get(no),
                      "unit_val": None, "bands": [], "rule": rule,
                      "note": "内置：竞争力对比配置清单参考(1).xlsx；/按0元处理" if no in ZERO_ITEMS else "内置用户规则"})
    return {"schema": "carkit.valuation/v1", "version": "user-reference-2026-09-12",
            "source": "内置：竞争力对比配置清单参考(1).xlsx + 用户补充规则", "items": items}


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
            detail.append({"no": no, "name": (valuation.item(no) or {}).get('name', str(no)), "side": "多", "amount": abs(amt), "display": disp, "rule": explain_rule(valuation, no)})
    for no, disp in less_map.items():
        amt = _amount_for(valuation, no, disp, side="less")
        if amt is None:
            missing.append(no)
        else:
            total_less += abs(amt)
            detail.append({"no": no, "name": (valuation.item(no) or {}).get('name', str(no)), "side": "少", "amount": -abs(amt), "display": disp, "rule": explain_rule(valuation, no)})
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
    return {1:'续航差小于50km计0，否则续航差×60元/km',4:'轮径每级700元，铝轮毂比钢轮毂500元',5:'气囊数量差×350元',21:'中控尺寸差小于3寸计0，否则500元',33:'无线充电按数量计：每个350元，功率不作为数量',36:'通风400、加热250、按摩600、记忆100、头枕音响100元',37:'扬声器数量差×100元',38:'车外扬声器数量差×100元',29:'仪表尺寸差×100元，全液晶附加200元'}.get(no, '内置分档规则：双方配置价值之差')


def _amount_for(valuation, no, disp, side):
    """从显示串反解自/对方值算金额。flat/per_unit 直接取表值；
    band/segmented 需要双方数值——从 disp 'A(B)' 解析"""
    vitem = valuation.item(no)
    if vitem is None:
        return None
    if vitem.get("rule") == "dynamic":
        return _default_rule_amount(no, disp, side)
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


def _default_rule_amount(no, disp, side):
    """Calculate the built-in workbook rules from the P21 display string."""
    text = str(disp or "")
    bits = re.match(r"^(.+?)[（(](.+?)[)）]$", text)
    cur, prev = (bits.group(1), bits.group(2)) if bits else (text, "✕")
    def num(v): return _num(v, 0) or 0
    if no == 1: return 0 if abs(num(cur) - num(prev)) < 50 else abs(num(cur) - num(prev)) * 60
    if no == 3: return abs((2000 if '800' in cur else 0) - (2000 if '800' in prev else 0))
    if no == 4:
        def wheel(v): return max(0, num(v) - 16) * 700 + (500 if "铝" in v else 0)
        return abs(wheel(cur) - wheel(prev))
    if no == 5: return abs(num(cur) - num(prev)) * 350
    if no == 6:
        def suspension(v): return (1000 if "软硬" in v else 0) + (8000 if "高低" in v or "空气" in v else 0)
        return abs(suspension(cur) - suspension(prev))
    if no == 7: return abs((1500 if "540" in cur else 1000 if "360" in cur or '倒车影像' in cur else 0) - (1500 if "540" in prev else 1000 if "360" in prev or '倒车影像' in prev else 0))
    if no == 9:
        from .differ import normalize_adas
        def adas(v):
            return {'城市NOA':8000,'高速NOA':3000,'基础L2':1000,'定速巡航':500}.get(normalize_adas(v), 0)
        return abs(adas(cur) - adas(prev))
    if no == 10: return 0
    if no == 17: return 1000 if "LED" in cur and "LED" not in prev else 0
    if no == 18:
        def roof(v): return 2000 if "不可开启全景" in v else 2500 if "可开启全景" in v else 1000 if "电动" in v else 0
        return abs(roof(cur) - roof(prev))
    if no == 20: return abs(cur.count("电调") + cur.count("折叠") + cur.count("加热") - prev.count("电调") - prev.count("折叠") - prev.count("加热")) * 100
    if no == 21: return 500 if abs(num(cur) - num(prev)) >= 3 else 0
    if no == 22:
        def screen(v): return 1500 + (500 if num(v) > 15.6 else -500 if num(v) < 12.6 and num(v) else 0) if num(v) else 0
        return abs(screen(cur) - screen(prev))
    if no == 23: return abs((3000 if "5G" in cur else 2000 if "4G" in cur else 0) - (3000 if "5G" in prev else 2000 if "4G" in prev else 0))
    if no == 25:
        rank = {"塑料": 0, "仿皮": 250, "真皮": 500, "翻毛皮": 600, "NAPPA": 700}
        return abs(next((v for k,v in reversed(list(rank.items())) if k in cur),0)-next((v for k,v in reversed(list(rank.items())) if k in prev),0))
    if no == 26: return abs((800 if '电' in cur else 0)-(800 if '电' in prev else 0))
    if no == 27: return 800 if "电调" in cur and "电调" not in prev else 0
    if no == 29:
        def cluster(v): return (200 if "全液晶" in v else 0) + num(v)*100
        return abs(cluster(cur) - cluster(prev))
    if no == 30: return 2000 if "AR-HUD" in cur else 1000 if "HUD" in cur else 0
    if no == 31: return 1000 if "流媒体" in cur and "流媒体" not in prev else 0
    if no == 32: return abs(num(cur) - num(prev)) * 50
    if no == 33:
        def chargers(v):
            if v.strip() in ('✕','X','无',''): return 0
            m = re.search(r'(\d+)\s*(?:个|处)', v)
            return int(m[1]) if m else 2 if '双' in v else 1
        return abs(chargers(cur) - chargers(prev)) * 350
    if no == 34:
        rank = {"织物": 0, "仿皮": 1500, "真皮": 2500, "翻毛皮": 3000, "NAPPA": 3500}
        return abs(next((v for k,v in reversed(list(rank.items())) if k in cur),0)-next((v for k,v in reversed(list(rank.items())) if k in prev),0))
    if no == 35:
        def seats(v):
            found = re.findall(r'(?:主驾|副驾)(\d+)向(电调|手调)', v)
            return sum(int(n)*50+(400 if mode=='电调' else 0) for n,mode in found) if found else num(v)*50+(400 if '电调' in v else 0)
        return abs(seats(cur)-seats(prev))
    if no == 36:
        vals = {"通风":400, "加热":250, "按摩":600, "记忆":100, "头枕":100}
        return abs(sum(v for k,v in vals.items() if k in cur)-sum(v for k,v in vals.items() if k in prev))
    if no in {37, 38}:
        def speakers(v):
            return _num(v, 1 if '扬声器' in v else 0) or 0
        return abs(speakers(cur)-speakers(prev))*100
    if no == 39:
        from .differ import ambient_level
        prices = [0, 200, 600]
        return abs(prices[ambient_level(cur)] - prices[ambient_level(prev)])
    if no == 40: return 800 if cur not in ("✕","") and prev in ("✕","") else 0
    if no == 41: return 200 if cur not in ("✕","") and prev in ("✕","") else 0
    return 0


# ---------- xlsx 模板生成（pjy 填金额用） ----------

def make_template_xlsx(path, rules, existing=None):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "赋值表"
    ws.append(["#", "配置项", "计价方式(flat/segmented_per_km/band/per_unit)",
               "金额(元)或单价", "分段/分档(JSON，可空)", "备注", "内置规则"])
    existing = existing or {}
    for item in rules.items:
        no = item["no"]
        ex = existing.get(no, {})
        ws.append([no, item.get("md_name") or item["name"],
                   ex.get("pricing", "flat"), ex.get("val", ""),
                   json.dumps(ex.get("bands", ""), ensure_ascii=False) if ex.get("bands") else "",
                   ex.get("note", ""), ex.get("rule", "")])
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
        no, name, pricing, val, bands, note, rule = (list(row) + [None] * 7)[:7]
        if val in (None, ""):
            continue    # 留空 = 待赋值
        if str(val).strip() in ('/', '／'):
            rule, pricing, val = 'excluded', 'manual', 0
        bands_list = []
        if bands:
            try:
                bands_list = json.loads(bands)
            except Exception:
                bands_list = []
        items.append({"no": int(no), "name": str(name), "pricing": str(pricing or "flat"),
                      "val": float(val) if pricing in ("flat", "manual", "per_unit") or not bands_list else None,
                      "unit_val": float(val) if pricing == "per_unit" else None,
                      "bands": bands_list, "note": str(note or ""), "rule": str(rule or "")})
    return {"schema": "carkit.valuation/v1", "version": "", "source": f"pjy 赋值表 {path}",
            "items": items}
