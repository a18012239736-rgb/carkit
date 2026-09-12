"""rules — 加载 engine/rules/ 下的随包规则数据（唯一事实源）"""
from __future__ import annotations
import json
import os

RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")


def _load(name):
    with open(os.path.join(RULES_DIR, name), encoding="utf-8") as f:
        return json.load(f)


class Rules:
    def __init__(self, rules_dir: str | None = None):
        global RULES_DIR
        if rules_dir:
            RULES_DIR = rules_dir
        self.checklist = _load("checklist_v1.json")
        self.exemptions = _load("exemptions.json")
        self.aliases = _load("aliases.json")
        self.items = [it for it in self.checklist["items"] if not it.get("merged_into")]
        self.items_by_no = {it["no"]: it for it in self.checklist["items"]}
        self.row_to_item = dict(self.aliases["row_to_item"])
        # checklist 的 source_rows 也并入行名映射（source_rows 优先）
        for it in self.checklist["items"]:
            for rn in it.get("source_rows", []):
                self.row_to_item.setdefault(rn, it["no"])
        self.exempt_by_id = {r["id"]: r for r in self.exemptions["rules"]}

    @property
    def version(self) -> str:
        return self.checklist["version"]

    def exemption(self, ex_id):
        return self.exempt_by_id.get(ex_id, {})

    def range_bands(self):
        return self.exempt_by_id.get("range_micro", {}).get("bands_km", [[0, 450], [451, 550], [551, 650], [651, 9999]])
