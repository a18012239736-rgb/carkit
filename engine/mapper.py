"""mapper — canonical RawTable → 41 项归一化值（竞品侧）

每个清单项一个归一化函数，规则来源：
- 对比配置清单-v1.md 的 pjy 填写规则括注
- golden 夹具 竞品阶梯-启源Q05-2026-09-11.md 的实测值形态
铁律：汽车之家无该配置行 = 该车没有（✕, row_absent）；不脑补。
"""
from __future__ import annotations
import re
from .models import RawTable, Cell

ABSENT = "✕"


# ---------- 基础工具 ----------

def _cell(raw: RawTable, row_names, i: int) -> Cell | None:
    """取第 i 个版型在候选行名下第一个存在行的 cell"""
    for name in row_names:
        r = raw.row(name)
        if r is not None and i < len(r.cells):
            return r.cells[i]
    return None


def _has_row(raw: RawTable, row_names) -> bool:
    return any(raw.row(n) is not None for n in row_names)


def _txt(c: Cell | None) -> str:
    return (c.text or "").strip() if c else ""


def _solid(c: Cell | None) -> bool:
    return bool(c and c.dot == "●")


def _optional(c: Cell | None) -> bool:
    return bool(c and c.dot == "○")


def _bool_val(c: Cell | None) -> str:
    if _solid(c):
        return "●"
    if _optional(c):
        return "○(选装)"
    return ABSENT


def _num(text: str):
    m = re.search(r"[\d.]+", text or "")
    return float(m.group(0)) if m else None


# ---------- 各项归一化 ----------

def n_range(raw, i, cfg):
    rows = cfg["source_rows"]
    c = _cell(raw, rows, i)
    v = _num(_txt(c))
    if v is None:
        return ABSENT
    return f"{int(v)}km"


def n_cell_brand(raw, i, cfg):
    c = _cell(raw, ["电芯品牌"], i)
    if not _solid(c):
        return ABSENT
    brand = _txt(c)
    bt = _cell(raw, ["电池类型"], i)
    if _solid(bt) and _txt(bt):
        btype = re.sub(r"电池$", "", _txt(bt))     # 磷酸铁锂电池 → 磷酸铁锂
        return f"{brand}({btype})"
    return brand


def n_high_voltage(raw, i, cfg):
    c = _cell(raw, cfg["source_rows"], i)
    if c is None:
        return ABSENT
    t = _txt(c)
    if _solid(c):
        return "●800V" if "800" in t else f"●{t or '高压平台'}"
    return ABSENT


def n_tire(raw, i, cfg):
    tc = _cell(raw, ["前轮胎规格"], i)
    t = _txt(tc)
    m = re.search(r"R(\d+)", t)
    if not m and not _solid(tc):
        return ABSENT
    r = m.group(1) if m else "?"
    mc = _cell(raw, ["轮圈材质"], i)
    mt = _txt(mc)
    if "钢" in mt:
        mat = "钢轮毂"
    elif "铝" in mt:
        mat = "铝"
    else:
        mat = mt
    return f"R{r}{mat}"


_AIRBAG_COMP = [("主/副驾驶座安全气囊", "主副"), ("前/后排侧气囊", "侧"), ("前/后排头部气囊(气帘)", "气帘")]


def n_airbag(raw, i, cfg):
    """返回 (count, components:list[str])；显示层再拼"""
    count, comps = 0, []
    for row_name, comp in _AIRBAG_COMP:
        c = _cell(raw, [row_name], i)
        if not _solid(c):
            continue
        t = _txt(c)
        if comp == "主副":
            count += 2
            comps.append("主副")
        else:
            # '前/后-' = 前有后无；'前/后' = 前后都有
            tokens = t.split("/")
            front = len(tokens) > 0 and not tokens[0].endswith("-")
            rear = len(tokens) > 1 and not tokens[1].endswith("-")
            if comp == "侧":
                if front:
                    count += 2
                    comps.append("前侧")
                if rear:
                    count += 2
                    comps.append("后侧")
            else:  # 气帘：物理上左右各1条覆盖前后排，无论标注均计2、统一叫「前气帘」（golden 口径）
                count += 2
                comps.append("前气帘")
    if any(_solid(_cell(raw, [name], i)) for name in ('中央安全气囊', '前排中央安全气囊')):
        count += 1
        comps.append('中央气囊')
    if count == 0:
        return 0, []
    return count, comps


def n_suspend(raw, i, cfg):
    for rn in ("魔毯智能悬架", "空气悬架"):
        c = _cell(raw, [rn], i)
        if _solid(c):
            return "●魔毯悬架" if "魔毯" in rn else "●空气悬架"
    c = _cell(raw, ["可变悬架功能", "可变悬架"], i)
    if c is None:
        return ABSENT
    if _solid(c):
        core = _txt(c).replace("悬架", "", 1) if _txt(c).startswith("悬架") else _txt(c)
        return f"●{core or '可变悬架'}"
    if _optional(c):
        core = _txt(c).replace("悬架", "", 1) if _txt(c).startswith("悬架") else _txt(c)
        return f"○{core or '可变悬架'}(选装)"
    return ABSENT


def n_camera540(raw, i, cfg):
    c540 = _cell(raw, ["透明底盘/540度影像"], i)
    if _solid(c540):
        return "540影像"
    c = _cell(raw, ["驾驶辅助影像"], i)
    if not _solid(c):
        return ABSENT
    t = _txt(c)
    # 双子项里也可能藏 540
    all_t = t + " ".join(s.text for s in (c.subs if isinstance(c, Cell) else []))
    if "540" in all_t:
        return "540影像"
    if "360" in all_t:
        return "360影像"
    return t or "●"


_LIDAR_BRAND = {"HESAI禾赛科技": "禾赛", "禾赛": "禾赛", "华为": "华为", "速腾聚创": "速腾聚创", "览沃": "览沃"}


def n_lidar(raw, i, cfg):
    cn = _cell(raw, ["激光雷达数量"], i)
    if not _solid(cn):
        return ABSENT
    n = _num(_txt(cn)) or 1
    cb = _cell(raw, ["激光雷达品牌"], i)
    brand = _LIDAR_BRAND.get(_txt(cb), _txt(cb))
    return f"●{int(n)}颗({brand})" if brand else f"●{int(n)}颗"


def n_adas(raw, i, cfg):
    seg = _cell(raw, ["辅助驾驶路段"], i)
    sysc = _cell(raw, ["辅助驾驶系统"], i)
    lvl = _cell(raw, ["辅助驾驶等级"], i)
    cruise = _cell(raw, ["巡航系统", "巡航系统类型"], i)
    seg_t, sys_t = _txt(seg), _txt(sysc)
    if _solid(seg) and "城市" in seg_t:
        return "城市NOA"
    if _solid(seg) and "高速" in seg_t:
        return "高速NOA"
    if _solid(sysc) and "城市" in sys_t:
        return "城市NOA"
    if _solid(sysc) and ("高速" in sys_t or "领航" in sys_t):
        return "高速NOA"
    if _solid(lvl) and "L2" in _txt(lvl).upper():
        base = "基础L2"
        if _optional(sysc) and sys_t:
            return f"{base}(○{sys_t}选装)"
        return base
    if _solid(sysc):
        return "基础L2"
    if _solid(cruise):
        return f"{_txt(cruise)}(无L2)"
    return ABSENT


def n_bool(raw, i, cfg):
    c = _cell(raw, cfg["source_rows"], i)
    return _bool_val(c)


def n_seat_memory(raw, i, cfg):
    c = _cell(raw, cfg['source_rows'], i)
    if not _solid(c):
        return _bool_val(c)
    t = _txt(c)
    if '前排' in t or ('主驾' in t and '副驾' in t):
        return '前排座椅记忆'
    if '副驾' in t or '副驾驶' in t:
        return '副驾座椅记忆'
    if '主驾' in t or '驾驶位' in t or '主驾驶' in t:
        return '主驾座椅记忆'
    return '[待定]座椅记忆位置未说明'


def n_trunk(raw, i, cfg):
    c = _cell(raw, ["电动后备厢", "电动后备箱"], i)
    if not _solid(c):
        return _bool_val(c)
    memo = _cell(raw, ["电动后备厢位置记忆"], i)
    return "●(带位置记忆)" if _solid(memo) else "●"


def n_v2l(raw, i, cfg):
    c = _cell(raw, ["对外放电"], i)
    if not _solid(c):
        return _bool_val(c)
    p = _cell(raw, ["对外交流放电功率(kW)", "对外放电功率(kW)"], i)
    pv = _num(_txt(p))
    return f"●{pv:g}kW" if pv else "●"


def n_lamp(raw, i, cfg):
    c = _cell(raw, ["近光灯光源"], i)
    if not _solid(c):
        return _bool_val(c)
    t = _txt(c).upper()
    if "LED" in t:
        return "LED大灯"
    if "LCD" in t:
        return "LCD大灯"
    if "氙" in t:
        return "氙气大灯"
    if "卤素" in t:
        return "卤素大灯"
    return f"{_txt(c)}大灯"


def n_sunroof(raw, i, cfg):
    c = _cell(raw, ["天窗类型"], i)
    if c is None:
        return ABSENT

    def core(cell):
        t = _txt(cell)
        if t.endswith("天窗") and len(t) > 2:
            t = t[:-2]
        return t or "天窗"

    if _solid(c):
        return f"●{core(c)}"
    if _optional(c):
        return f"○{core(c)}(选装)"
    # 主子项为 - 但 subs 有 ○
    for s in (c.subs or []):
        if s.dot == "○":
            return f"○{core(s)}(选装)"
    return ABSENT


def n_mirror(raw, i, cfg):
    c = _cell(raw, ["外后视镜功能"], i)
    if not _solid(c):
        return _bool_val(c)
    parts = [c.text] + [s.text for s in (c.subs or [])]
    joined = " ".join(p for p in parts if p)
    feats = []
    if "电动调节" in joined:
        feats.append("电调")
    if "电动折叠" in joined:
        feats.append("折叠")
    if "加热" in joined:
        feats.append("加热")
    return "+".join(feats) if feats else "●"


def _screen_core(t: str) -> str:
    m = re.search(r"([\d.]+)", t or "")
    return f"{m.group(1)}寸" if m else (t or "")


def n_screen_center(raw, i, cfg):
    c = _cell(raw, ["中控屏幕尺寸"], i)
    if c is None:
        c = _cell(raw, ["中控彩色屏幕"], i)
    if not _solid(c):
        return _bool_val(c)
    base = f"{_screen_core(_txt(c))}中控"
    for s in (c.subs or []):
        if s.dot == "○":
            n = re.search(r"[\d.]+", s.text or "")
            base += f"(○{n.group(0) if n else s.text}选装)"
    return base


def n_screen_passenger(raw, i, cfg):
    c = _cell(raw, cfg["source_rows"], i)
    if not _solid(c):
        return _bool_val(c)
    return f"{_screen_core(_txt(c))}副驾屏"


def n_network(raw, i, cfg):
    c = _cell(raw, ["4G/5G网络"], i)
    if _solid(c) and _txt(c):
        return _txt(c)
    c2 = _cell(raw, ["车联网"], i)
    if _solid(c2):
        return "●"
    return ABSENT


def n_material(raw, i, cfg):
    c = _cell(raw, cfg["source_rows"], i)
    if not _solid(c):
        return _bool_val(c)
    return _txt(c)


def n_steer_adjust(raw, i, cfg):
    c = _cell(raw, ["方向盘位置调节"], i)
    if not _solid(c):
        return _bool_val(c)
    t = _txt(c)
    if "电动" in t:
        return "电调"
    if "手动" in t:
        return "手动调"
    return t


def n_cluster(raw, i, cfg):
    full = _cell(raw, ["全液晶仪表盘"], i)
    size_c = _cell(raw, ["液晶仪表尺寸", "行车电脑显示屏幕"], i)
    size = _screen_core(_txt(size_c)).replace("寸", "")
    size_s = f"{size}寸" if size else ""
    if _solid(full):
        return f"全液晶仪表({size_s})" if size_s else "全液晶仪表"
    if _optional(full):
        return f"{size_s}仪表(○全液晶选装)" if size_s else "○全液晶(选装)"
    if size_s:
        return f"{size_s}仪表"
    return _bool_val(size_c)


def n_hud(raw, i, cfg):
    c = _cell(raw, cfg["source_rows"], i)
    if not _solid(c):
        return _bool_val(c)
    t = _txt(c).upper()
    if "P-HUD" in t or "P HUD" in t:
        return "●P-HUD"
    if "AR" in t:
        return "●AR-HUD"
    return "●HUD"


def n_rearview(raw, i, cfg):
    c = _cell(raw, ["内后视镜功能"], i)
    if not _solid(c):
        return _bool_val(c)
    parts = [c.text] + [s.text for s in (c.subs or [])]
    joined = " ".join(parts)
    if "流媒体" in joined:
        return "流媒体"
    if "防眩目" in joined:
        return "手动防眩目"
    return _txt(c)


def n_usb(raw, i, cfg):
    from .usb import usb_label
    c = _cell(raw, ["USB/Type-C接口数量"], i)
    if not _solid(c):
        return usb_label('') if not c or not c.dot else _bool_val(c)
    return usb_label(_txt(c))


def n_wireless_charge(raw, i, cfg):
    c = _cell(raw, ["手机无线充电功能"], i)
    if not _solid(c):
        return _bool_val(c)
    pos = _txt(c) or "前排"
    p = _cell(raw, ["手机无线充电功率"], i)
    pw = _txt(p) if _solid(p) else ""
    return f"●{pos}{pw}"


def n_seat_adjust(raw, i, cfg):
    elec = _cell(raw, ["主/副驾驶座电动调节"], i)
    main_c = _cell(raw, ["主座椅调节方式"], i)
    pas_c = _cell(raw, ["副座椅调节方式"], i)

    def extras(cell):
        if cell is None:
            return []
        parts = [cell.text] + [s.text for s in (cell.subs or [])]
        joined = " ".join(p for p in parts if p)
        ex = []
        m = re.search(r"腿部支撑\((\d+)向\)|腰[部部]?支撑\((\d+)向\)|腰部支撑\((\d+)向\)", joined)
        if "腿托" in joined:
            ex.append("腿托")
        w = re.search(r"腰[部]?支撑\((\d+)向\)", joined)
        if w:
            ex.append(f"腰撑{w.group(1)}向")
        return ex

    if _solid(elec):
        base = "主副电调"
    else:
        base = "主副手调"
    mex, pex = extras(main_c), extras(pas_c)
    if mex and not pex:
        return f"{base}(主含{'+'.join(mex)})"
    if mex and pex:
        return f"{base}(主{'+'.join(mex)}/副{'+'.join(pex)})"
    if pex:
        return f"{base}(副含{'+'.join(pex)})"
    return base


_SEAT_FUNCS = ["加热", "通风", "按摩"]


def n_seat_func(raw, i, cfg):
    from .seat_functions import SUBS, from_text
    c = _cell(raw, ["前排座椅功能"], i)
    parts = []
    if c:
        for src in ([c] if c.text else []) + list(c.subs or []):
            if src.dot == "●" and src.text:
                parts.append(src.text)
    funcs = [f for f in _SEAT_FUNCS if any(f in p for p in parts)]
    only_driver = any("仅驾驶位" in p or "仅主驾" in p for p in parts)
    if not funcs:
        val = ABSENT
    elif only_driver:
        val = f"{'/'.join(funcs)}(仅主驾)"
    else:
        val = f"前排{'/'.join(funcs)}(主副)"
    hc = _cell(raw, ["前排座椅头枕扬声器", "头枕音响"], i)
    row2 = _cell(raw, ["第二排座椅功能", "后排座椅功能"], i)
    rparts = []
    if row2:
        rparts = ([row2.text] if row2.dot == "●" and row2.text else []) + \
                 [s.text for s in (row2.subs or []) if s.dot == "●"]
    sub_map = from_text('+'.join(parts), '+'.join(rparts), (_txt(hc) or '头枕音响') if _solid(hc) else '')
    return val, funcs, {sub: sub_map[sub] for sub in SUBS}


def n_speaker(raw, i, cfg):
    c = _cell(raw, cfg["source_rows"], i)
    if not _solid(c):
        return _bool_val(c)
    n = _num(_txt(c))
    return str(int(n)) if n is not None else _txt(c)


def n_ambient(raw, i, cfg):
    c = _cell(raw, ["车内环境氛围灯"], i)
    if not _solid(c):
        return _bool_val(c)
    t = _txt(c)
    n = _num(t)
    if n and n > 1:
        return f"多色({int(n)}色)"
    if "单色" in t:
        return "单色"
    if "多色" in t:
        return "多色"
    return "●"


def n_text(raw, i, cfg):
    c = _cell(raw, cfg["source_rows"], i)
    if not _solid(c):
        return _bool_val(c)
    return _txt(c) or "●"


NORMALIZERS = {
    "range_km": n_range,
    "text": n_text,
    "cell_brand": n_cell_brand,
    "steer_adjust": n_steer_adjust,
    "high_voltage": n_high_voltage,
    "tire": n_tire,
    "airbag_count": n_airbag,
    "suspend": n_suspend,
    "camera540": n_camera540,
    "lidar": n_lidar,
    "adas": n_adas,
    "bool": n_bool,
    "trunk": n_trunk,
    "v2l": n_v2l,
    "lamp": n_lamp,
    "sunroof": n_sunroof,
    "mirror": n_mirror,
    "screen_center": n_screen_center,
    "screen_passenger": n_screen_passenger,
    "network": n_network,
    "material": n_material,
    "cluster": n_cluster,
    "hud": n_hud,
    "rearview": n_rearview,
    "usb": n_usb,
    "wireless_charge": n_wireless_charge,
    "seat_adjust": n_seat_adjust,
    "seat_func": n_seat_func,
    "seat_memory": n_seat_memory,
    "speaker_count": n_speaker,
    "ambient": n_ambient,
}


def map_raw_to_ladder(raw: RawTable, rules) -> dict:
    """返回 {item_no: {"values": [...], "row_absent": bool, "subs": [...], "airbag": [...]}}"""
    out = {}
    n_trims = len(raw.trims)
    for item in rules.items:
        no, vt = item["no"], item.get("normalize", "bool")
        rows = item.get("source_rows", [])
        row_absent = rows and not _has_row(raw, rows)
        fn = NORMALIZERS.get(vt, n_bool)
        values, extra = [], {}
        airbag_comps = []
        subs_rows = []
        for i in range(n_trims):
            if vt == "airbag_count":
                cnt, comps = fn(raw, i, item)
                values.append(cnt)
                airbag_comps.append(comps)
            elif vt == "seat_func":
                from .seat_functions import SUBS
                val, funcs, sub_map = fn(raw, i, item)
                values.append(val)
                if not subs_rows:
                    subs_rows = [{"sub": s, "values": []} for s in SUBS]
                for sr in subs_rows:
                    sr["values"].append(sub_map.get(sr["sub"], ABSENT))
            else:
                values.append(fn(raw, i, item))
        entry = {"values": values, "row_absent": bool(row_absent), "subs": subs_rows}
        if airbag_comps:
            entry["airbag_comps"] = airbag_comps
        out[no] = entry
    return out
