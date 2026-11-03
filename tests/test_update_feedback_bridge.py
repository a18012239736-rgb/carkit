"""Update and feedback entry points never execute downloads or submit public issues."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.bridge import Bridge
from engine import __version__
from engine.updater import RELEASES_URL


@pytest.fixture
def bridge(tmp_path):
    instance = Bridge(str(tmp_path / 'work'))
    yield instance
    instance.shutdown()


def test_update_save_dialog_cancel_and_errors_keep_existing_data(bridge, tmp_path, monkeypatch):
    original = Path(bridge.workdir) / '方案' / '已保存.json'
    original.write_text('已保存方案', encoding='utf-8')
    downloads = []
    bridge._updater = SimpleNamespace(
        _release={'can_download': True, 'asset_name': 'carkit-0.2.4.exe'},
        download_to=lambda path: downloads.append(path) or {'ok': True, 'path': path})
    choices = []

    def dialog(name, types):
        choices.append((name, types))
        return None

    monkeypatch.setattr(bridge, 'save_file_dialog', dialog)
    assert bridge.download_app_update() == {'ok': True, 'cancelled': True}
    assert choices == [('carkit-0.2.4.exe', ['Windows 程序 (*.exe)'])]
    monkeypatch.setattr(bridge, 'save_file_dialog', lambda *args: {'error': '窗口错误'})
    assert bridge.download_app_update() == {'ok': False, 'error': '窗口错误'}
    assert downloads == []
    destination = str(tmp_path / 'carkit-new.exe')
    monkeypatch.setattr(bridge, 'save_file_dialog', lambda *args: destination)
    assert bridge.download_app_update() == {'ok': True, 'path': destination}
    assert downloads == [destination]
    assert original.read_text(encoding='utf-8') == '已保存方案'


def test_update_check_and_folder_are_bound_to_backend_state(bridge, tmp_path, monkeypatch):
    checked = []
    bridge._updater = SimpleNamespace(check=lambda: checked.append(True) or {'ok': True},
                                     status=lambda: {'state': 'idle'})
    assert bridge.check_app_update() == {'ok': True}
    bridge._update_download_lock.acquire()
    try:
        assert not bridge.check_app_update()['ok']
        assert not bridge.download_app_update()['ok']
    finally:
        bridge._update_download_lock.release()
    assert checked == [True]
    assert not bridge.open_app_update_folder()['ok']
    downloaded = tmp_path / 'carkit-new.exe'
    downloaded.write_bytes(b'MZ-test')
    bridge._updater.status = lambda: {'state': 'complete', 'path': str(downloaded)}
    folders = []
    monkeypatch.setattr(bridge, '_open_folder', lambda path: folders.append(path) or {'ok': True})
    assert bridge.open_app_update_folder()['ok']
    assert folders == [str(tmp_path)]


def test_feedback_only_prepares_locally_then_opens_reviewed_official_draft(bridge, monkeypatch):
    opened, folders = [], []
    monkeypatch.setattr('webbrowser.open', lambda url: opened.append(url) or True)
    monkeypatch.setattr(bridge, '_open_folder', lambda path: folders.append(path) or {'ok': True})
    assert not bridge.open_feedback_issue()['ok']
    assert not bridge.open_feedback_folder()['ok']
    result = bridge.prepare_feedback({'title': '显示问题', 'description': '操作后文字换行异常', 'images': []})
    assert result['ok']
    assert opened == []
    note = Path(result['folder']) / '反馈说明.md'
    assert f'程序版本：{__version__}' in note.read_text(encoding='utf-8')
    assert bridge.open_feedback_issue()['ok']
    assert opened == [result['issue_url']]
    assert opened[0].startswith('https://github.com/a18012239736-rgb/carkit/issues/new?')
    assert bridge.open_feedback_folder()['ok']
    assert folders == [result['folder']]
    assert not bridge.prepare_feedback({'title': '', 'description': ''})['ok']
    assert not bridge.open_feedback_issue()['ok']
    assert note.is_file()  # A new invalid submission never removes an earlier draft.
    assert bridge.open_app_release_page()['ok']
    assert opened[-1] == RELEASES_URL
    assert bridge.open_internal_release_page()['ok']
    assert opened[-1] == 'https://my-ichery.feishu.cn/wiki/OkmFwGcV3iKq1Fk6qDocpjgcnXh'


def test_browser_open_failures_are_reported_without_submitting_or_deleting(bridge, monkeypatch):
    def fail(url):
        raise OSError('没有浏览器')

    monkeypatch.setattr('webbrowser.open', fail)
    assert not bridge.open_app_release_page()['ok']
    result = bridge.prepare_feedback({'title': '建议', 'description': '一个建议'})
    assert not bridge.open_feedback_issue()['ok']
    assert (Path(result['folder']) / '反馈说明.md').is_file()
