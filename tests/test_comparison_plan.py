import copy
import json

import pytest

from engine import comparison_plan, valuer


def inputs(left_kind='snapshot'):
    left = {'schema': 'carkit.snapshot/v1', 'model': '本品',
            'trims': [{'name': '基础型', 'price_guide': 10}],
            'cells': [{'no': 35, 'values': {'基础型': '主驾6向电调+副驾4向手调(腰撑4向)'},
                       'basis': '人工核对', 'links': {}}]}
    right = {'schema': 'carkit.ladder/v1', 'model': '竞品',
             'trims': [{'name': '高配版', 'price_guide': 11}],
             'items': [{'no': 35, 'name': '座椅调节', 'values': ['主驾8向电调+副驾4向电调'], 'subs': []}],
             'evidence': {'35': [{'row': '主座椅调节方式', 'dot': '●', 'text': '高低调节(4向)',
                                 'raw_path': '/another/computer/raw.json'}]}}
    if left_kind == 'ladder':
        left = copy.deepcopy(right)
        left['model'] = '本品'
        left['trims'][0]['name'] = '基础型'
    return {'left_kind': left_kind, 'left': left, 'right': right,
            'pairs': [{'self_trim': '基础型', 'comp_trim': '高配版',
                       'self_floor_price': 90000, 'comp_floor_price': 95000}],
            'valuation': {'schema': 'carkit.valuation/v1', 'version': '当时规则', 'source': '人工设置',
                          'items': [{'no': 35, 'name': '座椅调节', 'pricing': 'manual', 'rule': 'dynamic',
                                     'params': {'electric_bonus': 400, 'per_direction': 50, 'legacy_key': 7},
                                     'val': None, 'unit_val': None, 'bands': []}]},
            'rules': {'checklist': {'version': 'v1', 'items': [{'no': 35, 'name': '座椅调节'}]},
                      'aliases': {'row_to_item': {'主座椅调节方式': 35}},
                      'exemptions': {'rules': []}},
            'excluded_rows': ['腰部支撑']}


def result():
    return {'ok': True, 'self_model': '本品', 'comp_model': '竞品',
            'md_path': '/private/current/report.md', 'md': '原来算好的报告',
            'cells': [{'no': 35, 'pair': 0, 'self_config': '主驾6向电调+副驾4向手调',
                       'comp_config': '主驾8向电调+副驾4向电调'}],
            'groups': [{'pair': copy.deepcopy(inputs()['pairs'][0]), 'more': [], 'less': ['副驾4向电调'],
                        'valuation': {'config_adv': -500, 'flat_adv': 9500, 'overall': 4500}}],
            'review': [{'reason': '方向未注明'}], 'evidence': {'seat_count': [6, 4]},
            'missing_valuation': [], 'comparison_id': 'old-runtime-token'}


@pytest.mark.parametrize('kind', ['snapshot', 'ladder'])
def test_saved_plan_preserves_facts_results_evidence_and_old_rules(tmp_path, monkeypatch, kind):
    source, report = inputs(kind), result()
    before = copy.deepcopy((source, report))
    record = comparison_plan.save_plan(tmp_path, ' 项目A—10月对比 ', source, report, '0.1.19')
    monkeypatch.setitem(valuer.DEFAULT_DYNAMIC_PARAMS[35], 'electric_bonus', 99999)
    monkeypatch.setattr(valuer, 'default_valuation', lambda *_: pytest.fail('不应使用当前默认规则'))
    loaded = comparison_plan.load_plan(tmp_path, record['file'])
    assert loaded['name'] == record['name'] == '项目A—10月对比'
    assert loaded['app_version'] == '0.1.19'
    assert loaded['created_at'] == record['created_at']
    assert loaded['inputs']['valuation'] == source['valuation']
    assert loaded['inputs']['rules'] == source['rules']
    assert loaded['result']['groups'][0]['valuation'] == report['groups'][0]['valuation']
    assert loaded['result']['md'] == report['md']
    assert loaded['result']['review'] == report['review']
    assert loaded['result']['evidence'] == report['evidence']
    assert loaded['inputs']['right']['evidence']['35'][0] == {
        'row': '主座椅调节方式', 'dot': '●', 'text': '高低调节(4向)'}
    assert 'md_path' not in loaded['result']
    assert 'comparison_id' not in loaded['result']
    if kind == 'snapshot':
        assert loaded['inputs']['left']['cells'][0]['values'] == source['left']['cells'][0]['values']
    loaded['inputs']['valuation']['items'][0]['params']['electric_bonus'] = 1
    assert comparison_plan.load_plan(tmp_path, record['file'])['inputs']['valuation'] == source['valuation']
    assert (source, report) == before


def test_same_name_is_always_saved_as_new_file(tmp_path):
    first = comparison_plan.save_plan(tmp_path, '方案', inputs(), result(), '0.1.19')
    second = comparison_plan.save_plan(tmp_path, '方案', inputs(), result(), '0.1.19')
    assert first['file'] != second['file']
    assert len(list(tmp_path.glob('*.json'))) == 2


@pytest.mark.parametrize('name', ['', '  ', '.', '..', '../覆盖', '目录\\方案', '方案\x00', '方案\n', 'a'*101, None])
def test_bad_names_never_write(name, tmp_path):
    with pytest.raises(ValueError):
        comparison_plan.save_plan(tmp_path / 'plans', name, inputs(), result(), '0.1.19')
    assert not (tmp_path / 'plans').exists()


@pytest.mark.parametrize('filename', ['../outside.json', '/outside.json', '..\\outside.json',
                                       'plans/one.json', 'one.JSON', 'one.txt', '', None])
def test_load_rejects_paths_and_non_json_names(filename, tmp_path):
    with pytest.raises(ValueError, match='文件名'):
        comparison_plan.load_plan(tmp_path, filename)


def test_load_rejects_symlink_escape(tmp_path):
    root = tmp_path / 'plans'
    root.mkdir()
    external = tmp_path / 'outside.json'
    external.write_text('{}', encoding='utf-8')
    (root / 'link.json').symlink_to(external)
    with pytest.raises(ValueError, match='超出保存目录'):
        comparison_plan.load_plan(root, 'link.json')
    assert external.read_text(encoding='utf-8') == '{}'


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(schema='carkit.comparison-plan/v9'),
    lambda d: d.update(created_at='bad'),
    lambda d: d.update(created_at='2026-10-14T12:00:00'),
    lambda d: d['inputs']['left']['trims'].append({'name': '基础型'}),
    lambda d: d['inputs']['left']['cells'][0].update(values={'不存在': '✕'}),
    lambda d: d['inputs']['right']['items'][0].update(values=[]),
    lambda d: d['inputs']['right']['items'][0].update(subs=[{'sub': '功能', 'values': []}]),
    lambda d: d['inputs']['pairs'][0].update(comp_trim='不存在'),
    lambda d: d['inputs']['pairs'][0].update(self_floor_price=0),
    lambda d: d['inputs']['pairs'][0].update(comp_floor_price='Infinity'),
    lambda d: d['inputs']['valuation']['items'][0]['params'].update(electric_bonus=-1),
    lambda d: d['inputs']['valuation']['items'][0]['params'].update(per_direction='NaN'),
    lambda d: d['result'].update(md=None),
    lambda d: d['result'].update(groups=[]),
    lambda d: d['result']['groups'][0]['pair'].update(self_floor_price=12),
    lambda d: d['result']['groups'][0].update(comp_floor_price=12),
    lambda d: d['result']['groups'][0]['valuation'].update(config_adv='500'),
    lambda d: d['result'].update(review='错误结构'),
    lambda d: d['result']['cells'][0].update(pair=3),
    lambda d: d['result']['groups'][0]['valuation'].update(config_adv=float('inf')),
])
def test_invalid_archives_rejected_without_mutating_caller(mutate):
    data = comparison_plan.create_plan('方案', inputs(), result(), '0.1.19')
    mutate(data)
    original = copy.deepcopy(data)
    with pytest.raises(ValueError):
        comparison_plan.validate_plan(data)
    assert data == original


def test_saved_numbers_normalize_without_schema_upgrade():
    data = inputs()
    data['valuation']['items'][0]['params']['electric_bonus'] = '420'
    data['pairs'][0]['self_floor_price'] = '90000'
    validated = comparison_plan.create_plan('方案', data, result(), '0.1.19')
    assert validated['inputs']['pairs'][0]['self_floor_price'] == 90000
    assert validated['inputs']['valuation']['items'][0]['params'] == {
        'electric_bonus': 420, 'per_direction': 50, 'legacy_key': 7}
    assert len(validated['inputs']['valuation']['items']) == 1
    assert data['valuation']['items'][0]['params']['electric_bonus'] == '420'


def test_sparse_snapshot_values_and_legacy_inheritance_are_preserved():
    data = inputs()
    data['left']['trims'].append({'name': '豪华型', 'base': '基础型'})
    validated = comparison_plan.create_plan('方案', data, result(), '0.1.19')
    assert validated['inputs']['left'] == data['left']
    data['left']['cells'][0]['values'] = {}
    assert comparison_plan.create_plan('方案', data, result(), '0.1.19')['inputs']['left'] == data['left']


def test_collision_and_failed_write_never_replace_existing_plan(tmp_path, monkeypatch):
    record = comparison_plan.save_plan(tmp_path, '方案', inputs(), result(), '0.1.19')
    path = tmp_path / record['file']
    previous = path.read_bytes()
    monkeypatch.setattr(comparison_plan, 'unique_filename', lambda *_: path.name)
    with pytest.raises(FileExistsError):
        comparison_plan.save_plan(tmp_path, '方案', inputs(), result(), '0.1.19')
    assert path.read_bytes() == previous
    monkeypatch.setattr(comparison_plan, 'unique_filename', lambda *_: 'new.json')

    def fail(*_):
        raise OSError('模拟写入失败')

    monkeypatch.setattr(comparison_plan, 'atomic_write_text', fail)
    with pytest.raises(OSError, match='写入失败'):
        comparison_plan.save_plan(tmp_path, '方案', inputs(), result(), '0.1.19')
    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_load_rejects_json_nan(tmp_path):
    data = comparison_plan.create_plan('方案', inputs(), result(), '0.1.19')
    data['result']['groups'][0]['valuation']['config_adv'] = float('nan')
    (tmp_path / 'bad.json').write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='NaN'):
        comparison_plan.load_plan(tmp_path, 'bad.json')
