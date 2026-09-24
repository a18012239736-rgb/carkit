"""render_backup — DiffResult → deck BACKUP 页表格式 md（对齐 golden 输出）"""
from __future__ import annotations
import datetime
from .rules import display_order_key

VERDICT_MARK = {"多": "**多**", "少": "**少**", "同": "同", "豁免": "豁免", "不计": "不计"}


def _fmt_price(p):
    return f"{p:g}" if p is not None else "?"


def render_md(self_model, comp_model, groups, cells, rules_version="v1",
              checklist="v1", date=None, notes=None, pair_labels=None):
    date = date or datetime.date.today().isoformat()
    lines = []
    lines.append(f"# 赋值对比：{self_model} vs {comp_model}（{date}）")
    lines.append("")
    lines.append(f"- 配对：使用者指定（程序绝不自动配对）")
    lines.append(f"- 规则：对比配置清单 {checklist} / 豁免规则 {rules_version}（carkit engine 生成）")
    lines.append("")
    lines.append("## 竞争力对比表（deck BACKUP 格式）")
    lines.append("")
    n = len(groups)
    header = "|  | " + " | ".join(
        f"{self_model} {_fmt_price(g['self_price'])} VS {comp_model} {_fmt_price(g['comp_price'])}"
        for g in groups) + " |"
    lines.append(header)
    lines.append("| ---" * (n + 1) + " |")
    lines.append("| 版型 | " + " | ".join(
        f"{g['pair']['self_trim']} vs {g['pair']['comp_trim']}" for g in groups) + " |")
    lines.append(f"| {self_model}多 | " + " | ".join("<br>".join(g["more"]) or "—" for g in groups) + " |")
    lines.append(f"| {self_model}少 | " + " | ".join("<br>".join(g["less"]) or "—" for g in groups) + " |")

    def money_row(key, label):
        row = []
        for g in groups:
            v = g.get("valuation") or {}
            val = v.get(key)
            row.append("待赋值明细表" if val is None else f"{val:g}")
        lines.append(f"| {label} | " + " | ".join(row) + " |")

    money_row("config_adv", "配置优势")
    money_row("flat_adv", "拉平指导价优势")
    money_row("overall", "综合竞争力")
    lines.append("")
    if notes:
        for nt in notes:
            lines.append(f"> {nt}")
        lines.append("")

    lines.append("## 附：配置项判定明细（追溯用）")
    lines.append("")
    plabels = pair_labels or [f"{g['pair']['self_trim']}vs{g['pair']['comp_trim']}" for g in groups]
    lines.append("| # | 配置项 | " + " | ".join(plabels) + " |")
    lines.append("|---" * (len(plabels) + 2) + "|")
    # 按项号分组渲染
    nos = sorted({c["no"] for c in cells}, key=display_order_key)
    item_names = {c["no"]: c.get("name", "") for c in cells}
    for serial, no in enumerate(nos, 1):
        row_cells = [c for c in cells if c["no"] == no]
        row_cells.sort(key=lambda c: c["pair"])
        name = item_names.get(no) or str(no)
        disp_cells = []
        for c in row_cells:
            d = c["display"]
            # 判定词加粗对齐 golden：**多** / **少**
            for v in ("多", "少"):
                if d.startswith(v + " "):
                    d = f"**{v}** " + d[len(v) + 1:]
                    break
            disp_cells.append(d)
        lines.append(f"| {serial} | {name} | " + " | ".join(disp_cells) + " |")
    lines.append("")
    lines.append("> 由 carkit engine 生成；判定词：多/少/同/豁免/不计；豁免规则见 rules/exemptions.json。")
    return "\n".join(lines) + "\n"
