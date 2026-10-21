"""Self-contained comparison archives; never reload current rules or migrate inputs."""
from __future__ import annotations

import copy
import datetime
import json
import math
import re
from pathlib import Path

from .storage import atomic_write_text, unique_filename
from .valuer import normalize_floor_price

SCHEMA = 'carkit.comparison-plan/v1'


def _check(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value, label, limit=200):
    _check(isinstance(value, str) and 0 < len(value.strip()) <= limit, f'{label}不能为空或过长')
    return value


def _number(value, label):
    _check(not isinstance(value, bool) and isinstance(value, (int, float, str)), f'{label}必须是数字')
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f'{label}必须是有限数字') from None
    _check(math.isfinite(number) and number >= 0, f'{label}必须是大于等于0的有限数字')
    return int(number) if number.is_integer() else number


def _json(value):
    if isinstance(value, dict):
        _check(all(isinstance(key, str) for key in value), '方案对象字段名必须是字符串')
        for child in value.values():
            _json(child)
    elif isinstance(value, list):
        for child in value:
            _json(child)
    else:
        _check(value is None or isinstance(value, (str, bool, int, float)), '方案只能包含JSON数据')
        if isinstance(value, float):
            _check(math.isfinite(value), '方案不能包含NaN或Infinity')


def _without_paths(value):
    if isinstance(value, dict):
        return {key: _without_paths(child) for key, child in value.items()
                if key not in {'path', 'md_path'} and not key.endswith('_path')}
    if isinstance(value, list):
        return [_without_paths(child) for child in value]
    return value


def _rows(rows, label):
    _check(isinstance(rows, list), f'{label}必须是列表')
    numbers = []
    for row in rows:
        _check(isinstance(row, dict), f'{label}必须包含配置对象')
        no = row.get('no')
        _check(type(no) is int and no > 0, f'{label}配置编号无效')
        numbers.append(no)
    _check(len(numbers) == len(set(numbers)), f'{label}配置编号重复')


def _document(data, kind, label):
    _check(isinstance(data, dict) and data.get('schema') == f'carkit.{kind}/v1', f'{label}结构版本无效')
    _text(data.get('model'), label+'车型名称')
    trims = data.get('trims')
    _check(isinstance(trims, list) and trims, f'{label}缺少实际版型')
    names = []
    for trim in trims:
        _check(isinstance(trim, dict), f'{label}版型结构无效')
        names.append(_text(trim.get('name'), label+'版型名称'))
        if trim.get('price_guide') is not None:
            _number(trim['price_guide'], label+'指导价')
    name_set = set(names)
    _check(len(names) == len(name_set), f'{label}版型名称重复')
    if 'options' in data:
        from .models import normalize_product_options
        data['options'] = normalize_product_options(data['options'], names)
    rows = data.get('cells' if kind == 'snapshot' else 'items')
    _rows(rows, label)
    for row in rows:
        values = row.get('values')
        if kind == 'snapshot':
            # Sparse snapshots intentionally inherit or default omitted trims to ✕.
            _check(isinstance(values, dict) and values.keys() <= name_set, f'{label}配置值与版型不一致')
        else:
            _check(isinstance(values, list) and len(values) == len(names), f'{label}配置值列数与版型不一致')
            _check(isinstance(row.get('subs', []), list), f'{label}子项结构无效')
            for sub in row.get('subs', []):
                _check(isinstance(sub, dict) and isinstance(sub.get('values'), list)
                       and len(sub['values']) == len(names), f'{label}子项值列数与版型不一致')
    return names


def _valuation(data):
    _check(isinstance(data, dict) and data.get('schema') == 'carkit.valuation/v1', '方案赋值规则结构无效')
    _rows(data.get('items'), '赋值规则')
    for item in data['items']:
        _text(item.get('name'), '赋值规则名称')
        pricing = item.get('pricing', 'flat')
        _check(isinstance(pricing, str) and pricing in {'flat', 'manual', 'per_unit', 'band', 'segmented_per_km'}, '赋值方式无效')
        _check(isinstance(item.get('rule', ''), str), '赋值规则类型无效')
        for key in ('val', 'unit_val'):
            if item.get(key) is not None:
                item[key] = _number(item[key], f'#{item["no"]} {key}')
        _check(isinstance(item.get('params', {}), dict), '赋值参数必须是对象')
        for key, value in item.get('params', {}).items():
            item['params'][key] = _number(value, f'#{item["no"]} {key}')
        _check(isinstance(item.get('bands', []), list), '赋值档位必须是列表')
        for band in item.get('bands', []):
            _check(isinstance(band, dict) and isinstance(band.get('range'), list)
                   and len(band['range']) == 2, '赋值档位范围无效')
            band['range'] = [_number(value, '赋值档位范围') for value in band['range']]
            _check(band['range'][0] <= band['range'][1], '赋值档位上下限颠倒')
            for key in ('val', 'per_km'):
                if key in band:
                    band[key] = _number(band[key], '赋值档位金额')


def validate_plan(data):
    """Validate a copy without invoking model migrations or adding today's defaults."""
    data = copy.deepcopy(data)
    _json(data)
    _check(isinstance(data, dict) and data.get('schema') == SCHEMA, '不支持的对比方案版本')
    name = _text(data.get('name'), '方案名称', 100)
    _check(name.strip() not in {'.', '..'} and not re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]', name), '方案名称包含非法字符')
    name = name.strip()
    data['name'] = name
    _text(data.get('app_version'), '程序版本', 64)
    try:
        timestamp = datetime.datetime.fromisoformat(data.get('created_at', ''))
    except (TypeError, ValueError):
        raise ValueError('方案保存时间无效') from None
    _check(timestamp.tzinfo is not None, '方案保存时间缺少时区')
    inputs = data.get('inputs')
    _check(isinstance(inputs, dict) and isinstance(inputs.get('left_kind'), str)
           and inputs['left_kind'] in {'snapshot', 'ladder'}, '方案输入类型无效')
    left = _document(inputs.get('left'), inputs['left_kind'], '左侧')
    right = _document(inputs.get('right'), 'ladder', '右侧')
    pairs = inputs.get('pairs')
    _check(isinstance(pairs, list) and pairs, '方案缺少人工版型配对')
    for pair in pairs:
        _check(isinstance(pair, dict) and pair.get('self_trim') in left
               and pair.get('comp_trim') in right, '方案配对引用不存在的版型')
        for key in ('self_floor_price', 'comp_floor_price'):
            pair[key] = normalize_floor_price(pair.get(key), '方案底价')
    _valuation(inputs.get('valuation'))
    rules = inputs.get('rules')
    _check(isinstance(rules, dict) and all(isinstance(rules.get(key), dict)
           for key in ('checklist', 'aliases', 'exemptions')), '方案缺少本轮规则副本')
    _rows(rules['checklist'].get('items'), '清单规则')
    _check(isinstance(rules['aliases'].get('row_to_item'), dict)
           and isinstance(rules['exemptions'].get('rules'), list), '方案规则结构无效')
    _check(isinstance(inputs.get('excluded_rows'), list)
           and all(isinstance(row, str) for row in inputs['excluded_rows']), '方案展示偏好无效')
    result = data.get('result')
    _check(isinstance(result, dict) and result.get('ok') is True, '方案缺少成功的对比结果')
    _check(result.get('self_model') == inputs['left']['model']
           and result.get('comp_model') == inputs['right']['model'], '方案结果车型与输入不一致')
    _check(isinstance(result.get('md'), str) and isinstance(result.get('cells'), list)
           and isinstance(result.get('groups'), list), '方案结果结构不完整')
    _check(len(result['groups']) == len(pairs), '方案结果与配对组数不一致')
    for index, group in enumerate(result['groups']):
        _check(isinstance(group, dict) and isinstance(group.get('pair'), dict), '方案结果配对结构无效')
        pair = group['pair']
        _check(all(pair.get(key) == pairs[index][key] for key in ('self_trim', 'comp_trim')), '方案结果配对与输入不一致')
        for key in ('self_floor_price', 'comp_floor_price'):
            _check(normalize_floor_price(pair.get(key), '结果底价') == pairs[index][key], '方案结果底价与输入不一致')
            if key in group:
                _check(normalize_floor_price(group[key], '结果底价') == pairs[index][key], '方案结果底价与输入不一致')
        _check(isinstance(group.get('more'), list) and isinstance(group.get('less'), list)
               and isinstance(group.get('valuation'), dict), '方案结果金额或配置结构无效')
        _check(all(isinstance(label, str) for label in group['more']+group['less']), '方案配置描述必须是文本')
        for key in ('self_options', 'comp_options'):
            if key in group:
                _check(isinstance(group[key], list) and all(isinstance(option, str) for option in group[key]), '方案选装描述必须是文本列表')
        for key in ('config_adv', 'flat_adv', 'overall'):
            _check(key in group['valuation'] and (group['valuation'][key] is None
                   or type(group['valuation'][key]) in (int, float)), '方案结果金额类型无效')
    for cell in result['cells']:
        _check(isinstance(cell, dict) and type(cell.get('pair')) is int
               and 0 <= cell['pair'] < len(pairs), '方案明细引用不存在的配对组')
    for key in ('review', 'evidence'):
        if key in result:
            _check(isinstance(result[key], (dict, list)), '方案核对记录结构无效')
    result.pop('comparison_id', None)  # Runtime tokens never survive into an archive.
    return _without_paths(data)


def create_plan(name, inputs, result, app_version):
    return validate_plan({'schema': SCHEMA, 'name': name,
                          'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
                          'app_version': app_version, 'inputs': inputs, 'result': result})


def save_plan(directory, name, inputs, result, app_version):
    data = create_plan(name, inputs, result, app_version)
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / unique_filename(data['name'], '.json')
    # Reserve a new name first: atomic_write_text must never replace another plan.
    with path.open('x', encoding='utf-8'):
        pass
    try:
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False)+'\n')
    except Exception:
        path.unlink()
        raise
    return {'file': path.name, 'name': data['name'], 'created_at': data['created_at']}


def load_plan(directory, filename):
    _check(isinstance(filename, str) and filename and Path(filename).name == filename
           and '/' not in filename and '\\' not in filename and filename.endswith('.json'), '方案文件名无效')
    root = Path(directory).resolve()
    path = root / filename
    _check(not path.is_symlink() and path.resolve().parent == root, '方案文件超出保存目录')
    with path.open(encoding='utf-8') as source:
        return validate_plan(json.load(source))
