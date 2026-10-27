import sys
from types import SimpleNamespace

import pytest

from api.bridge import Bridge


@pytest.mark.parametrize('modern', [False, True], ids=['pywebview-5', 'pywebview-6'])
@pytest.mark.parametrize('method,result,expected', [
    ('open_file_dialog', ('/tmp/原始配置.json',), '/tmp/原始配置.json'),
    ('open_file_dialog', None, None),
    ('save_file_dialog', '/tmp/分析结果.xlsx', '/tmp/分析结果.xlsx'),
    ('save_file_dialog', ('/tmp/分析结果.xlsx',), '/tmp/分析结果.xlsx'),
    ('save_file_dialog', None, None),
])
def test_file_dialogs_use_supported_constants_and_keep_paths_and_options(monkeypatch, modern, method, result, expected):
    calls = []

    def create_file_dialog(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    class Webview(SimpleNamespace):
        def __getattr__(self, name):
            if modern and name in ('OPEN_DIALOG', 'SAVE_DIALOG'):
                raise AssertionError('Modern SDK must not access deprecated dialog constants')
            raise AttributeError(name)

    webview = Webview(windows=[SimpleNamespace(create_file_dialog=create_file_dialog)])
    if modern:
        webview.FileDialog = SimpleNamespace(OPEN='modern-open', SAVE='modern-save')
    else:
        webview.OPEN_DIALOG, webview.SAVE_DIALOG = 'legacy-open', 'legacy-save'
    monkeypatch.setitem(sys.modules, 'webview', webview)
    bridge = Bridge.__new__(Bridge)
    file_types = ['配置文件 (*.json)', '所有文件 (*.*)']
    if method == 'open_file_dialog':
        actual = bridge.open_file_dialog(file_types)
        dialog_type = webview.FileDialog.OPEN if modern else webview.OPEN_DIALOG
        options = {'allow_multiple': False, 'file_types': tuple(file_types)}
    else:
        actual = bridge.save_file_dialog('分析结果.xlsx', file_types)
        dialog_type = webview.FileDialog.SAVE if modern else webview.SAVE_DIALOG
        options = {'save_filename': '分析结果.xlsx', 'file_types': tuple(file_types)}
    assert actual == expected
    assert calls == [((dialog_type,), options)]
