"""数据模型：canonical RawTable / Ladder / Snapshot / DiffResult / ValuationTable

所有模型均为 dataclass + to_json/from_json，JSON 是模块间与 UI 层的唯一交换格式。
"""
from __future__ import annotations
import json
import copy
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


def _merge_central_airbag(total, central):
    """Upgrade the old separate row once; new files have no row 42."""
    central = str(central or '').strip()
    if central in ('', '✕', '×', 'X', '-', '无', '无配置') or central.startswith('○'):
        return total
    if '[待定]' in central or '[待定]' in str(total):
        return '[待定]请核对含中央气囊的气囊总数'
    if '中央' in str(total):
        return total
    number = re.match(r'^\s*(\d+)', str(total))
    return f'{int(number[1])+1}气囊' if number else '[待定]中央气囊已配置，请确认气囊总数'


# ---------- canonical RawTable ----------

@dataclass
class Cell:
    """一个单元格：dot ∈ {'●','○',''}，text 为去掉符号的文本；subs 为双子项列表"""
    dot: str = ""
    text: str = ""
    subs: list = field(default_factory=list)   # list[Cell]（序列化时为 dict）

    @property
    def absent(self) -> bool:
        return not self.dot and not self.text.strip()

    def to_dict(self):
        d = {"dot": self.dot, "text": self.text}
        if self.subs:
            d["subs"] = [s.to_dict() if isinstance(s, Cell) else s for s in self.subs]
        return d

    @classmethod
    def from_dict(cls, d):
        text = d.get("text", "") or ""
        dot = d.get("dot", "") or ""
        # Some Autohome rows put per-subitem markers inside the text
        # (e.g. 主●/副●) and leave the cell-level dot empty.  Preserve the
        # text for component parsing, while exposing the effective marker to
        # the mapper so such cells are not treated as absent.
        if not dot and "●" in text:
            dot = "●"
        elif not dot and "○" in text:
            dot = "○"
        subs = [cls.from_dict(s) for s in d.get("subs", [])]
        return cls(dot=dot, text=text, subs=subs)


@dataclass
class Trim:
    idx: int
    short: str
    full: str = ""
    price_guide: Optional[float] = None   # 万元


@dataclass
class RawRow:
    name: str
    cells: list = field(default_factory=list)   # list[Cell]
    group: str = ""


@dataclass
class RawTable:
    schema: str = "carkit.raw/v1"
    series_id: str = ""
    model: str = ""
    source: str = ""            # compact | rich | html | manual
    lossy: bool = False         # 富结构旧版丢失子项信息 → True
    scraped_at: str = ""
    trims: list = field(default_factory=list)   # list[Trim]
    rows: list = field(default_factory=list)    # list[RawRow]

    def row(self, *names) -> Optional[RawRow]:
        """按名字取第一个命中的行（支持多个候选名）"""
        for n in names:
            for r in self.rows:
                if r.name == n:
                    return r
        return None

    def to_json(self, **kw):
        return json.dumps(self.to_dict(), ensure_ascii=False, **kw)

    def to_dict(self):
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d):
        trims = [Trim(**t) for t in d.get("trims", [])]
        rows = [RawRow(name=r["name"], group=r.get("group", ""),
                       cells=[Cell.from_dict(c) for c in r.get("cells", [])])
                for r in d.get("rows", [])]
        return cls(schema=d.get("schema", "carkit.raw/v1"), series_id=d.get("series_id", ""),
                   model=d.get("model", ""), source=d.get("source", ""),
                   lossy=d.get("lossy", False), scraped_at=d.get("scraped_at", ""),
                   trims=trims, rows=rows)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=1))


# ---------- Ladder（41项阶梯，竞品或自产品通用容器） ----------

@dataclass
class LadderItem:
    no: int
    name: str
    values: list = field(default_factory=list)       # 每版型归一化值（str 或 dict[复合项]）
    row_absent: bool = False                          # 汽车之家无该行（竞品侧 ✕ 依据）
    unmapped: bool = False                            # [待映射]
    subs: list = field(default_factory=list)          # 复合子项（#36）：[{sub, values[]}]
    note: str = ""


@dataclass
class Ladder:
    schema: str = "carkit.ladder/v1"
    side: str = "competitor"     # competitor | self
    model: str = ""
    series_id: str = ""
    checklist: str = "v1"
    date: str = ""
    source: str = ""
    trims: list = field(default_factory=list)    # [{name, price_guide}]
    items: list = field(default_factory=list)    # list[LadderItem]

    def item(self, no) -> Optional[LadderItem]:
        for it in self.items:
            if it.no == no:
                return it
        return None

    def to_dict(self):
        return asdict(self)

    def to_json(self, **kw):
        return json.dumps(self.to_dict(), ensure_ascii=False, **kw)

    @classmethod
    def from_dict(cls, d):
        items = [LadderItem(**it) for it in d.get("items", [])]
        from .usb import usb_label
        from .seat_functions import SUBS, normalize
        for item in items:
            if item.no == 32:
                item.values = [usb_label(value) for value in item.values]
            if item.no == 36 and item.subs and any(row['sub'] not in SUBS for row in item.subs):
                old = {row['sub']:row['values'] for row in item.subs}
                converted = []
                for i, value in enumerate(item.values):
                    combined = normalize(value)
                    combined.update({key:state for key,state in normalize({key:values[i] for key,values in old.items() if i < len(values)}).items()
                                     if key.startswith('二排') or key.endswith('头枕音响')})
                    converted.append(combined)
                item.subs = [{'sub':sub,'values':[value[sub] for value in converted]} for sub in SUBS]
        central = next((it for it in items if it.no == 42), None)
        if central:
            airbags = next((it for it in items if it.no == 5), None)
            if airbags is None:
                airbags = LadderItem(no=5, name='气囊数量', values=['✕']*len(central.values))
                items.append(airbags)
            airbags.values = [_merge_central_airbag(v, central.values[i] if i < len(central.values) else '')
                              for i,v in enumerate(airbags.values)]
            items = [it for it in items if it.no != 42]
        return cls(**{k: v for k, v in d.items() if k != "items"}, items=items)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=1))


# ---------- Snapshot（自产品快照，Ladder 的自产品特化：side=self） ----------
# 快照 JSON 直接复用 Ladder 结构（side="self"），附加 meta：

@dataclass
class Snapshot:
    schema: str = "carkit.snapshot/v1"
    model: str = ""
    version: str = ""
    date: str = ""
    status: str = ""
    trims: list = field(default_factory=list)    # [{name, price_guide, mix, range, position}]
    cells: list = field(default_factory=list)    # [{no, values:{trim:value}, basis}]
    pending: list = field(default_factory=list)  # [{no, reason, handling}]
    rulings: list = field(default_factory=list)  # deck 差异裁决记录

    def to_ladder(self, checklist_items) -> Ladder:
        """展开成 Ladder（side=self），values 按 trims 顺序"""
        trim_names = [t["name"] for t in self.trims]
        items = []
        cells_by_no = {c["no"]: c for c in self.cells}
        for ci in checklist_items:
            no = ci["no"]
            if ci.get("merged_into"):
                continue
            c = cells_by_no.get(no)
            if c is None:
                items.append(LadderItem(no=no, name=ci["name"], values=["✕"] * len(trim_names),
                                        note="清单未提及，按无配置比较"))
                continue
            vals = [c["values"].get(t) or "✕" for t in trim_names]
            sub_rows = []
            if isinstance(vals[0], dict) or any(isinstance(v, dict) for v in vals):
                # 复合子项（#36）：values 为 {sub: v} dict
                subnames = list(vals[0].keys()) if isinstance(vals[0], dict) else []
                sub_rows = [{"sub": s, "values": [(v.get(s, "✕") if isinstance(v, dict) else "✕")
                                                  for v in vals]} for s in subnames]
            items.append(LadderItem(no=no, name=ci["name"], values=vals,
                                    subs=sub_rows, note=c.get("basis", "")))
        return Ladder(side="self", model=self.model, checklist=self.version,
                      date=self.date, source=f"snapshot {self.version}",
                      trims=[{"name": t["name"], "price_guide": t.get("price_guide")}
                             for t in self.trims],
                      items=items)

    def to_json(self, **kw):
        return json.dumps(asdict(self), ensure_ascii=False, **kw)

    @classmethod
    def from_dict(cls, d):
        d = copy.deepcopy(d)
        cells = d.get('cells', [])
        central = next((c for c in cells if c['no'] == 42), None)
        if central:
            airbags = next((c for c in cells if c['no'] == 5), None)
            if airbags is None:
                airbags = {'no':5, 'values':{}, 'basis':'旧中央气囊合并'}
                cells.append(airbags)
            for name, value in central.get('values', {}).items():
                airbags['values'][name] = _merge_central_airbag(airbags['values'].get(name,'✕'), value)
            airbags.pop('links', None)
            d['cells'] = [c for c in cells if c['no'] != 42]
            d['pending'] = [p for p in d.get('pending',[]) if p.get('no') != 42]
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=1))


# ---------- DiffResult ----------

@dataclass
class DiffCell:
    no: int
    pair: int                  # 配对组索引
    verdict: str               # 多 | 少 | 同 | 豁免 | 不计
    display: str               # 判定明细表显示串（不含 ** 加粗标记）
    self_val: str = ""
    comp_val: str = ""
    exempt_id: str = ""
    backup_more: str = ""      # 若 verdict=多：BACKUP 多栏显示串
    backup_less: str = ""      # 若 verdict=少：BACKUP 少栏显示串


@dataclass
class PairSpec:
    self_trim: str
    comp_trim: str
    self_price: Optional[float] = None
    comp_price: Optional[float] = None


@dataclass
class DiffResult:
    schema: str = "carkit.diff/v1"
    self_model: str = ""
    comp_model: str = ""
    date: str = ""
    checklist: str = "v1"
    rules_version: str = "v1"
    pairs: list = field(default_factory=list)    # list[PairSpec-dict]
    cells: list = field(default_factory=list)    # list[DiffCell-dict]
    valuation: Optional[dict] = None             # 有赋值表时：三指标；无则 None

    def to_json(self, **kw):
        return json.dumps(asdict(self), ensure_ascii=False, **kw)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=1))


# ---------- ValuationTable（pjy 规定的赋值表） ----------

@dataclass
class ValuationItem:
    no: int
    name: str
    pricing: str = "flat"       # flat | segmented_per_km | band | per_unit | manual
    val: Optional[float] = None         # flat
    bands: list = field(default_factory=list)   # band: [{"range":[lo,hi],"val":x}] ; segmented: [{"range":[lo,hi],"per_km":x}]
    unit_val: Optional[float] = None    # per_unit
    note: str = ""
    rule: str = ""                      # 内置用户规则标识（可选）


@dataclass
class ValuationTable:
    schema: str = "carkit.valuation/v1"
    version: str = ""
    source: str = "pjy 规定"
    items: list = field(default_factory=list)   # list[ValuationItem]

    def item(self, no):
        for it in self.items:
            d = it if isinstance(it, dict) else asdict(it)
            if d.get("no") == no:
                return d
        return None

    def to_json(self, **kw):
        return json.dumps(asdict(self), ensure_ascii=False, **kw)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        items = [ValuationItem(**it) for it in d.get("items", [])]
        return cls(version=d.get("version", ""), source=d.get("source", "pjy 规定"), items=items)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=1))
