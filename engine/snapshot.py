"""snapshot — 自产品快照加载/展开/导入

快照 JSON 是事实源（GUI 快照编辑器产出同格式）。「同基础」继承与裸●简写
在 resolve() 中展开为实际值。
"""
from __future__ import annotations
import re
from .models import Snapshot

# Zero-price tiers explicitly defined by pjy, not unpriced '/' items.
BASE_CONFIG = {4: 'R16钢轮毂', 17: '卤素大灯', 25: '塑料', 26: '手调',
               31: '手动防眩目', 32: 'USB/Type-C 3个', 34: '织物', 35: '主驾手调+副驾手调'}


def prepare_snapshot(snap):
    """Fill baseline tiers and establish links once; edited overrides keep no link."""
    by_no = {c['no']: c for c in snap.cells}
    seat = by_no.get(36)
    if seat:
        from .seat_functions import normalize
        old = seat['values']
        seat['values'] = {name: normalize(value) for name, value in old.items()}
        if seat['values'] != old:
            seat.pop('links', None)
    for no, default in BASE_CONFIG.items():
        cell = by_no.get(no)
        if cell is None:
            cell = {'no': no, 'values': {}, 'basis': '基础配置默认档位'}
            snap.cells.append(cell)
        for trim in snap.trims:
            if cell['values'].get(trim['name']) in (None, '', '✕', '×', 'X', '-', '无'):
                cell['values'][trim['name']] = default
    from .usb import usb_label
    for name, value in by_no[32]['values'].items():
        by_no[32]['values'][name] = usb_label(value)
    snap.cells.sort(key=lambda c: c['no'])
    for cell in snap.cells:
        if 'links' in cell:
            continue
        cell['links'] = {}
        for trim in snap.trims:
            name, base = trim['name'], trim.get('base')
            if not base or base not in cell['values']:
                continue
            value, parent = cell['values'].get(name), cell['values'][base]
            if isinstance(value, dict) and isinstance(parent, dict):
                cell['links'][name] = {sub: base for sub in value if value[sub] == parent.get(sub)}
            elif value == parent:
                cell['links'][name] = base
    return snap

def resolve(snap: Snapshot) -> Snapshot:
    """展开继承简写：'同基础'/裸'●'（继承本行左侧最近的具体值）"""
    # Refresh only values still identical to the old import output. Preserve
    # every user correction, including explicit design uncertainties.
    if snap.version == 'ppt-import-v1':
        from .ppt_import import make_snapshot
        source = next((r.get('draft') for r in snap.rulings if r.get('type') == 'ppt_import'), None)
        fresh = {c['no']: c for c in make_snapshot(source).cells} if source else {}
        def upgrade(v, replacement):
            if isinstance(v, dict):
                return {k: upgrade(x, replacement.get(k, '✕') if isinstance(replacement, dict) else '✕') for k,x in v.items()}
            return replacement if v == '[待定]PPT未说明' else v
        for c in snap.cells:
            for name, value in c['values'].items():
                c['values'][name] = upgrade(value, fresh.get(c['no'], {}).get('values', {}).get(name, '✕'))
        snap.pending = [p for p in snap.pending if p.get('no') != 0]
        snap.version = 'ppt-import-v2'
    trim_names = [t["name"] for t in snap.trims]
    for cell in snap.cells:
        vals = cell["values"]
        if not isinstance(vals, dict):
            continue
        first = vals.get(trim_names[0])
        last_concrete = first
        for t in trim_names:
            v = vals.get(t)
            if isinstance(v, dict):
                continue    # 复合子项不做继承展开（编辑器直接存全量）
            if v in ("同基础", "同基础型"):
                vals[t] = first
            elif v == "●" and isinstance(last_concrete, str) and len(last_concrete) > 1 \
                    and last_concrete.startswith("●"):
                vals[t] = last_concrete     # 裸●继承左侧带值的●
            elif v is not None and v != "":
                last_concrete = v
    return prepare_snapshot(snap)


def parse_snapshot_md(path: str) -> Snapshot:
    """从既有快照 md 的「覆盖率对账表」导入（41项×版型表）——best effort，
    复合单元格(#36)按 '/' 拆子项。GUI/JSON 是首选，本函数用于迁移旧文件。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # 版型列名：从对账表表头行取
    m = re.search(r"\|\s*#\s*\|\s*配置项\s*\|([^|]+(?:\|[^|]+)*?)\|\s*定稿依据\s*\|", text)
    if not m:
        raise ValueError("未找到覆盖率对账表表头")
    trim_names = [c.strip() for c in m.group(1).strip().strip("|").split("|")]
    cells = []
    row_re = re.compile(r"^\|\s*(\d+|—)\s*\|([^|]+)\|(.+)\|\s*$")
    in_table = False
    for line in text.splitlines():
        if line.startswith("| # | 配置项"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table:
            rm = row_re.match(line.strip())
            if not rm:
                if line.strip() and not line.startswith("|"):
                    in_table = False
                continue
            no_s, _name, rest = rm.groups()
            if no_s == "—":
                continue
            cols = [c.strip() for c in rest.strip().strip("|").split("|")]
            # 最后一列是定稿依据
            basis = cols[-1] if len(cols) > len(trim_names) else ""
            vals_raw = cols[:len(trim_names)]
            no = int(no_s)
            if no == 36:
                from .seat_functions import normalize
                values = {}
                for t, v in zip(trim_names, vals_raw):
                    subs = {}
                    for part in v.split("/"):
                        part = part.strip()
                        for key in ("前加热通风", "前按摩", "头枕音响", "头枕", "二排"):
                            if part.startswith(key):
                                subs["头枕音响" if key == "头枕" else key] = \
                                    "●" if part.endswith("●") else "✕"
                    values[t] = normalize(subs)
            else:
                values = dict(zip(trim_names, vals_raw))
            cells.append({"no": no, "values": values, "basis": basis})
    return Snapshot(model="", version="", cells=cells)
