"""golden 回归：carkit engine 输出 vs 2026-09-11 人工确认的 T19NG vs 启源Q05 对比结果

回归锚点（计划 P0）：
1. compact raw → 竞品阶梯：41项值与 golden 竞品阶梯 md 一致
2. diff 判定词（多/少/同/豁免/不计）40项×3组 100% 命中 golden 判定明细
3. BACKUP 多/少 两栏项目与 golden 完全一致（含顺序与显示串）
显示串允许「人工不一致白名单」内的偏差（golden 本身前后不一致的格子），白名单外零容忍。
"""
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.rules import Rules
from engine import rawschema, ladder as ladder_mod, differ
from engine.models import Snapshot
from engine.snapshot import resolve

GOLDEN = os.path.join(ROOT, "tests", "golden")
PAIRS = [{"self_trim": "基础型", "comp_trim": "405Max"},
         {"self_trim": "舒适型", "comp_trim": "506Max"},
         {"self_trim": "豪华型", "comp_trim": "506激光极智"}]

VERDICTS = ("多", "少", "同", "豁免", "不计")


# ---------- golden md 解析 ----------

def parse_golden_detail(path):
    """解析 41 项判定明细表 → {(no, pair_idx): (verdict, display)}"""
    text = open(path, encoding="utf-8").read()
    sec = text.split("## 附：41 项判定明细")[1]
    out = {}
    for line in sec.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|[^|]+\|(.+)\|\s*$", line)
        if not m:
            continue
        no = int(m.group(1))
        cols = [c.strip() for c in m.group(2).strip().strip("|").split("|")]
        for pi, col in enumerate(cols[:3]):
            out[(no, pi)] = _verdict_display(col, out.get((no, pi - 1)))
    return out


def _verdict_display(cell, prev):
    c = cell.replace("**", "").strip()
    for v in VERDICTS:
        if c.startswith(v):
            rest = c[len(v):].strip()
            if not rest:        # 裸判定词（人工重复压缩）→ display 记为裸判定词本身
                return v, v
            return v, c
    return "?", c


def parse_golden_backup(path):
    """解析 BACKUP 表 多/少 两行 → [(more_tokens, less_tokens) per group]"""
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    more = less = None
    for line in lines:
        if re.match(r"^\|\s*T19\s*NG多\s*\|", line):
            more = [c.strip() for c in line.strip().strip("|").split("|")[1:]]
        if re.match(r"^\|\s*T19\s*NG少\s*\|", line):
            less = [c.strip() for c in line.strip().strip("|").split("|")[1:]]
    assert more and less, "golden BACKUP 多/少行未找到"
    return [(m.split(), l.split()) for m, l in zip(more, less)]


def parse_golden_ladder(path):
    """解析竞品阶梯 md 41项表 → {no: [values(展开同)]}"""
    text = open(path, encoding="utf-8").read()
    sec = text.split("## 41 项配置阶梯")[1]
    out = {}
    prev = None
    for line in sec.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|[^|]+\|(.+)\|\s*$", line)
        if not m:
            prev = None
            continue
        no = int(m.group(1))
        cols = [c.strip() for c in m.group(2).strip().strip("|").split("|")]
        vals, last = [], None
        for c in cols:
            if c == "同" and last is not None:
                vals.append(last)
            else:
                vals.append(c)
                last = c
        out[no] = vals
        prev = no
    return out


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def rules():
    return Rules()


@pytest.fixture(scope="module")
def comp_ladder(rules):
    raw = rawschema.detect_and_load(
        os.path.join(GOLDEN, "raw-Q05-汽车之家全表-2026-09-11.json"), series_id="8241")
    return ladder_mod.build_ladder(raw, rules, model="启源Q05", series_id="8241",
                                   date="2026-09-11")


@pytest.fixture(scope="module")
def self_ladder(rules):
    snap = resolve(Snapshot.load(os.path.join(GOLDEN, "T19NG-snapshot.json")))
    return snap.to_ladder(rules.checklist["items"])


@pytest.fixture(scope="module")
def diff_cells(rules, self_ladder, comp_ladder):
    return differ.diff(self_ladder, comp_ladder, PAIRS, rules)


# ---------- 测试 ----------

def test_rawschema_both_formats():
    a = rawschema.detect_and_load(os.path.join(GOLDEN, "raw-Q05-汽车之家全表-2026-09-11.json"))
    assert len(a.trims) == 7 and len(a.rows) == 229
    assert a.trims[0].price_guide == 7.99 and a.trims[6].price_guide == 11.49
    assert not a.lossy
    b = rawschema.detect_and_load(os.path.join(GOLDEN, "启源Q05_8241_raw.json"))
    assert b.lossy and len(b.trims) == 7


def test_ladder_matches_golden(rules, comp_ladder):
    golden = parse_golden_ladder(os.path.join(GOLDEN, "竞品阶梯-启源Q05-2026-09-11.md"))
    mismatches = []
    for it in comp_ladder.items:
        g = golden.get(it.no)
        if g is None:
            continue
        mine = it.values
        # 归一比较：✕(无行)≈✕；○软硬调节(选装) 等全串比较
        for i, (mv, gv) in enumerate(zip(mine, g)):
            mv_n = str(mv).replace("✕(无行)", "✕")
            gv_n = str(gv).replace("✕(无行)", "✕").replace("✕(无行,无前备箱)", "✕")
            if mv_n != gv_n:
                mismatches.append((it.no, i, mv_n, gv_n))
    assert not mismatches, f"阶梯值不一致: {mismatches}"


def test_verdicts_100_percent(rules, diff_cells):
    golden = parse_golden_detail(os.path.join(GOLDEN, "赋值对比-T19NGvs启源Q05-2026-09-11.md"))
    mine = {(c["no"], c["pair"]): c["verdict"] for c in diff_cells}
    errors = []
    for key, (gv, gdisp) in golden.items():
        mv = mine.get(key)
        if mv != gv:
            errors.append(f"#{key[0]} 组{key[1]+1}: golden={gv} mine={mv} (golden显示: {gdisp})")
    assert not errors, "判定词不一致:\n" + "\n".join(errors)


# golden 本身人工不一致的显示串（判定词已 100% 校验，此处仅显示格式白名单）
DISPLAY_TOLERANCE = {
    (11, 0): ("同 ✕", "同 ✕(✕)"), (11, 1): ("同 ✕", "同 ✕(✕)"), (11, 2): ("同 ✕", "同 ✕(✕)"),
    (14, 0): ("同 ✕", "同 ✕(✕)"), (14, 1): ("同 ✕", "同 ✕(✕)"), (14, 2): ("同 ✕", "同 ✕(✕)"),
    (22, 0): ("同 ✕", "同 ✕(✕)"), (22, 1): ("同 ✕", "同 ✕(✕)"), (22, 2): ("同 ✕", "同 ✕(✕)"),
    (28, 0): ("同 ✕", "同 ✕(✕)"), (28, 1): ("同 ✕", "同 ✕(✕)"), (28, 2): ("同 ✕", "同 ✕(✕)"),
    (32, 1): ("不计", "不计(待定)"), (32, 2): ("不计", "不计(待定)"),
    (35, 0): ("同 主6副4电调(主副电调)", "同 主6副4电调(副电调)"),
    (35, 1): ("同 主6副4电调(主副电调)", "同(副腿托备注)"),
    (35, 2): ("同 主6副4电调(主副电调)", "同(副腿托备注)"),
    (4, 1): ("同 R18铝(R18铝)", "同 R18铝"),
    (4, 2): ("同 R18铝(R18铝)", "同 R18铝"),
    (20, 0): ("同 电调折叠加热(同)", "同 电调折叠加热(同+锁车折叠)"),
    (20, 1): ("同 电调折叠加热(同)", "同 电调折叠加热(同+锁车折叠)"),
    (20, 2): ("同 电调折叠加热(同)", "同 电调折叠加热(同+锁车折叠)"),
}


def _norm_display(d):
    d = d.replace("**", "").strip()
    d = re.sub(r"同 ✕\(✕\)$", "同 ✕", d)
    d = re.sub(r"^不计\(待定.*\)$", "不计", d)
    return d


def test_displays_match(diff_cells):
    golden = parse_golden_detail(os.path.join(GOLDEN, "赋值对比-T19NGvs启源Q05-2026-09-11.md"))
    diffs = []
    for c in diff_cells:
        key = (c["no"], c["pair"])
        if c['no'] == 36: continue  # 座椅功能已改为逐座位、逐功能；历史展示串不再适用。
        if key not in golden:
            continue
        gv, gdisp = golden[key]
        if gdisp == gv:
            continue    # golden 裸判定词（人工压缩），判定词已单独校验
        md, gd = _norm_display(c["display"]), _norm_display(gdisp)
        if md != gd and key not in DISPLAY_TOLERANCE:
            diffs.append(f"#{key[0]} 组{key[1]+1}: mine=「{c['display']}」 golden=「{gdisp}」")
    assert not diffs, "显示串偏差（白名单外）:\n" + "\n".join(diffs)


def test_backup_rows_match(rules, self_ladder, comp_ladder, diff_cells):
    golden = parse_golden_backup(os.path.join(GOLDEN, "赋值对比-T19NGvs启源Q05-2026-09-11.md"))
    snap = resolve(Snapshot.load(os.path.join(GOLDEN, "T19NG-snapshot.json")))
    self_prices = {t["name"]: t.get("price_guide") for t in snap.trims}
    comp_prices = {t["name"]: t.get("price_guide") for t in comp_ladder.trims}
    groups = differ.assemble_backup(diff_cells, PAIRS, "T19NG", "启源Q05",
                                    self_prices, comp_prices, valuation=None)
    errors = []
    for i, (g, (gm, gl)) in enumerate(zip(groups, golden)):
        # Updated display contract: name the existing configuration alone;
        # keep both configurations when both exist. Historical deck is unchanged.
        labels = {'可变悬架(软硬调节)': '悬架软硬调节',
                  '天窗(不可开启全景)': '不可开启全景天窗',
                  '车外扬声器': '1个车外扬声器',
                  '前排双50W无线充电(单)': '前排双50W无线充电(前排单50W无线充电)'}
        gm, gl = [labels.get(v,v) for v in gm], [labels.get(v,v) for v in gl]
        actual_more = [v for n,v in zip(g['more_items'],g['more']) if n != 36]
        expected_more = [v for v in gm if '座椅' not in v]
        if actual_more != expected_more:
            errors.append(f"组{i+1} 多栏:\n  mine  ={actual_more}\n  golden={expected_more}")
        new_less = {c['backup_less'] for c in diff_cells if c['pair']==i and c['no']>41}
        historical_less = [v for v in g['less'] if '座椅' not in v and v not in new_less]
        expected_less = [v for v in gl if '座椅' not in v]
        if historical_less != expected_less:
            errors.append(f"组{i+1} 少栏:\n  mine  ={historical_less}\n  golden={expected_less}")
    assert not errors, "BACKUP 多/少栏不一致:\n" + "\n".join(errors)


def test_valuation_formula_mechanics():
    """赋值机制单测：flat/拉平公式（金额数值待 pjy 赋值表，公式先行验证）"""
    from engine.models import ValuationTable, ValuationItem
    from engine.valuer import value_pair
    vt = ValuationTable(items=[
        ValuationItem(no=1, name="续航", pricing="flat", val=1000),
        ValuationItem(no=3, name="800V", pricing="flat", val=2000),
    ])
    r = value_pair({1: "500km(405)", 3: "800V"}, {}, 8.99, 9.99, vt)
    assert r["config_adv"] == 3000
    assert r["flat_adv"] == 3000 + (9.99 - 8.99) * 10000    # = 13000
    assert r["overall"] is None                              # 公式未提供 → [待公式]
    # 缺项 → 不脑补
    r2 = value_pair({1: "500km(405)", 9: "城市NOA(高速NOA)"}, {}, 8.99, 8.99, vt)
    assert r2["config_adv"] is None and 9 in r2["missing"]
