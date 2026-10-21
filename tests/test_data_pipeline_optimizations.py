import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from engine import acquire, scrape
from engine.models import Snapshot, ValuationItem, ValuationTable
from engine.snapshot import parse_snapshot_md, resolve


def test_markdown_snapshot_keeps_trim_columns_through_resolution(tmp_path):
    path = tmp_path / '快照.md'
    path.write_text('''# 覆盖率对账表
|#|配置项| 基础 | 舒适 |定稿依据|
|---|---|---|---|---|
|40|热泵空调|●热泵空调|●|配置表|
|30|HUD|✕|同基础|项目定义|

后续说明
|40|无关表格|无|无|不应导入|
''', encoding='utf-8')
    snapshot = resolve(parse_snapshot_md(path))
    ladder = snapshot.to_ladder([{'no': 40, 'name': '热泵空调'}, {'no': 30, 'name': 'HUD'}])
    assert ladder.trims == [{'name': '基础', 'price_guide': None}, {'name': '舒适', 'price_guide': None}]
    assert ladder.item(40).values == ['●热泵空调', '●热泵空调']
    assert ladder.item(40).note == '配置表'
    assert ladder.item(30).values == ['✕', '✕']


def test_empty_snapshot_can_be_resolved_and_converted():
    snapshot = resolve(Snapshot(cells=[{'no': 40, 'values': {}}]))
    ladder = snapshot.to_ladder([{'no': 40, 'name': '热泵空调'}, {'no': 32, 'name': 'USB'}])
    assert ladder.trims == []
    assert [item.values for item in ladder.items] == [[], []]


def test_snapshot_keeps_composite_fields_that_only_later_trims_have():
    snapshot = Snapshot(trims=[{'name': '基础'}, {'name': '舒适'}, {'name': '豪华'}], cells=[
        {'no': 36, 'values': {'基础': '✕', '舒适': {'主驾通风': '●'}, '豪华': {'副驾加热': '●'}}},
    ])
    item = snapshot.to_ladder([{'no': 36, 'name': '座椅功能'}]).item(36)
    assert item.subs == [
        {'sub': '主驾通风', 'values': ['✕', '●', '✕']},
        {'sub': '副驾加热', 'values': ['✕', '✕', '●']},
    ]


def test_snapshot_dictionary_is_independent_and_matches_json():
    snapshot = Snapshot(trims=[{'name': '基础'}], options={'基础': ['HUD']})
    data = snapshot.to_dict()
    assert data == json.loads(snapshot.to_json())
    data['trims'][0]['name'] = '修改'
    data['options']['基础'].append('天窗')
    assert snapshot.trims == [{'name': '基础'}]
    assert snapshot.options == {'基础': ['HUD']}


def test_valuation_lookup_reflects_edits_and_keeps_dataclass_copy_semantics():
    item = ValuationItem(no=40, name='热泵空调', params={'amount': 1000})
    table = ValuationTable(items=[ValuationItem(no=1, name='续航'), item])
    found = table.item(40)
    found['params']['amount'] = 2000
    assert item.params['amount'] == 1000
    item.params['amount'] = 3000
    assert table.item(40)['params']['amount'] == 3000
    table.items = [{'no': 40, 'name': '新规则'}]
    assert table.item(40) is table.items[0]
    assert table.item(99) is None


def _playwright(monkeypatch, runtime):
    module = ModuleType('playwright.sync_api')
    module.sync_playwright = lambda: SimpleNamespace(start=lambda: runtime)
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', module)


@pytest.mark.parametrize('message', ['页面创建失败', ''])
def test_acquirer_closes_failed_channel_before_trying_next(monkeypatch, message):
    events = []

    def fail_page(**kwargs):
        raise RuntimeError(message)

    first = SimpleNamespace(new_page=fail_page, close=lambda: events.append('close first'))
    page = object()
    second = SimpleNamespace(new_page=lambda **kwargs: page, close=lambda: events.append('close second'))

    def launch(channel, **kwargs):
        events.append(channel)
        return first if channel == 'msedge' else second

    runtime = SimpleNamespace(chromium=SimpleNamespace(launch=launch), stop=lambda: events.append('stop'))
    _playwright(monkeypatch, runtime)
    acquirer = acquire.Acquirer()
    try:
        acquirer.start()
        assert acquirer.page is page
        assert events == ['msedge', 'close first', 'chrome']
    finally:
        acquirer.close()
    assert events[-2:] == ['close second', 'stop']


def test_legacy_open_replaces_session_and_closes_failed_navigation(monkeypatch):
    events = []

    def fail_navigation(*args, **kwargs):
        raise RuntimeError('网页加载失败')

    page = SimpleNamespace(goto=fail_navigation)
    browser = SimpleNamespace(new_page=lambda: page, close=lambda: events.append('new browser'))
    runtime = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: browser),
                              stop=lambda: events.append('new runtime'))
    _playwright(monkeypatch, runtime)
    monkeypatch.setattr(scrape, '_SESSION', {
        'browser': SimpleNamespace(close=lambda: events.append('old browser')),
        'pw': SimpleNamespace(stop=lambda: events.append('old runtime')),
        'page': object(), 'series_id': '1111',
    })
    with pytest.raises(RuntimeError, match='网页加载失败'):
        scrape.scrape_open('2222')
    assert events == ['old browser', 'old runtime', 'new browser', 'new runtime']
    assert scrape._SESSION == {'pw': None, 'browser': None, 'page': None, 'series_id': ''}


@pytest.mark.parametrize('failure', ['wait', 'evaluate', None])
def test_legacy_capture_releases_resources_and_preserves_series_id(monkeypatch, failure):
    events = []

    def wait(*args, **kwargs):
        if failure == 'wait':
            raise RuntimeError('等待失败')

    def evaluate(*args):
        if failure == 'evaluate':
            raise RuntimeError('提取失败')
        return {'headers': ['示例车 2027款 基础版'],
                'rows': [{'n': '厂商指导价(元)', 'v': ['10.99万']}]}

    monkeypatch.setattr(scrape, '_SESSION', {
        'browser': SimpleNamespace(close=lambda: events.append('browser')),
        'pw': SimpleNamespace(stop=lambda: events.append('runtime')),
        'page': SimpleNamespace(wait_for_selector=wait, evaluate=evaluate), 'series_id': '8241',
    })
    if failure:
        with pytest.raises(RuntimeError, match='失败'):
            scrape.scrape_capture()
    else:
        assert scrape.scrape_capture().series_id == '8241'
    assert events == ['browser', 'runtime']
    assert scrape._SESSION == {'pw': None, 'browser': None, 'page': None, 'series_id': ''}
