import hashlib
import io
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from engine import updater


BINARY = b'MZverified-update-payload'


def asset(tag='v0.2.10', name=None, **changes):
    name = name or f'carkit-{tag.removeprefix("v")}.exe'
    result = {
        'name': name, 'state': 'uploaded', 'size': len(BINARY),
        'digest': 'sha256:' + hashlib.sha256(BINARY).hexdigest(),
        'browser_download_url': f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/{name}',
    }
    return {**result, **changes}


def release(tag='v0.2.10', assets=None, **changes):
    return {
        'tag_name': tag, 'name': tag, 'body': '测试更新说明',
        'draft': False, 'prerelease': False,
        'assets': [asset(tag)] if assets is None else assets,
        **changes,
    }


def mock_network(monkeypatch, metadata, binary=BINARY, response=None):
    calls = []

    def open_response(url, accept='application/vnd.github+json'):
        calls.append((url, accept))
        if url == updater.API_URL:
            return io.BytesIO(json.dumps(metadata).encode())
        assert url in [entry['browser_download_url'] for entry in metadata['assets']]
        assert accept == 'application/octet-stream'
        return response() if response else io.BytesIO(binary)

    monkeypatch.setattr(updater, '_open', open_response)
    return calls


def client(tmp_path, version='0.2.9'):
    executable = tmp_path / 'current.exe'
    executable.write_bytes(b'MZoriginal-program')
    instance = updater.AppUpdater(version, executable)
    # These existing cases exercise the Windows portable-package path on every host OS.
    instance.target = ('windows-x64', '.exe', 'Windows x64')
    return instance, executable


@pytest.mark.parametrize('current,latest,available', [
    ('0.2.9', 'v0.2.10', True),
    ('0.2.10', 'v0.2.9', False),
])
def test_numeric_version_comparison_never_offers_a_downgrade(tmp_path, monkeypatch, current, latest, available):
    check, _ = client(tmp_path, current)
    mock_network(monkeypatch, release(latest))
    result = check.check()
    assert result['ok'] and result['available'] is available
    assert result['can_download'] is available
    if not available:
        assert not check.download_to(tmp_path / 'downgrade.exe')['ok']


@pytest.mark.parametrize('changes', [
    {'prerelease': True}, {'draft': True}, {'tag_name': 'v0.2.10-rc.1'},
])
def test_unreleased_or_nonstable_versions_cannot_be_downloaded(tmp_path, monkeypatch, changes):
    check, _ = client(tmp_path)
    mock_network(monkeypatch, release(**changes))
    assert not check.check()['ok']
    assert not check.download_to(tmp_path / 'new.exe')['ok']


@pytest.mark.parametrize('assets,expected', [
    ([asset(name='carkit.exe'), asset()], 'carkit-0.2.10.exe'),
    ([asset(name='carkit.exe')], 'carkit.exe'),
    ([asset(state='new'), asset(name='carkit.exe')], 'carkit.exe'),
])
def test_only_uploaded_assets_are_used_and_versioned_filename_is_preferred(tmp_path, monkeypatch, assets, expected):
    check, _ = client(tmp_path)
    mock_network(monkeypatch, release(assets=assets))
    result = check.check()
    assert result['ok'] and result['can_download']
    assert result['asset_name'] == expected


@pytest.mark.parametrize('digest', [asset()['digest'], None])
def test_same_version_never_offers_a_download_even_with_different_bytes(tmp_path, monkeypatch, digest):
    check, _ = client(tmp_path, '0.2.3')
    calls = mock_network(monkeypatch, release('v0.2.3', assets=[asset('v0.2.3', digest=digest)]))
    result = check.check()
    assert result['ok'] and result['same_version']
    assert not result['available'] and not result['can_download']
    assert '最新' in result['reason']
    assert not check.download_to(tmp_path / 'same.exe')['ok']
    assert len(calls) == 1


def test_missing_digest_and_source_mode_block_downloads(tmp_path, monkeypatch):
    check, _ = client(tmp_path)
    calls = mock_network(monkeypatch, release(assets=[asset(digest=None)]))
    result = check.check()
    assert result['ok'] and result['available'] and not result['can_download']
    assert not check.download_to(tmp_path / 'unchecked.exe')['ok']
    assert len(calls) == 1

    calls = mock_network(monkeypatch, release())
    source = updater.AppUpdater('0.2.9')
    result = source.check()
    assert result['ok'] and result['available'] and not result['supported']
    assert not result['can_download']
    assert not source.download_to(tmp_path / 'source.exe')['ok']
    assert len(calls) == 1


@pytest.mark.parametrize('url', [
    'https://evil.example/carkit.exe',
    'http://github.com/a18012239736-rgb/carkit/releases/download/v0.2.10/carkit-0.2.10.exe',
    'https://github.com/someone/other/releases/download/v0.2.10/carkit-0.2.10.exe',
])
def test_release_asset_url_must_match_the_official_repository(tmp_path, monkeypatch, url):
    check, _ = client(tmp_path)
    calls = mock_network(monkeypatch, release(assets=[asset(browser_download_url=url)]))
    assert not check.check()['ok']
    assert not check.download_to(tmp_path / 'new.exe')['ok']
    assert len(calls) == 1


@pytest.mark.parametrize('url', [
    'https://evil.example/carkit.exe',
    'http://release-assets.githubusercontent.com/carkit.exe',
    'https://github.com@evil.example/carkit.exe',
    'https://github.com:8443/carkit.exe',
])
def test_download_redirect_rejects_untrusted_hosts_credentials_and_http(url):
    request = Request(asset()['browser_download_url'])
    with pytest.raises(ValueError, match='官方 GitHub'):
        updater._Redirects().redirect_request(request, None, 302, 'Found', {}, url)


@pytest.mark.parametrize('body,expected_digest', [
    (b'MZ' + b'x' * (len(BINARY) - 2), BINARY),
    (BINARY[:-1], BINARY),
    (BINARY + b'x', BINARY),
    (b'NO' + BINARY[2:], b'NO' + BINARY[2:]),
])
def test_invalid_downloads_never_leave_a_finished_executable(tmp_path, monkeypatch, body, expected_digest):
    check, executable = client(tmp_path)
    metadata = release(assets=[asset(digest='sha256:' + hashlib.sha256(expected_digest).hexdigest())])
    mock_network(monkeypatch, metadata, binary=body)
    assert check.check()['can_download']
    target = tmp_path / 'new.exe'
    assert not check.download_to(target)['ok']
    assert not target.exists()
    assert executable.read_bytes() == b'MZoriginal-program'
    assert not list(tmp_path.glob('*.part'))
    assert check.status()['state'] == 'error'


def test_interrupted_download_cleans_partial_file_and_keeps_original(tmp_path, monkeypatch):
    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise URLError('模拟连接中断')
            return super().read(size)

    check, executable = client(tmp_path)
    mock_network(monkeypatch, release(), response=lambda: Interrupted(BINARY))
    assert check.check()['can_download']
    assert not check.download_to(tmp_path / 'new.exe')['ok']
    assert set(tmp_path.iterdir()) == {executable}
    assert executable.read_bytes() == b'MZoriginal-program'


@pytest.mark.parametrize('destination', ['current.exe', 'existing.exe'])
def test_download_never_overwrites_running_or_existing_program(tmp_path, monkeypatch, destination):
    check, executable = client(tmp_path)
    target = tmp_path / destination
    if target != executable:
        target.write_bytes(b'keep-existing-file')
    original = target.read_bytes()
    calls = mock_network(monkeypatch, release())
    assert check.check()['can_download']
    assert not check.download_to(target)['ok']
    assert target.read_bytes() == original
    assert len(calls) == 1


def test_successful_download_preserves_executable_and_user_data(tmp_path, monkeypatch):
    check, executable = client(tmp_path)
    data = tmp_path / 'Codex' / '方案'
    data.mkdir(parents=True)
    saved = data / '用户方案.json'
    saved.write_text('{"keep":true}', encoding='utf-8')
    mock_network(monkeypatch, release())
    assert check.check()['can_download']
    target = tmp_path / 'new.exe'
    result = check.download_to(target)
    assert result == {'ok': True, 'path': str(target), 'sha256': hashlib.sha256(BINARY).hexdigest()}
    assert target.read_bytes() == BINARY
    assert executable.read_bytes() == b'MZoriginal-program'
    assert saved.read_text(encoding='utf-8') == '{"keep":true}'
    assert not list(tmp_path.glob('*.part'))
    assert check.status()['state'] == 'complete'
    assert check.status()['downloaded'] == len(BINARY)
    already_downloaded = check.check()
    assert already_downloaded['downloaded_path'] == str(target)
    assert not already_downloaded['can_download']
    assert check.status()['path'] == str(target)
    target.unlink()
    assert check.check()['can_download']


@pytest.mark.parametrize('machine,target', [
    ('arm64', 'macos-arm64'),
    ('x86_64', 'macos-x86_64'),
])
def test_macos_uses_matching_architecture_dmg_and_accepts_disk_image_bytes(tmp_path, monkeypatch, machine, target):
    monkeypatch.setattr(updater.sys, 'platform', 'darwin')
    monkeypatch.setattr(updater.platform, 'machine', lambda: machine)
    package = b'UDIF-macos-installer'
    name = f'carkit-0.2.10-{target}.dmg'
    executable = tmp_path / 'carkit'
    executable.write_bytes(b'current-macos-app')
    check = updater.AppUpdater('0.2.9', executable)
    metadata = release(assets=[
        {**asset(name=f'carkit-0.2.10-macos-arm64.dmg'),
         'size': len(package), 'digest': 'sha256:' + hashlib.sha256(package).hexdigest()},
        {**asset(name='carkit-0.2.10-macos-x86_64.dmg'),
         'size': len(package), 'digest': 'sha256:' + hashlib.sha256(package).hexdigest()},
    ])
    mock_network(monkeypatch, metadata, binary=package)
    info = check.check()
    assert info['ok'] and info['platform'] == target
    assert info['asset_name'] == name and info['can_download']
    path = tmp_path / name
    result = check.download_to(path)
    assert result['ok'] and path.read_bytes() == package


def test_macos_download_requires_dmg_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.sys, 'platform', 'darwin')
    monkeypatch.setattr(updater.platform, 'machine', lambda: 'arm64')
    package = b'UDIF-macos-installer'
    name = 'carkit-0.2.10-macos-arm64.dmg'
    executable = tmp_path / 'carkit'
    executable.write_bytes(b'current-macos-app')
    check = updater.AppUpdater('0.2.9', executable)
    metadata = release(assets=[{
        **asset(name=name), 'size': len(package),
        'digest': 'sha256:' + hashlib.sha256(package).hexdigest(),
    }])
    mock_network(monkeypatch, metadata, binary=package)
    assert check.check()['can_download']
    assert not check.download_to(tmp_path / 'new.exe')['ok']


def test_windows_prefers_legacy_release_assets_when_versioned_asset_is_missing(tmp_path, monkeypatch):
    check, _ = client(tmp_path)
    mock_network(monkeypatch, release(assets=[asset(name='carkit.exe')]))
    result = check.check()
    assert result['ok'] and result['asset_name'] == 'carkit.exe'


def test_destination_created_during_download_is_not_overwritten(tmp_path, monkeypatch):
    target = tmp_path / 'new.exe'

    class ConcurrentTarget(io.BytesIO):
        def read(self, size=-1):
            if not self.tell():
                target.write_bytes(b'concurrently-created-file')
            return super().read(size)

    check, _ = client(tmp_path)
    mock_network(monkeypatch, release(), response=lambda: ConcurrentTarget(BINARY))
    assert check.check()['can_download']
    assert not check.download_to(target)['ok']
    assert target.read_bytes() == b'concurrently-created-file'
    assert not list(tmp_path.glob('*.part'))


@pytest.mark.parametrize('error', [
    URLError('模拟断网'),
    HTTPError(updater.API_URL, 429, 'Too Many Requests', {}, None),
])
def test_network_failure_is_not_reported_as_latest(tmp_path, monkeypatch, error):
    check, _ = client(tmp_path)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(updater, '_open', fail)
    result = check.check()
    assert not result['ok'] and result['error']
    assert check.status()['state'] == 'error'
    assert not check.download_to(tmp_path / 'new.exe')['ok']
