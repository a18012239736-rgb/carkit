import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import app
from api.bridge import Bridge
from engine import stage_one
from engine.models import Cell, RawRow, RawTable, Trim


def _raw():
    return RawTable(model='测试车', trims=[Trim(0, '基础', price_guide=10)],
                    rows=[RawRow('CLTC纯电续航里程(km)', [Cell(text='500')])])


def test_acquisition_entry_points_keep_the_same_browser_thread_and_response(tmp_path, monkeypatch):
    bridge = Bridge(str(tmp_path))
    calls = []

    def operation(*args):
        calls.append((threading.get_ident(), args))
        return {'needs_browser': True, 'message': '请完成验证'}

    try:
        for method, action, args, expected in [
            ('stage_search', 'search', ('测试车', '2026'), ('测试车', '2026')),
            ('stage_choose_series', 'fetch', ('123',), ('123',)),
            ('stage_apply_filters', 'apply_filters', (), ({},)),
            ('stage_continue', 'resume', (), ()),
        ]:
            monkeypatch.setattr(bridge.acquirer, action, operation)
            assert getattr(bridge, method)(*args) == {
                'ok': True, 'needs_browser': True, 'message': '请完成验证',
            }
            assert calls[-1][1] == expected
        assert len({thread for thread, _ in calls}) == 1
        assert calls[0][0] != threading.get_ident()
    finally:
        bridge.shutdown()


def test_acquisition_saves_complete_capture_and_preserves_it_on_later_failure(tmp_path, monkeypatch):
    bridge = Bridge(str(tmp_path))
    try:
        monkeypatch.setattr('engine.acquire.Acquirer.resume', lambda self: {'raw': _raw().to_dict()})
        result = bridge.stage_continue()
        assert result['ok'] and result['complete']
        assert RawTable.load(result['raw_path']).model == '测试车'
        captured = bridge.stage_raw

        def fail(self):
            raise RuntimeError('读取失败')

        monkeypatch.setattr('engine.acquire.Acquirer.resume', fail)
        assert bridge.stage_continue() == {'ok': False, 'error': '读取失败'}
        assert bridge.stage_raw is captured
        assert len(list((tmp_path / 'raw').glob('*.json'))) == 1
    finally:
        bridge.shutdown()


def test_shutdown_releases_browser_once_when_called_repeatedly(tmp_path, monkeypatch):
    bridge = Bridge(str(tmp_path))
    closed = []
    monkeypatch.setattr('engine.acquire.Acquirer.close', lambda self: closed.append(threading.get_ident()))
    bridge.shutdown()
    bridge.shutdown()
    assert len(closed) == 1
    assert closed[0] != threading.get_ident()
    with pytest.raises(RuntimeError):
        bridge._acquire_executor.submit(lambda: None)


@pytest.mark.parametrize('failure', ['window', 'start'])
def test_app_releases_browser_when_native_startup_fails(tmp_path, monkeypatch, failure):
    bridge = Bridge(str(tmp_path))
    closed = []
    monkeypatch.setattr('engine.acquire.Acquirer.close', lambda self: closed.append(True))
    monkeypatch.setattr('api.bridge.Bridge', lambda workdir: bridge)
    monkeypatch.setattr(app, 'default_workdir', lambda: str(tmp_path))

    class Event:
        def __iadd__(self, handler):
            return self

    def fail(*args, **kwargs):
        raise RuntimeError('模拟窗口启动失败')

    window = SimpleNamespace(events=SimpleNamespace(closed=Event(), before_show=Event()))
    webview = SimpleNamespace(create_window=fail if failure == 'window' else lambda *a, **k: window,
                              start=fail)
    monkeypatch.setitem(sys.modules, 'webview', webview)
    with pytest.raises(RuntimeError, match='窗口启动失败'):
        app.main()
    assert closed == [True]


def test_markdown_exports_only_replace_the_file_suffix(tmp_path):
    bridge = Bridge(str(tmp_path / '工作.json数据'))
    try:
        source = tmp_path / 'raw.json'
        _raw().save(source)
        result = bridge.build_ladder(str(source))
        assert result['ok'], result
        expected = Path(result['path']).with_suffix('.md')
        assert Path(result['md_path']) == expected
        assert expected.is_file()
        rerendered = bridge.build_ladder_md_only(result['path'])
        assert rerendered == {'ok': True, 'path': str(expected)}
    finally:
        bridge.shutdown()


@pytest.mark.parametrize('plan', [[None], ['0'], [{'target': 0}], [{'target': True, 'base': None}]])
def test_invalid_stage_plans_fail_validation_before_rendering(plan):
    with pytest.raises(ValueError, match='版型|基准'):
        stage_one.validate_plan(_raw(), plan)


def test_seat_compaction_preserves_source_position_and_comparison_parentheses():
    items = [
        ('其他配置', 'HUD'),
        ('前排座椅功能', '主驾座椅加热+副驾座椅加热+独立腿托'),
        ('座椅备注', '主驾座椅通风（无）'),
        ('后排座椅功能', '后排座椅按摩'),
    ]
    assert stage_one._compact_items(items, None) == [
        'HUD', '前排加热+后排按摩', '独立腿托', '主驾座椅通风（无）',
    ]
