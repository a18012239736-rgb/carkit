"""Autohome display categories, with captured row groups taking precedence."""
from __future__ import annotations
import json
from pathlib import Path
import re

from . import rawschema


def clean_group(name):
    return re.sub(r'\s*[●]?\s*标配\s*[○]?\s*选配\s*[-−—]?\s*无\s*$', '', name or '').strip()


def display_groups(rows, extra_names, raw_dir):
    catalogue = json.loads(Path(__file__).with_name('rules').joinpath('autohome_categories.json').read_text(encoding='utf-8'))
    catalogue_groups = {group['name']: group['rows'] for group in catalogue['groups']}
    known = {}
    for group, names in catalogue_groups.items():
        for name in names:
            known.setdefault(name, []).append(group)
    for name, target in catalogue.get('legacy_aliases', {}).items():
        if target in known:
            known.setdefault(name, known[target])

    names = list(dict.fromkeys([*(row.name for row in rows), *extra_names]))
    captured, groups = {}, {}
    for row in rows:
        group = clean_group(row.group) or ('价格信息' if row.name in ('厂商指导价(元)', '经销商报价') else '')
        if group:
            groups.setdefault(group, [])
            targets = captured.setdefault(row.name, [])
            if group not in targets:
                targets.append(group)

    needed = set(names) - captured.keys()
    history = {}
    if needed:
        for path in sorted(Path(raw_dir).glob('*.json')):
            try:
                old = rawschema.detect_and_load(str(path))
                for row in old.rows:
                    group = clean_group(row.group)
                    if row.name in needed and group:
                        targets = history.setdefault(row.name, [])
                        if group not in targets:
                            targets.append(group)
            except Exception:
                continue

    pending = {}

    def add(name, targets):
        for group in targets:
            bucket = groups[group] if group in groups else pending.setdefault(group, [])
            if name not in bucket:
                bucket.append(name)

    for row in rows:
        group = clean_group(row.group)
        targets = [group] if group else captured.get(row.name) or history.get(row.name) or known.get(row.name) or ['未分类（旧数据）']
        add(row.name, targets)
    current_names = {row.name for row in rows}
    for name in names:
        if name not in current_names:
            add(name, history.get(name) or known.get(name) or ['其他车型/已保存'])

    for group in catalogue_groups:
        if group in pending:
            groups[group] = pending.pop(group)
    for group in ('未分类（旧数据）', '其他车型/已保存'):
        if group in pending:
            pending[group] = pending.pop(group)
    groups.update(pending)
    return [{'name': name, 'rows': items} for name, items in groups.items()]
