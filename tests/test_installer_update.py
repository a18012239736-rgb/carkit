import hashlib
import io
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from engine import installer_update, updater


INSTALLER = b'MZverified-installer'


@pytest.fixture
def release(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    executable = tmp_path / 'carkit.exe'
    executable.write_bytes(b'MZcurrent-app')
    client = installer_update.InstallerUpdater('0.3.2', public, executable)

    def serve(version='0.3.3', *, tampered=False, url=None, size=None):
        official_url = (f'https://github.com/{updater.REPOSITORY}/releases/download/'
                        f'v{version}/carkit-{version}-setup.exe')
        manifest = json.dumps({'version': version, 'notes': '新版说明', 'windows-x64': {
            'url': url or official_url, 'size': len(INSTALLER) if size is None else size,
            'sha256': hashlib.sha256(INSTALLER).hexdigest(),
        }}, ensure_ascii=False).encode('utf-8')
        responses = {installer_update.MANIFEST_URL: manifest + (b'\n' if tampered else b''),
                     installer_update.SIGNATURE_URL: key.sign(manifest), official_url: INSTALLER}
        requests = []

        def open_response(url, accept='application/vnd.github+json'):
            requests.append(url)
            return io.BytesIO(responses[url])

        monkeypatch.setattr(updater, '_open', open_response)
        return requests

    return client, serve


def test_signed_installer_checks_download_and_revalidation(release, tmp_path):
    client, serve = release
    requests = serve()
    info = client.check()
    assert info['ok'] and info['installer_update'] and info['can_download']
    assert info['latest_version'] == '0.3.3' and info['release_notes'] == '新版说明'
    with pytest.raises(ValueError, match='未下载'):
        client.verified_installer()

    path = tmp_path / info['asset_name']
    assert client.download_to(path)['ok']
    assert path.read_bytes() == INSTALLER
    assert client.verified_installer() == path
    assert requests[2].endswith('/v0.3.3/carkit-0.3.3-setup.exe')
    again = client.check()
    assert again['downloaded_path'] == str(path) and not again['can_download']

    path.write_bytes(b'MZtampered-installer')
    with pytest.raises(ValueError, match='完整性校验失败'):
        client.verified_installer()
    assert client.check()['can_download']


@pytest.mark.parametrize('version', ['0.3.2', '0.3.1'])
def test_signed_equal_or_older_installer_is_unavailable(release, version):
    client, serve = release
    requests = serve(version)
    result = client.check()
    assert result['ok'] and not result['available'] and not result['can_download']
    assert requests == [installer_update.MANIFEST_URL, installer_update.SIGNATURE_URL]


@pytest.mark.parametrize('overrides,message', [
    ({'tampered': True}, '签名校验失败'),
    ({'version': '0.3.3-beta.1'}, '版本号无效'),
    ({'url': 'https://example.org/carkit.exe'}, '地址与官方版本不一致'),
    ({'size': updater.MAX_DOWNLOAD + 1}, '大小无效'),
])
def test_manifest_errors_clear_previous_download_authorization(release, tmp_path, overrides, message):
    client, serve = release
    serve()
    assert client.check()['can_download']
    requests = serve(**overrides)
    result = client.check()
    assert not result['ok'] and message in result['error']
    assert not client.download_to(tmp_path / 'new.exe')['ok']
    assert requests == [installer_update.MANIFEST_URL, installer_update.SIGNATURE_URL]
