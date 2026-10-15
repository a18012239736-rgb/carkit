"""Product options survive imports/plans without entering standard valuation."""
import copy
import json
from pathlib import Path

import pytest

from api.bridge import Bridge
from engine.comparison_plan import load_plan
from engine.models import Ladder, Snapshot
from engine.ppt_import import _apply, make_snapshot
from engine.rules import Rules
from engine.seat_functions import empty


def _draft():
    return {
        'model': '测试本品', 'source': 'options-test.pptx', 'page': 1,
        'price_kind': '指导价',
        'columns': [
            {'name': '基础型', 'price': 9, 'text': '500km续航\n360影像'},
            {'name': '舒适型', 'base': '基础型', 'price': 10, 'text': ''},
        ],
    }


def _values(snapshot, no):
    return next(cell['values'] for cell in snapshot.cells if cell['no'] == no)


def _options_without_markers(options):
    """The semantic option is its description, not the import marker."""
    return [str(text).lstrip('○').replace('选装', '').replace('选配', '').strip(' ：:')
            for text in options]


def test_legacy_snapshot_and_ladder_without_options_still_load():
    snapshot = Snapshot.from_dict({'model': '旧本品', 'trims': [{'name': '旧版'}], 'cells': []})
    ladder = Ladder.from_dict({'model': '旧竞品', 'trims': [{'name': '旧版'}], 'items': []})
    assert snapshot.options == ladder.options == {}
    assert snapshot.to_ladder(Rules().items).options == {}


def test_options_round_trip_as_display_only_snapshot_and_ladder_data():
    snapshot = make_snapshot(_draft())
    original_items = copy.deepcopy(snapshot.to_ladder(Rules().items).items)
    snapshot.options = {'基础型': ['800V高压平台', '540影像'], '舒适型': ['真皮座椅']}
    loaded = Snapshot.from_dict(json.loads(snapshot.to_json()))
    ladder = loaded.to_ladder(Rules().items)
    assert loaded.options == ladder.options == snapshot.options
    assert ladder.items == original_items
    assert Ladder.from_dict(json.loads(ladder.to_json())).options == snapshot.options


@pytest.mark.parametrize('options,expected', [
    ('540°透明底盘\n真皮座椅', ['540°透明底盘', '真皮座椅']),
    (['540°透明底盘', '真皮座椅'], ['540°透明底盘', '真皮座椅']),
])
def test_explicit_per_trim_options_accept_multiline_text_or_list(options, expected):
    draft = _draft()
    draft['columns'][0]['options'] = options
    snapshot = make_snapshot(draft)
    assert _options_without_markers(snapshot.options['基础型']) == expected
    assert not snapshot.options.get('舒适型')
    assert _values(snapshot, 7) == {'基础型': '360影像', '舒适型': '360影像'}


@pytest.mark.parametrize('marker', ['选装', '选配', '○'])
def test_optional_imaging_line_never_overwrites_inherited_standard_imaging(marker):
    draft = _draft()
    draft['columns'][1]['text'] = marker + '540°透明底盘'
    snapshot = make_snapshot(draft)
    assert _values(snapshot, 7) == {'基础型': '360影像', '舒适型': '360影像'}
    assert _options_without_markers(snapshot.options['舒适型']) == ['540°透明底盘']
    assert not any(pending.get('no') == 7 for pending in snapshot.pending)


@pytest.mark.parametrize('text', ['360影像+选装540°透明底盘', '360影像+○540度透明底盘'])
def test_standard_and_optional_equipment_can_coexist_in_same_line(text):
    draft = _draft()
    draft['columns'][0]['text'] = text
    snapshot = make_snapshot(draft)
    assert _values(snapshot, 7)['基础型'] == '360影像'
    options = _options_without_markers(snapshot.options['基础型'])
    assert len(options) == 1 and '540' in options[0] and '透明底盘' in options[0]


def test_options_are_independent_per_trim_without_implicit_inheritance():
    draft = _draft()
    draft['columns'][0]['text'] += '\n选装540°透明底盘'
    draft['columns'][1]['options'] = '真皮座椅'
    draft['columns'].append({'name': '豪华型', 'base': '舒适型', 'text': ''})
    snapshot = make_snapshot(draft)
    assert _options_without_markers(snapshot.options['基础型']) == ['540°透明底盘']
    assert _options_without_markers(snapshot.options['舒适型']) == ['真皮座椅']
    assert not snapshot.options.get('豪华型')
    assert set(_values(snapshot, 7).values()) == {'360影像'}


@pytest.mark.parametrize('text,standard_imaging,options', [
    ('360影像（选装540°透明底盘）', '360影像', ['540°透明底盘']),
    ('540°透明底盘（选装）', '✕', ['540°透明底盘']),
    ('选装配置：\n热泵空调\n540°透明底盘\n标配配置：\n360影像',
     '360影像', ['热泵空调', '540°透明底盘']),
    ('驾驶辅助影像：○', '✕', ['驾驶辅助影像']),
])
def test_option_parentheses_sections_and_table_labels_keep_standard_status(text, standard_imaging, options):
    draft = _draft()
    draft['columns'][0]['text'] = text
    snapshot = make_snapshot(draft)
    assert _values(snapshot, 7)['基础型'] == standard_imaging
    assert _options_without_markers(snapshot.options['基础型']) == options
    assert _values(snapshot, 40)['基础型'] == '✕'


@pytest.mark.parametrize('separator', ['；', ';', '、'])
def test_standard_compound_seat_functions_keep_original_apply_semantics(separator):
    text = '前排座椅通风' + separator + '加热'
    expected = {36: empty()}
    _apply(text, expected, {}, [])
    draft = _draft()
    draft['columns'][0]['text'] = text
    snapshot = make_snapshot(draft)
    actual = _values(snapshot, 36)['基础型']
    assert actual == expected[36]
    assert all(actual[seat + feature] == '●'
               for seat in ('主驾', '副驾') for feature in ('通风', '加热'))
    assert not snapshot.options.get('基础型')


@pytest.mark.parametrize('invalid_options', [
    {'不存在的版型': ['540影像']},
    {'基础型': [500]},
])
def test_invalid_option_trim_or_non_text_is_rejected_without_overwriting_snapshot(tmp_path, invalid_options):
    bridge = Bridge(str(tmp_path / 'work'))
    try:
        snapshot = make_snapshot(_draft())
        path = tmp_path / 'unchanged.json'
        snapshot.save(path)
        original = path.read_bytes()
        data = json.loads(snapshot.to_json())
        data['options'] = invalid_options
        assert not bridge.save_snapshot(str(path), data)['ok']
        assert path.read_bytes() == original
        assert not bridge.save_ppt_snapshot(data, True)['ok']
        assert not list((Path(bridge.workdir) / '快照').glob('*'))
        with pytest.raises(ValueError):
            Snapshot.from_dict(data)
        ladder_data = snapshot.to_ladder(bridge.rules.items).to_dict()
        ladder_data['options'] = invalid_options
        with pytest.raises(ValueError):
            Ladder.from_dict(ladder_data)
    finally:
        bridge.shutdown()


def test_preview_confirm_reload_diff_and_saved_plan_preserve_options_without_price_changes(tmp_path):
    bridge = Bridge(str(tmp_path / 'work'))
    try:
        draft = _draft()
        draft['columns'][0]['options'] = ['540°透明底盘', '800V高压平台']
        draft['columns'][1]['text'] = '选装热泵空调'
        preview = bridge.ppt_preview(draft)
        assert preview['ok'], preview.get('error')
        assert not bridge.save_ppt_snapshot(preview['snapshot'], False)['ok']
        saved = bridge.save_ppt_snapshot(preview['snapshot'], True)
        assert saved['ok'], saved.get('error')
        reloaded = bridge.load_snapshot(saved['path'])
        assert reloaded['ok'], reloaded.get('error')
        source = Snapshot.from_dict(reloaded['snapshot'])
        assert _options_without_markers(source.options['基础型']) == ['540°透明底盘', '800V高压平台']
        assert _options_without_markers(source.options['舒适型']) == ['热泵空调']
        assert _values(source, 7)['基础型'] == '360影像'
        assert _values(source, 3)['基础型'] == _values(source, 40)['舒适型'] == '✕'

        right = source.to_ladder(bridge.rules.items)
        right.side, right.model = 'competitor', '测试竞品'
        right.trims = [{'name': '竞品基础版', 'price_guide': 9.5},
                       {'name': '竞品舒适版', 'price_guide': 10.5}]
        right.options = {'竞品基础版': ['车顶行李架'], '竞品舒适版': ['座椅按摩']}
        right_path = tmp_path / 'right.json'
        right.save(right_path)
        baseline_source = Snapshot.from_dict(reloaded['snapshot'])
        baseline_source.options = {}
        baseline_path = tmp_path / 'baseline-left.json'
        baseline_source.save(baseline_path)
        baseline_right = copy.deepcopy(right)
        baseline_right.options = {}
        baseline_right_path = tmp_path / 'baseline-right.json'
        baseline_right.save(baseline_right_path)
        pairs = [
            {'self_trim': '基础型', 'comp_trim': '竞品基础版',
             'self_floor_price': 80000, 'comp_floor_price': 85000},
            {'self_trim': '舒适型', 'comp_trim': '竞品舒适版',
             'self_floor_price': 90000, 'comp_floor_price': 95000},
        ]
        baseline = bridge.run_diff(str(baseline_path), str(baseline_right_path), pairs)
        report = bridge.run_diff(saved['path'], str(right_path), pairs)
        assert baseline['ok'], baseline.get('error')
        assert report['ok'], report.get('error')
        assert report['cells'] == baseline['cells']
        assert report['missing_valuation'] == baseline['missing_valuation']
        for index, group in enumerate(report['groups']):
            assert group['self_options'] == source.options[pairs[index]['self_trim']]
            assert group['comp_options'] == right.options[pairs[index]['comp_trim']]
            assert {key: value for key, value in group.items()
                    if key not in ('self_options', 'comp_options')} == baseline['groups'][index]
            assert 'self_options' not in baseline['groups'][index]
            assert 'comp_options' not in baseline['groups'][index]

        plan = bridge.save_comparison_plan('本品选装展示方案', report['comparison_id'])
        assert plan['ok'], plan.get('error')
        stored = load_plan(Path(bridge.workdir) / '方案', plan['file'])
        assert stored['inputs']['left']['options'] == source.options
        assert stored['inputs']['right']['options'] == right.options
        from engine.comparison_plan import validate_plan
        for invalid in ('不是列表', [123]):
            malformed = copy.deepcopy(stored)
            malformed['result']['groups'][0]['self_options'] = invalid
            with pytest.raises(ValueError, match='选装描述'):
                validate_plan(malformed)
        opened = bridge.open_comparison_plan(plan['file'])
        assert opened['ok'], opened.get('error')
        assert opened['result']['groups'] == report['groups']
        assert Snapshot.load(opened['paths']['left']).options == source.options
        assert Ladder.load(opened['paths']['right']).options == right.options
        rerun = bridge.run_diff(opened['paths']['left'], opened['paths']['right'],
                                opened['inputs']['pairs'], opened['paths']['valuation'],
                                False, opened['session'])
        assert rerun['ok'], rerun.get('error')
        assert rerun['groups'] == report['groups']
        assert rerun['cells'] == baseline['cells']
    finally:
        bridge.shutdown()


def test_native_ppt_table_preserves_standard_and_optional_rows_separately():
    from xml.etree import ElementTree as ET
    from engine.ppt_import import NS, _parse_native_table
    tag = lambda name: '{'+NS['a']+'}'+name
    table = ET.Element(tag('tbl'))
    for values in [
        ['版型', '基础型', '舒适型'],
        ['驾驶辅助影像', '360影像', '540°透明底盘'],
        ['选装配置', 'HUD', '个性车漆\n电动尾门'],
    ]:
        row = ET.SubElement(table, tag('tr'))
        for value in values:
            cell = ET.SubElement(row, tag('tc'))
            for line in value.splitlines():
                ET.SubElement(ET.SubElement(cell, tag('p')), tag('t')).text = line
    draft = _parse_native_table(table)
    draft['model'] = '表格测试本品'
    snapshot = make_snapshot(draft)
    assert _values(snapshot, 7) == {'基础型': '360影像', '舒适型': '540影像'}
    assert snapshot.options == {'基础型': ['HUD'], '舒适型': ['个性车漆', '电动尾门']}
    assert set(_values(snapshot, 13).values()) == {'✕'}
