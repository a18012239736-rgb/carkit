"""differ — 判定引擎：快照(自产品) × 竞品阶梯 → 41项判定（多/少/同/豁免/不计）

铁律：
- 版型配对由调用方（pjy）指定，本模块绝不自动配对
- [待定] 不计入多/少；选装○不计为有；豁免规则来自 rules/exemptions.json
- 值归一化后按 value_type 比较；显示模板对齐 golden（赋值对比-T19NGvs启源Q05）
"""
from __future__ import annotations
import re

MORE, LESS, SAME, EXEMPT, NA = "多", "少", "同", "豁免", "不计"

# BACKUP 表多/少栏的项目排序（pjy deck 风格，可在规则中调整）
BACKUP_MORE_ORDER = [1, 3, 40, 23, 21, 9, 37, 27, 33, 30]
BACKUP_LESS_ORDER = [6, 18, 5, 4, 15, 16, 19, 38, 33, 36, 29]


# ---------- 小工具 ----------

def _strip_dot(v) -> str:
    if not isinstance(v, str):
        return v
    return re.sub(r"^[●○]\s*", "", v.strip())


def _num(v, default=None):
    m = re.search(r"[\d.]+", str(v))
    return float(m.group(0)) if m else default


def _is_pending(v) -> bool:
    if isinstance(v, dict):
        return any(_is_pending(value) for value in v.values())
    return isinstance(v, str) and ("[待定]" in v or v.strip() == "?")


def _is_optional(v) -> bool:
    return isinstance(v, str) and (v.startswith("○") or "(选装)" in v or "○" in v)


def _has(v) -> bool:
    """●才算有；○(选装)不算有（豁免规则 optional_not_have）"""
    if not isinstance(v, str):
        return False
    v = v.strip()
    if v.startswith("○"):
        return False
    if v in ("✕", "-", "", "无"):
        return False
    return True


def _plain(v) -> bool:
    return isinstance(v, str) and v.strip() in ("✕", "-", "", "无")


# ---------- 各 value_type 比较器：返回 (verdict, self_short, comp_short) ----------

def cmp_bool(sv, cv, **kw):
    s, c = _has(sv), _has(cv)
    if s and not c:
        return MORE, _short_bool(sv), _short_bool(cv)
    if c and not s:
        return LESS, _short_bool(sv), _short_bool(cv)
    return SAME, _short_bool(sv), _short_bool(cv)


def _short_bool(v):
    v = str(v)
    if _has(v):
        s = _strip_dot(v)
        if s.startswith("(") and s.endswith(")"):
            return "●" + s[1:-1].replace("位置", "")    # ●(带位置记忆) → ●带记忆
        return s if s else "●"
    if _is_optional(v):
        return "○选装"
    return "✕"


def cmp_num(sv, cv, unit="", **kw):
    s, c = _num(sv), _num(cv)
    if s is None and c is None:
        return SAME, _strip_dot(sv) or "✕", _strip_dot(cv) or "✕"
    if s is None:
        return LESS, "✕", _fmt_num(c, unit)
    if c is None:
        return MORE, _fmt_num(s, unit), "✕"
    if s > c:
        return MORE, _fmt_num(s, unit), _fmt_num(c, unit)
    if s < c:
        return LESS, _fmt_num(s, unit), _fmt_num(c, unit)
    return SAME, _fmt_num(s, unit), _fmt_num(c, unit)


def _fmt_num(x, unit=""):
    s = f"{x:g}"
    return s + unit if unit else s


def cmp_rank(order, no=None):
    """按枚举顺序表比较（越大越好，order 从弱到强）；显示串走 _short_generic"""
    def f(sv, cv, **kw):
        si, ci = _rank_of(sv, order), _rank_of(cv, order)
        ss, cs = _short_generic(no, sv), _short_generic(no, cv)
        if si > ci:
            return MORE, ss, cs
        if si < ci:
            return LESS, ss, cs
        return SAME, ss, cs
    return f


def _rank_of(v, order):
    s = _strip_dot(v)
    best = -1
    for i, name in enumerate(order):
        if name and name in s:
            best = max(best, i)
    if best >= 0:
        return best
    return 0 if _has(v) else -1


def cmp_tire(sv, cv, **kw):
    def parse(v):
        s = _strip_dot(v)
        m = re.search(r"R(\d+)", s)
        r = int(m.group(1)) if m else 0
        mat = 1 if "铝" in s else (0 if "钢" in s else -1)
        return (r, mat) if r else None
    sp, cp = parse(sv), parse(cv)
    ss = re.sub(r"轮毂$", "", _strip_dot(sv))
    cs = _strip_dot(cv)
    if sp and cp:
        if sp > cp:
            return MORE, ss, cs
        if sp < cp:
            return LESS, ss, cs
        return SAME, ss, cs
    return cmp_bool(sv, cv)


def cmp_mirror(sv, cv, **kw):
    def feats(v):
        s = _strip_dot(v)
        if "三项全" in s:
            return {"电调", "折叠", "加热"}
        return {f for f in ("电调", "折叠", "加热") if f in s}
    sf, cf = feats(sv), feats(cv)
    ss = "电调折叠加热" if sf == {"电调", "折叠", "加热"} else "+".join(
        f for f in ("电调", "折叠", "加热") if f in sf) or "✕"
    cs = "同" if cf == sf else "+".join(f for f in ("电调", "折叠", "加热") if f in cf) or "✕"
    if sf > cf:
        return MORE, ss, cs
    if sf < cf:
        return LESS, ss, cs
    return SAME, ss, cs


def cmp_wireless(sv, cv, **kw):
    def rank(v):
        s = _strip_dot(v)
        if not _has(v):
            return 0, s or "✕"
        if "双" in s:
            return 2, "前排双50W"
        pw = re.search(r"(\d+)W", s)
        return 1, f"前排{pw.group(1) if pw else ''}50W".replace("50W50W", "50W") if not pw else f"前排{pw.group(1)}W"
    sr, ss = rank(sv)
    cr, cs = rank(cv)
    # 显示对齐 golden：单50W → 「单50W」/「前排50W」
    cs_d = "单50W" if cr == 1 else cs
    if sr > cr:
        return MORE, ss, cs_d
    if sr < cr:
        # 少侧 comp 显示保留原值（前排50W）
        return LESS, ss or "✕", cs
    return SAME, ss, cs_d


def cmp_speaker_ext(sv, cv, **kw):
    """#38 车外扬声器：自方可能只有●无数量，对方有数量 → ● vs ≥1 视为同"""
    s_has, c_has = _has(sv), _has(cv)
    c_n = _num(cv)
    if s_has and (c_has or (c_n or 0) >= 1):
        return SAME, "●", _fmt_num(c_n) if c_n is not None else _strip_dot(cv)
    if not s_has and ((c_n or 0) >= 1 or c_has):
        return LESS, "✕", _fmt_num(c_n) if c_n is not None else _strip_dot(cv)
    if s_has and not c_has:
        return MORE, "●", "✕"
    return SAME, "✕", "✕"


def cmp_cluster(sv, cv, **kw):
    def parse(v):
        s = _strip_dot(str(v))
        size = _num(s) or 0
        full = 1 if "全液晶" in s and "○" not in s.split("全液晶")[0][-1:] else 0
        if "○全液晶" in str(v) or "(○全液晶选装)" in str(v):
            full = 0    # 对方仅选装全液晶 → 不计为有
        return size, full
    s_size, s_full = parse(sv)
    c_size, c_full = parse(cv)
    if s_size == 0 and c_size == 0:
        return cmp_bool(sv, cv)
    s_short = f"{s_size:g}寸" if s_size else "✕"
    c_short = (f"全液晶{c_size:g}" if c_full else f"{c_size:g}寸") if c_size else "✕"
    if (s_size, s_full) > (c_size, c_full):
        return MORE, s_short, c_short
    if (s_size, s_full) < (c_size, c_full):
        return LESS, s_short, c_short
    return SAME, s_short, c_short


# ---------- #36 座椅功能 ----------

def cmp_seat36(sv, cv, comp_sub_vals=None, **kw):
    from .seat_functions import SUBS, PRICES, normalize
    s = normalize(sv)
    c = normalize(cv)
    if comp_sub_vals:
        c.update(normalize(comp_sub_vals) if any(k in comp_sub_vals for k in SUBS) else {})
    more, less, unknown = [], [], []
    for key in SUBS:
        left, right = str(s[key]), str(c[key])
        if '[待定]' in left or '[待定]' in right:
            unknown.append(key)
        elif left == '●' and right != '●':
            more.append(key)
        elif right == '●' and left != '●':
            less.append(key)
    amount = sum(PRICES[next(f for f in PRICES if k.endswith(f))] for k in more) - \
             sum(PRICES[next(f for f in PRICES if k.endswith(f))] for k in less)
    verdict = MORE if amount > 0 else LESS if amount < 0 else SAME
    detail = '；'.join(part for part in (
        '本品多：'+'、'.join(more) if more else '',
        '本品少：'+'、'.join(less) if less else '',
        '待核对：'+'、'.join(unknown) if unknown else '',
    ) if part) or '配置相同'
    display = f'{verdict} {detail}'
    def summary(keys):
        grouped={seat:[] for seat in ('前排','主驾','副驾','二排')}
        for feature in PRICES:
            seats=[seat for seat in ('主驾','副驾','二排') if seat+feature in keys]
            if seats[:2] == ['主驾','副驾']:
                grouped['前排'].append(feature); seats=seats[2:]
            for seat in seats:
                grouped[seat].append(feature)
        return '、'.join(seat+'座椅'+''.join(features) for seat,features in grouped.items() if features)
    backup = summary(more if verdict == MORE else less) if amount else ''
    return verdict, display, backup


# ---------- 主流程 ----------

def _pair_values(self_ladder, comp_ladder, no, si, ci):
    sit = self_ladder.item(no)
    cit = comp_ladder.item(no)
    sv = sit.values[si] if sit and si < len(sit.values) else "✕"
    cv = cit.values[ci] if cit and ci < len(cit.values) else "✕"
    if no == 32:
        from .usb import usb_label
        sv, cv = usb_label(sv), usb_label(cv)
    comp_sub_vals = {}
    if cit:
        for sr in cit.subs or []:
            comp_sub_vals[sr["sub"]] = sr["values"][ci] if ci < len(sr["values"]) else "✕"
    return sv, cv, cit, comp_sub_vals


def diff(self_ladder, comp_ladder, pairs, rules):
    """pairs: [{"self_trim":名,"comp_trim":名}]；返回 DiffResult 用 dict 列表"""
    self_trims = [t["name"] for t in self_ladder.trims]
    comp_trims = [t["name"] for t in comp_ladder.trims]
    cells = []
    range_bands = rules.range_bands()

    def band(km):
        for i, (lo, hi) in enumerate(range_bands):
            if lo <= km <= hi:
                return i
        return len(range_bands)

    def find_trim(names, target):
        """版型名容错匹配：精确 / ±尾缀「版」"""
        if target in names:
            return names.index(target)
        for cand in (target + "版", target.rstrip("版")):
            if cand and cand in names:
                return names.index(cand)
        raise ValueError(f"版型不存在: {target}（可用: {names}）")

    for pi, pair in enumerate(pairs):
        si = find_trim(self_trims, pair["self_trim"])
        ci = find_trim(comp_trims, pair["comp_trim"])
        for item in rules.items:
            no = item["no"]
            sv, cv, cit, comp_subs = _pair_values(self_ladder, comp_ladder, no, si, ci)
            screen_optional = ''
            if no in (21, 22, 29):
                from .screen_config import normalize_screen
                sv, cv = normalize_screen(sv, no), normalize_screen(cv, no)
                if str(sv).startswith('○'):
                    screen_optional += ' 左侧选装按无配置计'
                    sv = '✕'
                if str(cv).startswith('○'):
                    screen_optional += ' 右侧选装按无配置计'
                    cv = '✕'
            if no == 9:
                sv, cv = normalize_adas(sv), normalize_adas(cv)
            comp_absent = bool(cit and cit.row_absent)
            verdict = disp = exempt = ""
            backup_more = backup_less = ""
            core = ""

            from .powertrain import not_applicable
            range_excluded = no == 1 and (
                not_applicable(self_ladder.trims[si].get('energy_type', ''), no)
                or not_applicable(comp_ladder.trims[ci].get('energy_type', ''), no))
            if range_excluded or sv == '不适用' or cv == '不适用':
                cells.append(_cell(no, pi, NA, '不计(动力类型不适用)', sv, cv, 'not_applicable', '', ''))
                continue

            # ---- 全局豁免：待定 ----
            if no != 36 and (_is_pending(sv) or _is_pending(cv)):
                verdict, exempt = NA, "pending"
                comp_core = _strip_dot(cv) if not _plain(cv) else "✕"
                disp = f"不计(待定vs{comp_core})" if pi == 0 else "不计(待定)"
                cells.append(_cell(no, pi, verdict, disp, sv, cv, exempt, "", ""))
                continue

            # ---- #24 车载KTV 豁免 ----
            if no == 24:
                verdict, exempt = EXEMPT, "ktv"
                disp = f"豁免 {_short_bool(sv)}({_short_bool(cv)})" if pi == 0 else "豁免"
                cells.append(_cell(no, pi, verdict, disp, sv, cv, exempt, "", ""))
                continue

            # ---- #31 内后视镜：手动防眩目默认双方●，只比流媒体 ----
            if no == 31:
                s_media, c_media = "流媒体" in str(sv), "流媒体" in str(cv)
                if s_media == c_media:
                    verdict, exempt = SAME, "rearview_manual"
                    disp = "同 手动防眩目(同)" if not s_media else "同 流媒体(流媒体)"
                elif s_media:
                    verdict = MORE
                    disp = "多 流媒体(手动防眩目)"
                else:
                    verdict = LESS
                    disp = "少 手动防眩目(流媒体)"
                cells.append(_cell(no, pi, verdict, disp, sv, cv, exempt, "", ""))
                continue

            # ---- #1 续航：微差豁免（band）----
            if no == 1:
                s_km, c_km = _num(sv), _num(cv)
                if s_km is not None and c_km is not None:
                    if band(s_km) == band(c_km):
                        verdict, exempt = EXEMPT, "range_micro"
                        disp = f"豁免(微差{s_km:g}/{c_km:g})"
                        cells.append(_cell(no, pi, verdict, disp, sv, cv, exempt, "", ""))
                        continue
                    verdict = MORE if s_km > c_km else LESS
                    disp = f"{verdict} {s_km:g}({c_km:g})"
                    bk = f"{s_km:g}km({c_km:g})"
                    backup_more, backup_less = (bk, "") if verdict == MORE else ("", bk)
                    cells.append(_cell(no, pi, verdict, disp, sv, cv, "", backup_more, backup_less))
                    continue

            # ---- #36 座椅功能 ----
            if no == 12:
                def front(value):
                    if not _has(value): return 0, '✕'
                    if '手动' in str(value): return 500, '手动前备箱'
                    if '电动' in str(value) or str(value) == '●': return 1000, '电动前备箱'
                    return None, '[待定]前备箱开启方式'
                s_cost, ss = front(sv)
                c_cost, cs = front(cv)
                if s_cost is None or c_cost is None:
                    cells.append(_cell(no, pi, NA, '不计(请确认前备箱开启方式)', sv, cv, 'pending', '', ''))
                    continue
                verdict = MORE if s_cost > c_cost else LESS if s_cost < c_cost else SAME
                label = f'{ss}({cs})' if s_cost and c_cost else ss if s_cost else cs
                cells.append(_cell(no, pi, verdict, f'{verdict} {label}', sv, cv, '',
                                   label if verdict == MORE else '', label if verdict == LESS else ''))
                continue

            if no == 36:
                verdict, disp, backup = cmp_seat36(sv, cv, comp_subs)
                backup_more, backup_less = (backup, "") if verdict == MORE else (("", backup) if verdict == LESS else ("", ""))
                cells.append(_cell(no, pi, verdict, disp, sv, cv, "", backup_more, backup_less))
                continue

            # ---- 通用 value_type 分派 ----
            vt = item.get("value_type", "bool")
            if vt in ("bool", "bool_memo", "trunk") or item.get("normalize") in ("bool", "trunk"):
                v, ss, cs = cmp_bool(sv, cv)
            elif vt == "airbag_count":
                v, ss, cs = cmp_num(_num(sv, 0), _num(cv, 0))
            elif vt == "speaker_count":
                if no == 38:
                    v, ss, cs = cmp_speaker_ext(sv, cv)
                else:
                    v, ss, cs = cmp_num(_strip_dot(sv), _strip_dot(cv))
            elif vt == "tire":
                v, ss, cs = cmp_tire(sv, cv)
            elif vt == "adas_enum":
                v, ss, cs = cmp_rank(item.get("enum_order", []), no=no)(sv, cv)
            elif vt == "mirror":
                v, ss, cs = cmp_mirror(sv, cv)
            elif vt == "wireless_charge":
                v, ss, cs = cmp_wireless(sv, cv)
            elif vt == "cluster":
                v, ss, cs = cmp_cluster(sv, cv)
            elif vt == "seat_memory":
                def count(value): return 0 if not _has(value) else 2 if '前排' in str(value) or '主副' in str(value) else 1
                s_count, c_count = count(sv), count(cv)
                v = MORE if s_count > c_count else LESS if s_count < c_count else SAME
                ss, cs = _strip_dot(str(sv)), _strip_dot(str(cv))
            elif vt == "network":
                v, ss, cs = cmp_rank(["4G", "5G"])(sv, cv)
                ss = ss.replace("[暂定]", "暂定")
            elif vt == "material":
                # 皮质=仿皮（pjy 规则）；比较归一，显示保留原文
                sn = str(sv).replace("皮质", "仿皮")
                cn = str(cv).replace("皮质", "仿皮")
                if _strip_dot(sn).replace("●", "") == _strip_dot(cn).replace("●", ""):
                    v, ss, cs = SAME, _strip_dot(sv), _strip_dot(cv)
                else:
                    from .valuer import _default_rule_amount
                    s_cost = _default_rule_amount(no, sn, 'more') if _has(sn) else 0
                    c_cost = _default_rule_amount(no, cn, 'more') if _has(cn) else 0
                    v = MORE if s_cost > c_cost else LESS if s_cost < c_cost else SAME
                    ss, cs = _strip_dot(sv), _strip_dot(cv)
            elif vt in ("screen",):
                s_size, c_size = _num(sv), _num(cv)
                if s_size is None and c_size is None:
                    v, ss, cs = cmp_bool(sv, cv)
                else:
                    mopt = re.search(r"○([\d.]+)", str(cv))
                    cs = (f"{c_size:g}" + (f",○{mopt.group(1)}选装" if mopt else "")) \
                        if c_size is not None else "✕"
                    ss = f"{s_size:g}" if s_size is not None else "✕"
                    if (s_size or 0) > (c_size or 0):
                        v = MORE
                    elif (s_size or 0) < (c_size or 0):
                        v = LESS
                    else:
                        v = SAME
            elif vt == "range_km":
                v, ss, cs = cmp_num(_strip_dot(sv), _strip_dot(cv), "km")
            elif vt in ("camera", "lidar", "v2l", "sunroof", "suspend", "hud", "ambient", "high_voltage", "lamp", "seat_adjust", "rearview", "usb", "text", "enum_text"):
                v, ss, cs = _cmp_generic(no, item, sv, cv)
            else:
                v, ss, cs = cmp_bool(sv, cv)

            verdict = v
            # ○选装注记：对方仅○ → 按无比较但显示注记
            disp = f"{verdict} {ss}({cs})"
            if screen_optional:
                disp += screen_optional
            # BACKUP 显示串
            bm, bl = _backup_display(no, verdict, sv, cv, ss, cs, item['name'])
            backup_more, backup_less = bm, bl
            cells.append(_cell(no, pi, verdict, disp, sv, cv, "", backup_more, backup_less))
    return cells


def _cell(no, pi, verdict, disp, sv, cv, exempt, bm, bl):
    return {"no": no, "pair": pi, "verdict": verdict, "display": disp,
            "self_val": sv if isinstance(sv, str) else str(sv),
            "comp_val": cv if isinstance(cv, str) else str(cv),
            "exempt_id": exempt, "backup_more": bm, "backup_less": bl}


_RANKS = {
    6: ["软硬调节", "空气悬架", "魔毯"],       # 可变悬架
    7: ["360", "540"],                          # 影像
    17: ["卤素", "氙气", "LED", "LCD"],          # 灯光（LED<LCD 按 pjy 规则 LCD 更高？保守同档处理）
    30: ["HUD", "AR-HUD", "P-HUD"],
    39: ["单色", "多色"],
    26: ["手动", "电调", "电动"],
    35: ["手调", "电调"],
}


def normalize_adas(value):
    if _is_pending(value) or _is_optional(value):
        return value
    text = re.sub(r'无\s*L2|非\s*L2|不支持\s*L2', '', str(value), flags=re.I)
    for token, label in [('城市', '城市NOA'), ('高速', '高速NOA'), ('L2', '基础L2'), ('自适应巡航', '基础L2'), ('定速', '定速巡航')]:
        if token.lower() in text.lower():
            return label
    return value


def ambient_level(value):
    if not _has(value):
        return 0
    text = str(value)
    count = re.search(r'(\d+)\s*色', text)
    if '多色' in text or (count and int(count[1]) > 1):
        return 2
    return 1


def _cmp_generic(no, item, sv, cv):
    """带枚举序的通用比较；返回 (verdict, self_short, comp_short)"""
    if no == 18:
        from .valuer import _default_rule_amount
        s = _default_rule_amount(no, str(sv), 'more') if _has(sv) else 0
        c = _default_rule_amount(no, str(cv), 'more') if _has(cv) else 0
        return (MORE if s > c else LESS if s < c else SAME), _short_generic(no, sv), _short_generic(no, cv)
    if no == 39:
        s, c = ambient_level(sv), ambient_level(cv)
        labels = ['✕', '单色', '多色']
        return (MORE if s > c else LESS if s < c else SAME), labels[s], labels[c]
    order = _RANKS.get(no)
    ss, cs = _short_generic(no, sv), _short_generic(no, cv)
    if order:
        si = _rank_of2(sv, order)
        ci = _rank_of2(cv, order)
        # ○选装不计为有
        if not _has(sv):
            si = -1 if _plain(sv) else -1
        if not _has(cv):
            ci = -1
        if _is_optional(cv) and not _has(cv):
            ci = -1
        if si > ci:
            return MORE, ss, cs
        if si < ci:
            return LESS, ss, cs
        return SAME, ss, cs
    # 数值型（v2l 功率、lidar 颗数、usb 总数、camera 已由 rank 处理）
    if no == 8:
        s_n = 0 if not _has(sv) else (_num(sv, 0) or 1)
        c_n = 0 if not _has(cv) else (_num(cv, 0) or 1)
        if s_n == c_n:
            return SAME, ss, cs
        return (MORE if s_n > c_n else LESS), ss, cs
    if no == 16:
        # An omitted power rating is not evidence of a lower specification.
        if _has(sv) and _has(cv) and (_num(sv) is None or _num(cv) is None):
            return SAME, ss, cs
        s_n = 0 if not _has(sv) else (_num(sv, 0) or 1)
        c_n = 0 if not _has(cv) else (_num(cv, 0) or 1)
        if s_n == c_n:
            return SAME, ss, cs
        return (MORE if s_n > c_n else LESS), ss, cs
    if no == 32:
        from .usb import usb_total
        s_n, c_n = usb_total(sv), usb_total(cv)
        if s_n is None or c_n is None:
            return SAME, ss, cs
        if s_n == c_n:
            return SAME, ss, cs
        return (MORE if s_n > c_n else LESS), ss, cs
    # 布尔类兜底：判定用 ●/○ 语义，显示用 _short_generic
    s_h, c_h = _has(sv), _has(cv)
    v = MORE if (s_h and not c_h) else LESS if (c_h and not s_h) else SAME
    return v, ss, cs


def _rank_of2(v, order):
    s = _strip_dot(str(v))
    best = -1
    for i, name in enumerate(order):
        if name in s:
            best = i
    if best >= 0:
        return best
    return -1 if _plain(v) or not _has(v) else 0


def _short_generic(no, v):
    s = _strip_dot(str(v))
    if not _has(v):
        if _is_optional(v):
            return "○选装"
        return "✕" if s in ("", "✕") or not _has(v) else s
    if no == 6:
        core = s.replace("悬架", "") if "软硬" in s else s
        return f"{core}●"
    if no == 7:
        return s.replace("影像", "")
    if no == 8:
        return "●" + s.replace("(", "").replace(")", "")
    if no == 16:
        return re.sub(r"^●", "", s)
    if no == 17:
        return s.replace("大灯", "")
    if no == 18:
        return f"{s}●"
    if no == 30:
        return "●"
    if no == 39:
        m = re.search(r"(\d+)色", s)
        return f"{m.group(1)}色" if m else s
    if no == 26:
        return s.replace("调", "") if s in ("手动调", "电调") else s
    if no == 35:
        if re.search(r'(?:主驾|副驾)\d+向', s):
            return s
        m = re.search(r"主(\d+)向.*?副(\d+)向", s)
        if m:
            return f"主{m.group(1)}副{m.group(2)}电调"
        return "主副电调" if "电调" in s else "主副手调"
    if no == 9:
        # 基础L2(○天枢领航激光版选装) → 基础L2,○激光版
        m = re.match(r"(.*?)[（(]○(.+?)选装[)）]", s)
        if m:
            sysname = m.group(2).replace("天枢领航", "") or "激光版"
            return f"{m.group(1)},○{sysname}"
        return s
    return s if s else "●"


# ---------- BACKUP 显示模板 ----------

def _backup_display(no, verdict, sv, cv, ss, cs, name=''):
    """返回 (backup_more, backup_less)；非多/少为空串"""
    if verdict not in (MORE, LESS):
        return "", ""
    # A one-sided difference names only the equipment that exists.
    if not _has(sv) and _has(cv):
        out, _ = _backup_display(no, MORE, cv, '✕', cs, '✕', name)
        return (out, '') if verdict == MORE else ('', out)
    s, c = _strip_dot(str(sv) if sv is not None else '✕'), _strip_dot(str(cv) if cv is not None else '✕')
    def number(value):
        n = _num(value)
        return f'{n:g}' if n is not None else '✕'
    out = ""
    if no == 3:
        out = f'{s}({c})' if _has(cv) else s
    elif no == 40:
        out = "热泵空调"
    elif no == 27:
        out = "方向盘加热"
    elif no == 26:
        if not _has(sv) or not _has(cv):
            value = c if verdict == LESS else s
            out = '方向盘电调' if '电' in value else '方向盘手动调节'
        else:
            out = f"方向盘调节：{ss}({cs})"
    elif no == 39:
        out = f"{ss}氛围灯({cs})" if _has(sv) and _has(cv) else f"{cs if verdict == LESS else ss}氛围灯"
    elif no == 30:
        out = f'{s}({c})' if _has(cv) else s
    elif no == 23:
        sv2 = s.replace("[暂定]", "").replace("暂定", "")
        cv2 = c if c not in ("✕", "") else ""
        out = f"{sv2}车联网({cv2})" if cv2 else f"{sv2}车联网"
    elif no == 21:
        out = f"{number(sv)}中控({number(cv)})"
    elif no == 9:
        # Keep both sides: valuation also reads this description.
        # In particular, absence vs cruise control must not collapse to ✕.
        out = f"{ss}({cs})" if cs not in ("✕", "") else ss
    elif no == 37:
        out = f"{number(sv)}扬({number(cv)})" if _num(cv) is not None else f"{number(sv)}扬"
    elif no == 33:
        def charging(value):
            power = re.search(r"(\d+(?:\.\d+)?)\s*W", value, re.I)
            watts = f"{float(power[1]):g}W" if power else ""
            return f"前排{'双' if '双' in value else '单'}{watts}无线充电"
        out = f'{charging(s)}({charging(c)})' if _has(cv) else charging(s)
    elif no == 32:
        from .usb import usb_label
        out = f'{usb_label(sv)}（{usb_label(cv)}）'
    elif no == 5:
        out = f"{number(sv)}气囊({number(cv)})"
    elif no == 4:
        out = f"{s}({c})"
    elif no == 6:
        def suspension(value):
            return value if '悬架' in value else '悬架'+value if value else '可变悬架'
        out = f'{suspension(s)}({suspension(c)})' if _has(cv) else suspension(s)
    elif no == 18:
        def roof(value):
            return value if '天窗' in value or '天幕' in value else value+'天窗'
        out = f'{roof(s)}({roof(c)})' if _has(cv) else roof(s)
    elif no == 15:
        out = "主动闭合式进气格栅"
    elif no == 16:
        def discharge(value):
            pw = _num(value)
            return f'对外放电{pw:g}kW' if pw else '对外放电'
        out = f'{discharge(sv)}({discharge(cv)})' if _has(cv) else discharge(sv)
    elif no == 19:
        out = "后雨刷"
    elif no == 38:
        def speaker(value):
            n = _num(value)
            return f'{n:g}个车外扬声器' if n else '车外扬声器'
        out = f'{speaker(s)}({speaker(c)})' if _has(cv) else speaker(s)
    elif no == 29:
        # ○全液晶选装 不算全液晶（选装○不计为有）
        c_full = ("全液晶" in c) and not re.search(r"○\s*全液晶", str(cv))
        c_size = _num(cv)
        cdisp = (f"全液晶{c_size:g}" if c_full else f"{c_size:g}") if c_size else c
        out = f"{number(sv)}仪表({cdisp})"
    elif no == 1:
        out = f"{number(sv)}km({number(cv)})" if _num(cv) is not None else f"{number(sv)}km"
    else:
        out = f"{ss}({cs})" if cs not in ("✕", "") else ss
    if not _has(cv):
        out = re.sub(r'[（(](?:✕|×|0个)[)）]', '', out)
    # A generic boolean comparator uses ● for “有”.  Never let that marker
    # escape into the P21 summary as a standalone bullet.
    if re.fullmatch(r'[●✕×○\s()（）]*', out):
        labels = {
            11: "电动吸合门", 12: "电动前备箱", 13: "电动后备箱", 14: "车顶行李架",
            15: "主动闭合式进气格栅", 22: "副驾娱乐屏", 27: "方向盘加热",
            28: "方向盘记忆", 30: "HUD", 41: "后排出风口",
        }
        out = name or labels.get(no, f"配置项{no}")
    return (out, "") if verdict == MORE else ("", out)


def _merge_seat_labels(labels):
    """Combine display labels only; valuation keeps the original item mapping."""
    grouped = {}
    pattern = r'(前排|主驾|副驾|二排)座椅((?:通风|加热|记忆|按摩|头枕音响)+)'
    for label in labels:
        for part in label.split('、'):
            match = re.fullmatch(pattern, part)
            if match:
                grouped.setdefault(match[1], set()).update(re.findall(r'通风|加热|记忆|按摩|头枕音响', match[2]))
    result, emitted = [], set()
    for label in labels:
        parts = []
        for part in label.split('、'):
            match = re.fullmatch(pattern, part)
            if not match:
                parts.append(part)
            elif match[1] not in emitted:
                seat = match[1]
                parts.append(seat+'座椅'+''.join(f for f in ('通风','加热','记忆','按摩','头枕音响') if f in grouped[seat]))
                emitted.add(seat)
        if parts:
            result.append('、'.join(parts))
    return result


def assemble_backup(cells, pairs, self_model, comp_model, self_prices, comp_prices,
                    valuation=None):
    """按 BACKUP_MORE/LESS_ORDER 汇总每组的多/少栏；valuation 为 None 时金额行占位"""
    groups = []
    for pi, pair in enumerate(pairs):
        more, less = [], []
        more_map, less_map = {}, {}
        for c in cells:
            if c["pair"] != pi:
                continue
            if c["verdict"] == MORE and c["backup_more"]:
                more_map[c["no"]] = c["backup_more"]
            elif c["verdict"] == LESS and c["backup_less"]:
                less_map[c["no"]] = c["backup_less"]
        for no in BACKUP_MORE_ORDER + [n for n in sorted(more_map) if n not in BACKUP_MORE_ORDER]:
            if no in more_map:
                more.append(more_map[no])
        for no in BACKUP_LESS_ORDER + [n for n in sorted(less_map) if n not in BACKUP_LESS_ORDER]:
            if no in less_map:
                less.append(less_map[no])
        g = {"pair": pair, "more": _merge_seat_labels(more), "less": _merge_seat_labels(less),
             "more_items": [n for n in more_map], "less_items": [n for n in less_map]}
        sp, cp = self_prices.get(pair["self_trim"]), comp_prices.get(pair["comp_trim"])
        g["self_price"], g["comp_price"] = sp, cp
        if valuation is not None:
            from .valuer import value_pair
            g["valuation"] = value_pair(more_map, less_map, sp, cp, valuation)
        else:
            g["valuation"] = {"config_adv": None, "flat_adv": None, "overall": None,
                              "missing": sorted(set(list(more_map) + list(less_map)))}
        groups.append(g)
    return groups
