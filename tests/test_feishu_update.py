import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import URLError
from urllib.request import Request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from engine import feishu_update as module

BINARY = b'MZverified-feishu-installer'


@pytest.fixture
def release(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    executable = tmp_path / 'current.exe'
    executable.write_bytes(b'MZoriginal')
    fallback = SimpleNamespace(check=Mock(return_value={'ok': False}), _release=None)
    client = module.FeishuUpdater('0.3.5', key.public_key().public_bytes_raw(), executable,
                                  installed=True, fallback=fallback)

    def serve(version='0.3.6', *, signature=True, package_changes=None, file_changes=None,
              binary=BINARY, malformed=False, metadata_html=False, kind='windows-installer'):
        suffix = {'windows-installer': '-setup.exe', 'windows-x64': '.exe',
                  'macos-arm64': '-macos-arm64.dmg', 'macos-x86_64': '-macos-x86_64.dmg'}[kind]
        name = f'carkit-{version}{suffix}'
        package = {'name': name, 'size': len(BINARY), 'sha256': hashlib.sha256(BINARY).hexdigest()}
        package.update(package_changes or {})
        manifest = json.dumps({'version': version, 'notes': '版本更新',
                               'packages': {kind: package}}, ensure_ascii=False).encode()
        if malformed:
            manifest = b'[]'
        files = [('carkit-update.json', len(manifest)), ('carkit-update.json.sig', 64), (name, len(BINARY))]
        blocks = {}
        for i, (filename, size) in enumerate(files):
            file = {'name': filename, 'token': f'Token{i}', 'size': size}
            if i == 2:
                file.update(file_changes or {})
            blocks[f'Block{i}'] = {'id': f'Block{i}', 'data': {'type': 'file', 'file': file}}
        doc = ('window.DATA = {clientVars: Object(' + json.dumps({'data': {'block_map': blocks}}) + ')}').encode()
        signature_bytes = key.sign(manifest) if signature else b'0' * 64
        responses = {module.WIKI_URL: doc}
        for filename, payload in [('carkit-update.json', manifest), ('carkit-update.json.sig', signature_bytes),
                                  (name, binary)]:
            _, url = module._attachment(module._files(doc.decode()), filename)
            responses[url] = payload
        if metadata_html:
            _, url = module._attachment(module._files(doc.decode()), 'carkit-update.json')
            responses[url] = b'<html>please log in</html>'
        calls = []

        def open_response(url):
            calls.append(url)
            return io.BytesIO(responses[url])

        monkeypatch.setattr(client, '_open', open_response)
        return calls

    return client, fallback, serve, executable


def test_public_document_signed_update_download_and_revalidation(release, tmp_path):
    client, fallback, serve, executable = release
    calls = serve()
    info = client.check()
    assert info['ok'] and info['source'] == 'feishu' and info['installer_update']
    assert info['can_download'] and info['latest_version'] == '0.3.6'
    assert info['release_url'] == module.WIKI_URL and info['release_notes'] == '版本更新'
    target = tmp_path / info['asset_name']
    with pytest.raises(ValueError, match='未下载'):
        client.verified_installer()
    assert client.download_to(target)['ok']
    assert client.verified_installer() == target and target.read_bytes() == BINARY
    assert executable.read_bytes() == b'MZoriginal'
    assert len(calls) == 4 and 'mount_point=docx_file' in calls[-1]
    assert client.status()['state'] == 'complete'
    assert client.check()['downloaded_path'] == str(target)
    target.write_bytes(b'MZtampered')
    with pytest.raises(ValueError, match='完整性校验失败'):
        client.verified_installer()
    assert client.check()['can_download']
    fallback.check.assert_not_called()


@pytest.mark.parametrize('version', ['0.3.5', '0.3.4'])
def test_same_or_older_version_never_downloads(release, tmp_path, version):
    client, _, serve, _ = release
    calls = serve(version)
    info = client.check()
    assert info['ok'] and not info['available'] and not info['can_download']
    assert not client.download_to(tmp_path / 'new.exe')['ok']
    assert len(calls) == 3


@pytest.mark.parametrize('overrides,message', [
    ({'signature': False}, '签名校验失败'),
    ({'metadata_html': True}, '签名校验失败'),
    ({'malformed': True}, '格式无效'),
    ({'version': '0.3.6-beta'}, '版本或格式无效'),
    ({'package_changes': {'name': 'carkit-0.3.6.exe'}}, '版本、大小或校验值无效'),
    ({'package_changes': {'size': True}}, '版本、大小或校验值无效'),
    ({'package_changes': {'sha256': 'bad'}}, '版本、大小或校验值无效'),
    ({'file_changes': {'size': 99}}, '附件大小与签名清单不一致'),
])
def test_integrity_errors_clear_authorization_and_never_fallback(release, tmp_path, overrides, message):
    client, fallback, serve, _ = release
    serve()
    assert client.check()['can_download']
    serve(**overrides)
    info = client.check()
    assert not info['ok'] and message in info['error']
    assert client._release is None
    assert not client.download_to(tmp_path / 'new.exe')['ok']
    fallback.check.assert_not_called()


@pytest.mark.parametrize('binary', [b'<html>login</html>', BINARY[:-1], b'MZ' + b'x' * (len(BINARY) - 2)])
def test_invalid_or_interrupted_files_leave_no_executable(release, tmp_path, binary):
    client, fallback, serve, executable = release
    serve(binary=binary)
    assert client.check()['can_download']
    target = tmp_path / 'new.exe'
    assert not client.download_to(target)['ok']
    assert not target.exists() and not list(tmp_path.glob('*.part'))
    assert executable.read_bytes() == b'MZoriginal'
    fallback.check.assert_not_called()


def test_document_unavailable_uses_github_backend_without_losing_its_state(release, tmp_path, monkeypatch):
    client, fallback, _, _ = release
    info = {'ok': True, 'available': True, 'can_download': True, 'reason': '发现新版'}
    fallback._release = info.copy()
    fallback.check.return_value = info
    fallback.status = Mock(return_value={'state': 'complete', 'path': 'existing.exe'})
    fallback.download_to = Mock(return_value={'ok': True, 'path': 'existing.exe'})
    fallback.verified_installer = Mock(return_value=tmp_path / 'existing.exe')
    monkeypatch.setattr(client, '_open', Mock(side_effect=URLError('offline')))
    assert client.check()['source'] == 'github'
    assert client._release is fallback._release
    assert client.status()['path'] == 'existing.exe'
    assert client.download_to(tmp_path / 'new.exe')['ok']
    assert client.verified_installer() == tmp_path / 'existing.exe'


@pytest.mark.parametrize('kind,extension', [
    ('windows-x64', '.exe'), ('macos-arm64', '.dmg'), ('macos-x86_64', '.dmg'),
])
def test_matching_portable_and_mac_package_downloads(release, tmp_path, kind, extension):
    client, fallback, serve, _ = release
    client.installed = False
    client.target = (kind, extension, kind)
    serve(kind=kind)
    info = client.check()
    assert info['ok'] and not info['installer_update'] and info['platform'] == kind
    assert info['asset_name'].endswith(extension) and info['can_download']
    target = tmp_path / info['asset_name']
    assert client.download_to(target)['ok'] and target.read_bytes() == BINARY
    with pytest.raises(ValueError, match='安装版'):
        client.verified_installer()
    fallback.check.assert_not_called()


def test_download_does_not_overwrite_running_app(release):
    client, _, serve, executable = release
    serve()
    assert client.check()['can_download']
    assert not client.download_to(executable)['ok']
    assert executable.read_bytes() == b'MZoriginal'


@pytest.mark.parametrize('url', [
    'http://my.feishu.cn/wiki/x', 'https://evil.feishu.cn/file',
    'https://my.feishu.cn@evil.example/file', 'https://accounts.feishu.cn:8443/file',
    'https://my.feishu.cn:bad/file',
])
def test_redirects_never_leave_the_observed_feishu_hosts(url):
    with pytest.raises(module.IntegrityError):
        module._Redirects().redirect_request(Request(module.WIKI_URL), None, 302, 'Found', {}, url)


def test_parser_uses_json_only_and_rejects_ambiguous_metadata():
    with pytest.raises(ValueError):
        module._files('clientVars: Object((()=>{throw "executed"})())')
    file = {'token': 'abc', 'block': 'def'}
    with pytest.raises(module.IntegrityError, match='重名'):
        module._attachment({'carkit-update.json': [file, file]}, 'carkit-update.json')
