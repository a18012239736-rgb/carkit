"""Complete-plan API round trips stay independent of current files and rules."""
import copy
import json
from pathlib import Path

import pytest

from api.bridge import Bridge
from engine import valuer
from engine.comparison_plan import load_plan
from engine.models import Cell, RawRow, RawTable, Snapshot, Trim
from engine.storage import atomic_write_text
from test_comparison_display import ladder


@pytest.fixture
def setup(tmp_path):
    instances = []

    def new_bridge():
        bridge = Bridge(str(tmp_path / 'work'))
        instances.append(bridge)
        return bridge

    bridge = new_bridge()
    left_path = tmp_path / 'left.json'
    right_path = tmp_path / 'right.json'
    Snapshot(model='本品', version='manual-test', status='定稿', date='2026-10-14',
             trims=[{'name': '左版', 'price_guide': 10}], cells=[
                 {'no': 1, 'values': {'左版': '500km'}, 'basis': '本品设计输入'},
                 {'no': 35, 'values': {'左版': '主驾6向电调+副驾4向手调'}, 'basis': '人工确认'},
                 {'no': 40, 'values': {'左版': '热泵空调'}, 'basis': '本品设计输入'},
             ]).save(left_path)
    raw = RawTable(model='竞品', series_id='9991', source='html', scraped_at='2026-10-14T12:00:00+08:00',
                   trims=[Trim(idx=0, short='右版', full='竞品 2026款 右版', price_guide=11)], rows=[
                       RawRow(name='CLTC纯电续航里程(km)', group='基本参数', cells=[Cell(text='630')]),
                       RawRow(name='主座椅调节方式', group='座椅配置', cells=[Cell(subs=[
                           Cell(dot='●', text='前后调节'), Cell(dot='●', text='靠背调节'),
                           Cell(dot='●', text='高低调节(4向)'), Cell(dot='●', text='腰部支撑(4向)'),
                       ])]),
                       RawRow(name='副座椅调节方式', group='座椅配置', cells=[Cell(subs=[
                           Cell(dot='●', text='前后调节'), Cell(dot='●', text='靠背调节'),
                       ])]),
                       RawRow(name='主/副驾驶座电动调节', group='座椅配置', cells=[Cell(text='主●/副●')]),
                   ])
    raw_path = Path(bridge.workdir) / 'raw' / '原始配置.json'
    raw.save(raw_path)
    right = ladder({1: '630km', 35: '主驾8向电调+副驾4向电调'}, '右版', '竞品')
    right.evidence = {'raw': raw.to_dict()}
    right.save(right_path)
    valuation = valuer.default_valuation(bridge.rules)
    next(item for item in valuation['items'] if item['no'] == 40)['val'] = 2600
    saved = bridge.save_current_valuation(valuation)
    assert saved['ok']
    preferences = Path(bridge.workdir) / '阶梯展示排除清单.json'
    atomic_write_text(preferences, json.dumps({'excluded_rows': ['腰部支撑']}))
    pairs = [{'self_trim': '左版', 'comp_trim': '右版',
              'self_floor_price': 88000, 'comp_floor_price': 101000}]
    files = {path: path.read_bytes() for path in (left_path, right_path, raw_path, Path(saved['path']))}
    yield {'bridge': bridge, 'new_bridge': new_bridge, 'left': left_path, 'right': right_path,
           'raw': raw_path, 'valuation': Path(saved['path']), 'preferences': preferences,
           'pairs': pairs, 'files': files}
    for instance in instances:
        instance.shutdown()


def _run(state, bridge=None, pairs=None):
    report = (bridge or state['bridge']).run_diff(str(state['left']), str(state['right']),
                                                pairs or state['pairs'])
    assert report['ok'], report.get('error')
    return report


def _save(bridge, report, name='项目—10月对比'):
    record = bridge.save_comparison_plan(name, report['comparison_id'])
    assert record['ok'], record.get('error')
    return record


def _rerun(bridge, opened, pairs=None):
    paths = opened['paths']
    report = bridge.run_diff(paths['left'], paths['right'], pairs or opened['inputs']['pairs'],
                             paths['valuation'], opened['inputs']['left_kind'] == 'ladder', opened['session'])
    assert report['ok'], report.get('error')
    return report


def _archive_path(bridge, record):
    return Path(bridge.workdir) / '方案' / record['file']


def test_snapshot_plan_round_trip_after_restart_preserves_result_pairs_and_evidence(setup):
    state, bridge = setup, setup['bridge']
    report = _run(state)
    record = _save(bridge, report)
    assert bridge.comparison_plans()['plans'][0]['file'] == record['file']
    archive = load_plan(Path(bridge.workdir) / '方案', record['file'])
    assert archive['inputs']['pairs'] == state['pairs']
    assert archive['inputs']['excluded_rows'] == ['腰部支撑']
    assert archive['inputs']['right']['evidence']['raw'] == json.loads(state['raw'].read_text())
    assert archive['result'] == {key: value for key, value in report.items()
                                 if key not in ('md_path', 'comparison_id')}
    bridge.shutdown()
    restarted = state['new_bridge']()
    opened = restarted.open_comparison_plan(record['file'])
    assert opened['ok'], opened.get('error')
    assert opened['name'] == record['name']
    assert isinstance(opened['app_version'], str) and opened['app_version']
    assert opened['result']['comparison_id'] != report['comparison_id']
    assert 'md_path' not in opened['result']
    assert opened['result']['groups'] == report['groups']
    assert opened['result']['review'] == report['review']
    assert opened['result']['evidence'] == report['evidence']
    assert _rerun(restarted, opened)['groups'] == report['groups']
    seat = next(item for item in opened['result']['evidence'] if item['no'] == 35)
    assert '腰部支撑' in json.dumps(seat['right']['rows'], ensure_ascii=False)
    assert any('8向' in line for line in seat['right']['calculation'])
    assert all(path.read_bytes() == original for path, original in state['files'].items())


def test_open_and_recalculate_without_original_files_or_current_rules(setup, monkeypatch):
    state, bridge = setup, setup['bridge']
    original = _run(state)
    record = _save(bridge, original)
    state['left'].unlink()
    state['right'].unlink()
    restarted = state['new_bridge']()
    next(rule for rule in restarted.rules.exemptions['rules'] if rule['id'] == 'range_micro')['bands_km'] = [[0, 10000]]
    next(item for item in restarted.rules.checklist['items'] if item['no'] == 40)['name'] = '当前改名'
    restarted.rules._index()
    changed_valuation = valuer.default_valuation(restarted.rules)
    next(item for item in changed_valuation['items'] if item['no'] == 40)['val'] = 99999
    assert restarted.save_current_valuation(changed_valuation)['ok']
    global_before = restarted.rules.to_snapshot()
    current_before = state['valuation'].read_bytes()
    raw_before = state['raw'].read_bytes()
    monkeypatch.setitem(valuer.DEFAULT_DYNAMIC_PARAMS[35], 'electric_bonus', 90000)
    opened = restarted.open_comparison_plan(record['file'])
    assert opened['ok'], opened.get('error')
    assert opened['result']['groups'] == original['groups']
    assert _rerun(restarted, opened)['groups'] == original['groups']
    assert restarted.rules.to_snapshot() == global_before
    assert state['valuation'].read_bytes() == current_before
    assert state['raw'].read_bytes() == raw_before
    assert not state['left'].exists() and not state['right'].exists()


def test_editable_work_copy_recalculates_then_saves_new_plan_without_changing_archive(setup):
    state, bridge = setup, setup['bridge']
    original = _run(state)
    record = _save(bridge, original)
    archive_path = _archive_path(bridge, record)
    archive_before = archive_path.read_bytes()
    opened = bridge.open_comparison_plan(record['file'])
    assert opened['ok'], opened.get('error')
    left_path = Path(opened['paths']['left'])
    left = json.loads(left_path.read_text())
    next(cell for cell in left['cells'] if cell['no'] == 40)['values']['左版'] = '✕'
    atomic_write_text(left_path, json.dumps(left, ensure_ascii=False))
    changed = _rerun(bridge, opened)
    assert changed['groups'][0]['valuation']['config_adv'] == original['groups'][0]['valuation']['config_adv']-2600
    second = _save(bridge, changed)
    assert second['file'] != record['file']
    assert archive_path.read_bytes() == archive_before
    assert all(path.read_bytes() == before for path, before in state['files'].items())
    second_plan = load_plan(Path(bridge.workdir) / '方案', second['file'])
    assert next(cell for cell in second_plan['inputs']['left']['cells'] if cell['no'] == 40)['values']['左版'] == '✕'


def test_result_tokens_save_their_own_inputs_not_last_completed_comparison(setup):
    state, bridge = setup, setup['bridge']
    first = _run(state)
    first_groups = copy.deepcopy(first['groups'])
    second_pairs = copy.deepcopy(state['pairs'])
    second_pairs[0]['comp_floor_price'] = 105000
    second = _run(state, pairs=second_pairs)
    first['groups'][0]['valuation']['overall'] = 99999  # Browser copies are not the authority.
    a = _save(bridge, first, '旧结果')
    b = _save(bridge, second, '新结果')
    root = Path(bridge.workdir) / '方案'
    assert load_plan(root, a['file'])['result']['groups'] == first_groups
    assert load_plan(root, a['file'])['inputs']['pairs'] == state['pairs']
    assert load_plan(root, b['file'])['inputs']['pairs'] == second_pairs
    assert load_plan(root, b['file'])['result']['groups'][0]['valuation']['overall'] == first_groups[0]['valuation']['overall']+4000


def test_ladder_on_left_is_preserved_and_recalculates_without_snapshot_conversion(setup):
    state, bridge = setup, setup['bridge']
    left = ladder({1: '500km', 35: '主驾6向电调+副驾4向手调', 40: '热泵空调'}, '左版', '本品')
    left.evidence = {'custom': {'text': '手工修正过的来源'}}
    left.save(state['left'])
    report = bridge.run_diff(str(state['left']), str(state['right']), state['pairs'], left_is_competitor=True)
    assert report['ok'], report.get('error')
    record = _save(bridge, report)
    opened = bridge.open_comparison_plan(record['file'])
    assert opened['ok'], opened.get('error')
    assert opened['inputs']['left_kind'] == 'ladder'
    assert opened['inputs']['left']['evidence'] == left.evidence
    assert _rerun(bridge, opened)['groups'] == report['groups']


def test_reopened_report_exports_without_original_markdown_path(setup, tmp_path):
    state, bridge = setup, setup['bridge']
    record = _save(bridge, _run(state))
    opened = bridge.open_comparison_plan(record['file'])
    assert opened['ok'] and 'md_path' not in opened['result']
    bridge.save_file_dialog = lambda name, *_: str(tmp_path / name)
    excel = bridge.export_excel('diff', opened['result'])
    assert excel['ok'], excel.get('error')
    assert Path(excel['path']).is_file()
    markdown = tmp_path / '重新导出.md'
    assert bridge.write_text_file(str(markdown), opened['result']['md'])['ok']
    assert markdown.read_text(encoding='utf-8') == opened['result']['md']


def test_expired_result_token_cannot_save_latest_result_by_accident(setup):
    state, bridge = setup, setup['bridge']
    first = _run(state)
    for _ in range(8):
        latest = _run(state)
    assert not bridge.save_comparison_plan('过期结果', first['comparison_id'])['ok']
    saved = _save(bridge, latest, '最新结果')
    assert bridge.comparison_plans()['plans'][0]['file'] == saved['file']


@pytest.mark.parametrize('token', ['', '../any-token', None, [], {}])
def test_invalid_result_token_cannot_save_or_overwrite_a_plan(setup, token):
    bridge = setup['bridge']
    before = list((Path(bridge.workdir) / '方案').iterdir())
    assert not bridge.save_comparison_plan('非法保存', token)['ok']
    assert list((Path(bridge.workdir) / '方案').iterdir()) == before


@pytest.mark.parametrize('filename', ['../left.json', '/tmp/left.json', '..\\left.json', 'plan.txt'])
def test_invalid_plan_filename_is_rejected_by_bridge(setup, filename):
    bridge = setup['bridge']
    assert not bridge.open_comparison_plan(filename)['ok']
    assert not (Path(bridge.workdir) / '方案' / '工作副本').exists()


def test_plan_session_cannot_be_used_with_foreign_paths_or_other_bridge(setup):
    state, bridge = setup, setup['bridge']
    record = _save(bridge, _run(state))
    opened = bridge.open_comparison_plan(record['file'])
    assert opened['ok']
    paths = opened['paths']
    for changed in ('left', 'right', 'valuation'):
        candidate = dict(paths)
        candidate[changed] = str(state['left'])
        answer = bridge.run_diff(candidate['left'], candidate['right'], opened['inputs']['pairs'],
                                 candidate['valuation'], False, opened['session'])
        assert not answer['ok'] and '输入已变更' in answer['error']
    assert not bridge.run_diff(paths['left'], paths['right'], opened['inputs']['pairs'],
                               paths['valuation'], False, '../session')['ok']
    another_bridge = state['new_bridge']()
    assert not another_bridge.run_diff(paths['left'], paths['right'], opened['inputs']['pairs'],
                                       paths['valuation'], False, opened['session'])['ok']


def test_work_copy_symlink_cannot_escape_plan_session(setup):
    state, bridge = setup, setup['bridge']
    record = _save(bridge, _run(state))
    opened = bridge.open_comparison_plan(record['file'])
    assert opened['ok']
    paths = opened['paths']
    copied_right = Path(paths['right'])
    copied_right.unlink()
    copied_right.symlink_to(state['right'])
    answer = bridge.run_diff(paths['left'], paths['right'], opened['inputs']['pairs'],
                             paths['valuation'], False, opened['session'])
    assert not answer['ok']
    assert state['right'].read_bytes() == state['files'][state['right']]


def test_work_copy_parent_directory_symlink_cannot_escape_plan_session(setup, tmp_path):
    state, bridge = setup, setup['bridge']
    record = _save(bridge, _run(state))
    opened = bridge.open_comparison_plan(record['file'])
    assert opened['ok']
    paths = opened['paths']
    directory = Path(paths['left']).parent
    relocated = tmp_path / 'outside-session'
    directory.rename(relocated)
    directory.symlink_to(relocated, target_is_directory=True)
    assert not any(Path(path).is_symlink() for path in paths.values())
    before = {path: path.read_bytes() for path in relocated.iterdir()}
    archive = _archive_path(bridge, record)
    archive_before = archive.read_bytes()
    answer = bridge.run_diff(paths['left'], paths['right'], opened['inputs']['pairs'],
                             paths['valuation'], False, opened['session'])
    assert not answer['ok'] and '工作副本路径无效' in answer['error']
    assert {path: path.read_bytes() for path in relocated.iterdir()} == before
    assert archive.read_bytes() == archive_before


def test_recalculated_plan_keeps_saved_display_preferences_not_changed_global_defaults(setup):
    state, bridge = setup, setup['bridge']
    record = _save(bridge, _run(state))
    atomic_write_text(state['preferences'], json.dumps({'excluded_rows': ['新全局隐藏项']}))
    preferences_before = state['preferences'].read_bytes()
    opened = bridge.open_comparison_plan(record['file'])
    assert opened['ok']
    recalculated = _rerun(bridge, opened)
    second = _save(bridge, recalculated)
    plan = load_plan(Path(bridge.workdir) / '方案', second['file'])
    assert plan['inputs']['excluded_rows'] == ['腰部支撑']
    assert state['preferences'].read_bytes() == preferences_before
