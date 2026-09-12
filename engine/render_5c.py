"""render_5c — RawTable → 5C 五段制 md（模板化渲染）

五段制（零跑A10 范本）：
1. 开头一句话定位
2. 版型与价格：树状 list（续航→版型）+ 价格表
3. 配置：基本配置段（最低配全量）+ 若干「较X +Y万:(Y版)」升档段（双列增减）
4. 选装：段尾 > 引用块

写法禁令（程序硬编码遵守）：无 emoji、无 ●/○ 符号、无「增项/减项」小标题、
增项不加括号（括号只在比较对象有明确值时用）、升档段必须双列增减项。
本机 Claude 工作流可拿 engine 数据自行灵活措辞；exe 内用本模板。
"""
from __future__ import annotations
import datetime
import re

# 5C 输出跳过的行（价格/参数表头类）
SKIP_ROWS = {"厂商指导价(元)", "经销商报价", "厂商", "上市时间", "外观颜色", "内饰颜色"}


def _val_text(cell) -> str:
    """cell → 纯文本值（去符号；无值返回空）"""
    if cell is None:
        return ""
    if cell.dot == "○":
        return ""      # 选装不进基本配置/升档段
    t = (cell.text or "").strip()
    return t


def _opt_text(cell) -> str:
    if cell is None or cell.dot != "○":
        return ""
    return (cell.text or "").strip() or "选装"


def _fmt_price(p):
    return f"{p:g}" if p is not None else "—"


def render_md(raw, model: str = "", series_id: str = "", date: str = "") -> str:
    model = model or raw.model or "未知车型"
    date = date or datetime.date.today().isoformat()
    trims = sorted(raw.trims, key=lambda t: (t.price_guide is None, t.price_guide or 0))
    n = len(trims)
    lines = []

    # ---- 段1 一句话定位 ----
    level = raw.row("级别")
    body = raw.row("车身结构")
    energy = raw.row("能源类型")
    pos_bits = [ _val_text(level.cells[0]) if level and level.cells else "",
                 _val_text(body.cells[0]) if body and body.cells else "",
                 _val_text(energy.cells[0]) if energy and energy.cells else "" ]
    pos = " ".join(b for b in pos_bits if b)
    lines.append(f"# 5C-看竞争-{model}")
    lines.append("")
    lines.append(f"{model}：{pos or '（定位一句话待人工补充）'}，指导价 "
                 f"{_fmt_price(trims[0].price_guide)}-{_fmt_price(trims[-1].price_guide)} 万，共 {n} 个版型。")

    # ---- 数据源与版本说明 ----
    lines.append("")
    lines.append("## 数据源与版本说明")
    lines.append(f"- 来源：汽车之家主站配置对比页 DOM 抓取（www.autohome.com.cn/config/series/{series_id or raw.series_id}.html）")
    lines.append(f"- 抓取时间：{raw.scraped_at or date}")
    lines.append(f"- 收录范围：{n} 版型（carkit 模板渲染；○=选装进选装段，无行=无）")

    # ---- 段2 版型与价格 ----
    lines.append("")
    lines.append("## 版型与价格")
    lines.append("")
    range_row = next((r for r in raw.rows if "纯电续航里程" in r.name), None)
    if range_row:
        by_range = {}
        for i, t in enumerate(trims):
            # range_row.cells 按原始列序，需要 idx 映射
            cell = range_row.cells[t.idx] if t.idx < len(range_row.cells) else None
            rv = (_val_text(cell) or "?") + "km"
            by_range.setdefault(rv, []).append(t.short)
        for rv, names in by_range.items():
            lines.append(f"- {rv}：{' / '.join(names)}")
    lines.append("")
    lines.append("| 版型 | " + " | ".join(t.short for t in trims) + " |")
    lines.append("|---" * (n + 1) + "|")
    lines.append("| 指导价(万) | " + " | ".join(_fmt_price(t.price_guide) for t in trims) + " |")

    # ---- 段3 配置 ----
    lines.append("")
    lines.append("## 配置")
    lines.append("")

    def col_of(t):
        return t.idx

    base = trims[0]
    lines.append(f"**基本配置（{base.short}）：**")
    lines.append("")
    for r in raw.rows:
        if r.name in SKIP_ROWS:
            continue
        c = r.cells[col_of(base)] if col_of(base) < len(r.cells) else None
        v = _val_text(c)
        if c is not None and c.dot == "●":
            lines.append(f"{r.name}：{v}" if v and v != "●" else r.name)
    # ---- 升档段 ----
    for prev, cur in zip(trims, trims[1:]):
        dp = (cur.price_guide or 0) - (prev.price_guide or 0)
        lines.append("")
        lines.append(f"**较{prev.short} +{dp:g}万:（{cur.short}）**")
        lines.append("")
        adds, dels = [], []
        for r in raw.rows:
            if r.name in SKIP_ROWS:
                continue
            pc = r.cells[col_of(prev)] if col_of(prev) < len(r.cells) else None
            cc = r.cells[col_of(cur)] if col_of(cur) < len(r.cells) else None
            pv, cv = _val_text(pc), _val_text(cc)
            p_has = pc is not None and pc.dot == "●"
            c_has = cc is not None and cc.dot == "●"
            if c_has and not p_has:
                adds.append(f"{r.name}：{cv}" if cv and cv != "●" else r.name)
            elif c_has and p_has and cv != pv and cv and pv:
                adds.append(f"{r.name}：{pv} → {cv}")
            elif p_has and not c_has:
                dels.append(f"{r.name}（{pv}）" if pv and pv != "●" else r.name)
        if adds:
            lines.append("增：" + "；".join(adds))
        if dels:
            lines.append("减：" + "；".join(dels))
        if not adds and not dels:
            lines.append("（配置相同，仅价格/续航差异）")

    # ---- 段4 选装 ----
    opts = []
    for r in raw.rows:
        for i, t in enumerate(trims):
            c = r.cells[col_of(t)] if col_of(t) < len(r.cells) else None
            o = _opt_text(c)
            if o:
                item = f"{r.name}：{o}" if o != "选装" else r.name
                entry = f"{item}（{t.short}）"
                if entry not in opts:
                    opts.append(entry)
    if opts:
        lines.append("")
        lines.append("> 选装：" + "；".join(opts))

    lines.append("")
    return "\n".join(lines) + "\n"
