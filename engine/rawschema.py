"""rawschema — 各种来源的原始抓取数据 → canonical RawTable

支持三种输入：
1. compact：生产级 evaluate JS 输出（双重编码 JSON 字符串，{headers,rowCount,rows:[{n,v[]}]}，
   v 单元格为 "●14.6英寸 | ○15.6英寸" / "-" 文本）——无损，canonical 首选
2. rich：openclaw 旧版 {scraped_at,trimNames,rows:[{name,values:[{dot,text}]}]}（+_grouped 变体）
   ——有损（双子项被压扁），标 lossy=True
3. dict：已经是 canonical RawTable 字典
"""
from __future__ import annotations
import json
import re
from .models import RawTable, RawRow, Cell, Trim

_PRICE_RE = re.compile(r"([\d.]+)\s*万")


def _parse_price(text: str):
    m = _PRICE_RE.search(text or "")
    return float(m.group(1)) if m else None


def _split_compact_cell(v: str) -> Cell:
    """'●14.6英寸 | ○15.6英寸' → Cell(dot=●,text=14.6英寸,subs=[Cell(○,15.6英寸)])
    '-' → 空 Cell"""
    v = (v or "").strip()
    if v in ("-", ""):
        return Cell()
    parts = [p.strip() for p in v.split("|")]

    def one(p):
        dot = ""
        if p.startswith("●"):
            dot, p = "●", p[1:]
        elif p.startswith("○"):
            dot, p = "○", p[1:]
        return Cell(dot=dot, text=p.strip())

    head = one(parts[0])
    if len(parts) > 1:
        head.subs = [one(p) for p in parts[1:] if p]
    return head


def _short_name(full: str) -> str:
    """'长安启源Q05 2026款 405Air' → '405Air'；'…506激光极智版' → '506激光极智'
    （去品牌车系+年款前缀；尾缀「版」按 pjy golden 惯例去掉，全称保留在 Trim.full）"""
    m = re.search(r"\d{4}款\s*(.*)$", full)
    s = (m.group(1) if m else full).strip()
    if s.endswith("版") and len(s) > 1:
        s = s[:-1]
    return s


def _model_name(full: str) -> str:
    """'长安启源Q05 2026款 405Air' → '长安启源Q05'"""
    m = re.match(r"^(.*?)\s*\d{4}款", full)
    return (m.group(1) if m else full).strip()


def from_compact(data, series_id: str = "", scraped_at: str = "") -> RawTable:
    if isinstance(data, str):
        data = json.loads(data)          # 双重编码：外层已是 str
        if isinstance(data, str):
            data = json.loads(data)
    headers = data.get("headers", [])
    rows_in = data.get("rows", [])
    trims = [Trim(idx=i, full=h, short=_short_name(h)) for i, h in enumerate(headers)]
    model = _model_name(headers[0]) if headers else ""
    rows = []
    for r in rows_in:
        cells = [_split_compact_cell(v) for v in r.get("v", [])]
        rows.append(RawRow(name=r["n"], cells=cells))
    # 价格行
    price_row = next((r for r in rows if r.name == "厂商指导价(元)"), None)
    if price_row:
        for t, c in zip(trims, price_row.cells):
            t.price_guide = _parse_price(c.text)
    return RawTable(series_id=series_id, model=model, source="compact",
                    scraped_at=scraped_at, trims=trims, rows=rows)


def from_rich(data, series_id: str = "") -> RawTable:
    if isinstance(data, str):
        data = json.loads(data)
    trim_names = data.get("trimNames", [])
    trims = [Trim(idx=i, short=t, full=t) for i, t in enumerate(trim_names)]
    rows = []
    for r in data.get("rows", []):
        cells = [Cell(dot=v.get("dot", ""), text=v.get("text", "")) for v in r.get("values", [])]
        rows.append(RawRow(name=r["name"], cells=cells, group=r.get("group", "")))
    price_row = next((r for r in rows if r.name == "厂商指导价(元)"), None)
    if price_row:
        for t, c in zip(trims, price_row.cells):
            t.price_guide = _parse_price(c.text)
    return RawTable(series_id=series_id or data.get("series_id", ""), model="",
                    source="rich", lossy=True,
                    scraped_at=data.get("scraped_at", ""), trims=trims, rows=rows)


def detect_and_load(path: str, series_id: str = "") -> RawTable:
    """自动识别输入格式：canonical / compact / rich"""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    data = json.loads(content)
    if isinstance(data, str):                 # 双重编码 compact
        return from_compact(data, series_id=series_id)
    if data.get("schema", "").startswith("carkit.raw"):
        return RawTable.from_dict(data)
    if "headers" in data and "rows" in data and data["rows"] and "n" in data["rows"][0]:
        return from_compact(data, series_id=series_id)
    if "trimNames" in data:
        return from_rich(data, series_id=series_id)
    raise ValueError(f"无法识别的 raw 格式: {path}（keys={list(data.keys())[:6]}）")
