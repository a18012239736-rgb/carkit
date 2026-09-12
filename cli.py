#!/usr/bin/env python3
"""carkit CLI — engine 的命令行入口（开发/回归/Claude 工作流共用）

命令：
  ladder   RAW.json [-o 阶梯.json] [--md 阶梯.md] [--series 8241] [--model 启源Q05]
  snapshot MD快照 [-o 快照.json]           # 旧 md 快照迁移（best effort）
  diff     --snapshot S.json --ladder L.json --pairs "基础型:405Max,舒适型:506Max"
           [--valuation V.json] [-o 结果.md] [--json 结果.json]
  template [-o 赋值表模板.xlsx]             # 生成 pjy 填的赋值表模板
  selftest                                   # golden 回归自检
"""
from __future__ import annotations
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.rules import Rules
from engine import rawschema, ladder as ladder_mod, differ, render_backup, valuer
from engine.models import Snapshot, Ladder


def cmd_ladder(args):
    rules = Rules()
    raw = rawschema.detect_and_load(args.raw, series_id=args.series or "")
    lad = ladder_mod.build_ladder(raw, rules, model=args.model or raw.model,
                                  series_id=args.series or raw.series_id,
                                  date=datetime.date.today().isoformat())
    out = args.o or f"竞品阶梯-{lad.model}-{lad.date}.json"
    lad.save(out)
    print(f"[ok] 阶梯 JSON → {out}（{len(lad.trims)}版型 × {len(lad.items)}项）")
    if raw.lossy:
        print("[warn] 输入为富结构旧版 raw，双子项信息有损（○选装可能丢失），建议用 compact 版重抓")
    unmapped = [it.no for it in lad.items if it.unmapped]
    if unmapped:
        print(f"[待映射] 项: {unmapped} —— 请人工裁决后补 rules/aliases.json")
    if args.md:
        md = ladder_mod.render_md(lad)
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[ok] 阶梯 md → {args.md}")


def cmd_snapshot(args):
    snap = Snapshot.from_dict(json.load(open(args.json, encoding="utf-8"))) \
        if args.json.endswith(".json") else None
    if snap is None:
        from engine.snapshot import parse_snapshot_md, resolve
        snap = resolve(parse_snapshot_md(args.json))
    out = args.o or "snapshot.json"
    snap.save(out)
    print(f"[ok] 快照 JSON → {out}（{len(snap.cells)}项 × {len(snap.trims)}版型）")


def cmd_diff(args):
    rules = Rules()
    snap = Snapshot.load(args.snapshot)
    from engine.snapshot import resolve
    snap = resolve(snap)
    self_lad = snap.to_ladder(rules.checklist["items"])
    comp_lad = Ladder.load(args.ladder)
    pairs = []
    for p in args.pairs.split(","):
        s, c = p.split(":")
        pairs.append({"self_trim": s.strip(), "comp_trim": c.strip()})
    # 校验配对版型存在（铁律：配对必须显式指定且有效）
    self_trims = [t["name"] for t in self_lad.trims]
    comp_trims = [t["name"] for t in comp_lad.trims]
    for pr in pairs:
        if pr["self_trim"] not in self_trims:
            sys.exit(f"[错误] 自产品版型不存在: {pr['self_trim']}（可用: {self_trims}）")
        if pr["comp_trim"] not in comp_trims:
            sys.exit(f"[错误] 竞品版型不存在: {pr['comp_trim']}（可用: {comp_trims}）")
    cells = differ.diff(self_lad, comp_lad, pairs, rules)
    # 注入项名
    name_by_no = {it["no"]: (it.get("md_name") or it["name"]) for it in rules.checklist["items"]}
    for c in cells:
        c["name"] = name_by_no.get(c["no"], str(c["no"]))
    self_prices = {t["name"]: t.get("price_guide") for t in self_lad.trims}
    comp_prices = {t["name"]: t.get("price_guide") for t in comp_lad.trims}
    valuation = None
    if args.valuation:
        from engine.models import ValuationTable
        if args.valuation.endswith(".xlsx"):
            vd = valuer.load_xlsx(args.valuation)
            json_path = args.valuation.rsplit(".", 1)[0] + ".json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(vd, f, ensure_ascii=False, indent=1)
            valuation = ValuationTable.from_dict(vd) if hasattr(ValuationTable, "from_dict") else _vt(vd)
        else:
            valuation = ValuationTable.load(args.valuation)
    groups = differ.assemble_backup(cells, pairs, snap.model, comp_lad.model,
                                    self_prices, comp_prices, valuation)
    notes = [f"[暂定/待定]：{p.get('reason')}（{p.get('handling')}）" for p in snap.pending]
    md = render_backup.render_md(snap.model or "自产品", comp_lad.model or "竞品",
                                 groups, cells, rules_version=rules.version,
                                 checklist=rules.version,
                                 date=datetime.date.today().isoformat(), notes=notes)
    out = args.o or f"赋值对比-{snap.model}vs{comp_lad.model}-{datetime.date.today().isoformat()}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[ok] 对比结果 → {out}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"pairs": pairs, "cells": cells, "groups": groups}, f,
                      ensure_ascii=False, indent=1)
        print(f"[ok] 结构化结果 → {args.json}")
    # 待赋值提示
    for i, g in enumerate(groups):
        miss = (g.get("valuation") or {}).get("missing")
        if miss:
            print(f"[待赋值] 组{i + 1} 缺金额项: {miss} —— 请 pjy 在赋值表中补，程序不脑补")


def _vt(d):
    from engine.models import ValuationTable, ValuationItem
    return ValuationTable(version=d.get("version", ""), source=d.get("source", ""),
                          items=[ValuationItem(**it) for it in d["items"]])


def cmd_template(args):
    rules = Rules()
    out = args.o or "赋值表模板.xlsx"
    valuer.make_template_xlsx(out, rules)
    print(f"[ok] 赋值表模板 → {out}（41项预填，金额留空=待赋值；填完后 diff --valuation 使用）")


def cmd_selftest(args):
    import subprocess
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-x", "-q"],
                       cwd=os.path.dirname(os.path.abspath(__file__)))
    sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(prog="carkit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ladder", help="raw JSON → 41项竞品阶梯")
    p.add_argument("raw")
    p.add_argument("-o", help="输出阶梯 JSON 路径")
    p.add_argument("--md", help="同时输出阶梯 md")
    p.add_argument("--series", help="seriesId")
    p.add_argument("--model", help="车型名")
    p.set_defaults(fn=cmd_ladder)

    p = sub.add_parser("snapshot", help="快照 md/json → 快照 JSON")
    p.add_argument("json")
    p.add_argument("-o")
    p.set_defaults(fn=cmd_snapshot)

    p = sub.add_parser("diff", help="快照 × 竞品阶梯 → 赋值对比结果")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--ladder", required=True)
    p.add_argument("--pairs", required=True, help='版型配对 "自:竞,自:竞"（必须人工指定）')
    p.add_argument("--valuation", help="赋值表 JSON/xlsx（缺省只出差配清单）")
    p.add_argument("-o", help="输出 md")
    p.add_argument("--json", help="输出结构化 JSON")
    p.set_defaults(fn=cmd_diff)

    p = sub.add_parser("template", help="生成赋值表 xlsx 模板")
    p.add_argument("-o")
    p.set_defaults(fn=cmd_template)

    p = sub.add_parser("selftest", help="golden 回归")
    p.set_defaults(fn=cmd_selftest)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
