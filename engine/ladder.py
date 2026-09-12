"""ladder — RawTable → 竞品阶梯 Ladder（41项×N版型）+ md 渲染"""
from __future__ import annotations
import datetime
from .models import Ladder, LadderItem
from .mapper import map_raw_to_ladder


def _fmt(v) -> str:
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    return str(v)


def build_ladder(raw, rules, model: str = "", date: str = "", series_id: str = "") -> Ladder:
    mapped = map_raw_to_ladder(raw, rules)
    items = []
    for item_cfg in rules.items:
        no = item_cfg["no"]
        m = mapped.get(no, {"values": [], "row_absent": True, "subs": []})
        values = [_fmt(v) for v in m["values"]]
        if item_cfg.get("value_type") == "airbag_count":
            # 气囊：值=「数量(成分)」显示串（如 4(主副+前侧) / 6(+前气帘)），differ 取前导数字比较
            values = _airbag_display(m["values"], m.get("airbag_comps", []))
        name = item_cfg.get("md_name") or item_cfg["name"]
        li = LadderItem(no=no, name=name, values=values,
                        row_absent=m.get("row_absent", False),
                        subs=m.get("subs", []),
                        note=item_cfg.get("fill_rule") or "")
        items.append(li)
    trims = [{"name": t.short, "price_guide": t.price_guide} for t in raw.trims]
    return Ladder(side="competitor", model=model or raw.model,
                  series_id=series_id or raw.series_id,
                  checklist=rules.version,
                  date=date or datetime.date.today().isoformat(),
                  source=f"汽车之家 config/series/{series_id or raw.series_id}.html 现抓",
                  trims=trims, items=items)


def _airbag_display(counts, comps):
    """405Air→'4(主副+前侧)'，下一档→'6(+前气帘)'，同值→'6'"""
    out, prev = [], None
    for cnt, cp in zip(counts, comps):
        if prev is None:
            out.append(f"{cnt}({'+'.join(cp)})" if cp else str(cnt))
        elif cnt == prev[0]:
            out.append(str(cnt))
        else:
            added = [c for c in cp if c not in prev[1]]
            out.append(f"{cnt}(+{'+'.join(added)})" if added else str(cnt))
        prev = (cnt, cp)
    return out


# ---------- md 渲染（对齐 竞品阶梯-启源Q05 golden 格式） ----------

def render_md(ladder: Ladder, title: str = "") -> str:
    lines = []
    model = ladder.model
    lines.append(f"# 竞品配置阶梯-{model}（赋值对比专用 · 41项清单格式）")
    lines.append("")
    lines.append(f"- **来源**：{ladder.source}，{ladder.date}，{len(ladder.trims)}版型")
    lines.append(f"- **格式**：按 `对比配置清单-{ladder.checklist}` 41 项 + pjy 填写规则；`○`=选装；**汽车之家无该配置行 = 没有（✕）**")
    lines.append(f"- 由 carkit engine 生成（rules {ladder.checklist}）")
    lines.append("")
    lines.append("## 版型与价格")
    lines.append("")
    names = [t["name"] for t in ladder.trims]
    lines.append("| 版型 | " + " | ".join(names) + " |")
    lines.append("|---" * (len(names) + 1) + "|")
    prices = [("—" if t.get("price_guide") is None else f"{t['price_guide']:g}") for t in ladder.trims]
    lines.append("| 指导价(万) | " + " | ".join(prices) + " |")
    lines.append("")
    lines.append("## 41 项配置阶梯")
    lines.append("")
    lines.append("| # | 配置项 | " + " | ".join(names) + " |")
    lines.append("|---" * (len(names) + 2) + "|")
    for it in ladder.items:
        display = it.values
        cells, prev = [], None
        for idx, v in enumerate(display):
            v = str(v)
            if idx == 0 and it.row_absent and v == "✕":
                v = "✕(无行)"
            elif prev is not None and v == prev and v != "✕(无行)":
                v = "同"
            cells.append(v)
            prev = str(display[idx])
        lines.append(f"| {it.no} | {it.name} | " + " | ".join(cells) + " |")
        for sr in (it.subs or []):
            sub_cells, prev = [], None
            for idx, v in enumerate(sr["values"]):
                v = str(v)
                if prev is not None and v == prev:
                    v = "同"
                sub_cells.append(v if idx or True else v)
                prev = str(sr["values"][idx])
            lines.append(f"| — | {sr['sub']} | " + " | ".join(sub_cells) + " |")
    lines.append("")
    lines.append("> 由 carkit 生成；○=选装不计为有；无行=没有。")
    return "\n".join(lines) + "\n"
