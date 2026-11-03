"""Read signed release manifests for the installed Windows application."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from engine import updater


MANIFEST_URL = f'{updater.RELEASES_URL}/download/latest.json'
SIGNATURE_URL = MANIFEST_URL + '.sig'
MAX_MANIFEST = 2 * 1024 * 1024


class InstallerUpdater(updater.AppUpdater):
    def __init__(self, current_version, public_key, executable=None):
        super().__init__(current_version, executable or sys.executable)
        self._public_key = Ed25519PublicKey.from_public_bytes(public_key)

    def _read_manifest(self):
        with updater._open(MANIFEST_URL) as response:
            raw = response.read(MAX_MANIFEST + 1)
        if len(raw) > MAX_MANIFEST:
            raise ValueError('更新清单过大')
        with updater._open(SIGNATURE_URL, 'application/octet-stream') as response:
            signature = response.read(65)
        try:
            self._public_key.verify(signature, raw)
        except InvalidSignature:
            raise ValueError('更新清单签名校验失败') from None
        try:
            manifest = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ValueError('更新清单格式无效') from None
        if not isinstance(manifest, dict):
            raise ValueError('更新清单格式无效')
        return manifest

    def _verified_path(self, release):
        if self._downloaded and self._downloaded['sha256'] == release['digest']:
            path = Path(self._downloaded['path'])
            try:
                if (path.is_file() and path.stat().st_size == release['asset']['size']
                        and updater._sha256(path) == release['digest']):
                    return path
            except OSError:
                pass
        return None

    def check(self):
        if not self._operation.acquire(blocking=False):
            return {'ok': False, 'error': '正在检查或下载更新，请稍候'}
        try:
            self._release = None
            self._set_state(state='checking')
            manifest = self._read_manifest()
            version = manifest.get('version')
            if not isinstance(version, str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}', version):
                raise ValueError('更新清单版本号无效')
            latest = updater._version(version)
            current = updater._version(self.current_version)
            available = latest > current
            tag = f'v{version}'
            release_url = f'https://github.com/{updater.REPOSITORY}/releases/tag/{tag}'
            name = f'carkit-{version}-setup.exe'
            expected_url = f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/{name}'
            installer = manifest.get('windows-x64')
            if not isinstance(installer, dict) or installer.get('url') != expected_url:
                raise ValueError('安装包地址与官方版本不一致')
            size, digest = installer.get('size'), installer.get('sha256')
            if type(size) is not int or not 0 < size <= updater.MAX_DOWNLOAD:
                raise ValueError('安装包大小无效')
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
                raise ValueError('安装包缺少有效 SHA-256 摘要')
            release = {'asset': {'name': name, 'size': size, 'browser_download_url': expected_url},
                       'digest': digest.lower()}
            path = self._verified_path(release) if available else None
            result = {'ok': True, 'current_version': self.current_version,
                      'latest_version': version, 'same_version': latest == current,
                      'available': available, 'supported': True, 'installer_update': True,
                      'can_download': available and path is None, 'downloaded_path': str(path) if path else '',
                      'release_url': release_url, 'asset_name': name, 'asset_size': size,
                      'release_notes': str(manifest.get('notes') or '本次发布未填写更新说明'),
                      'reason': ('发现新版，下载后可安装并重启' if available else '当前已是最新正式版本')}
            if latest < current:
                result['reason'] = '当前程序版本高于 GitHub 正式版本，不提供降级'
            self._release = {**release, **result}
            if path:
                self._set_state(state='complete', downloaded=size, total=size, path=str(path))
            else:
                self._set_state(state='idle')
            return result
        except Exception as error:
            message = updater._message(error)
            self._set_state(state='error', error=message)
            return {'ok': False, 'error': message}
        finally:
            self._operation.release()

    def verified_installer(self):
        """Recheck the selected installer before handing it to the launcher."""
        if not self._operation.acquire(blocking=False):
            raise ValueError('正在检查或下载更新，请稍候')
        try:
            if self._release and self._release['available']:
                path = self._verified_path(self._release)
                if path:
                    return path
            raise ValueError('安装包未下载或完整性校验失败，请重新检查更新后下载')
        finally:
            self._operation.release()
