"""Read official releases and download a verified new exe; never replace a running app."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = 'a18012239736-rgb/carkit'
RELEASES_URL = f'https://github.com/{REPOSITORY}/releases/latest'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_DOWNLOAD = 512 * 1024 * 1024


def _version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', str(value))
    if not match:
        raise ValueError('正式版本号格式无效，请到官方发布页查看')
    return tuple(map(int, match.groups()))


def _https_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.hostname not in {
                'api.github.com', 'github.com', 'release-assets.githubusercontent.com',
                'objects.githubusercontent.com'}):
        raise ValueError('更新地址不属于官方 GitHub 下载服务，已停止')


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url, accept='application/vnd.github+json'):
    _https_url(url)
    request = Request(url, headers={'Accept': accept, 'User-Agent': 'carkit-updater',
                                   'Cache-Control': 'no-cache',
                                   'X-GitHub-Api-Version': '2022-11-28'})
    return build_opener(_Redirects()).open(request, timeout=20)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _message(error):
    if isinstance(error, HTTPError):
        if error.code in (403, 429):
            return 'GitHub 暂时限制访问，请稍后重试或打开官方发布页'
        if error.code == 404:
            return '尚未找到正式版本或安装包，请到官方发布页查看'
        return 'GitHub 更新服务暂不可用，请稍后重试'
    if isinstance(error, (URLError, TimeoutError)):
        return '无法连接 GitHub，请检查网络后重试；当前程序仍可正常使用'
    if isinstance(error, OSError):
        return '无法读取或保存更新文件，请检查文件权限和可用空间后重试'
    return str(error)


class AppUpdater:
    def __init__(self, current_version, executable=None):
        _version(current_version)
        self.current_version = current_version
        self.executable = Path(executable).resolve() if executable else None
        self._current_digest = None
        self._release = None
        self._operation = Lock()
        self._state_lock = Lock()
        self._state = {'ok': True, 'state': 'idle', 'downloaded': 0, 'total': 0}

    def _set_state(self, **values):
        with self._state_lock:
            self._state = {'ok': True, 'downloaded': 0, 'total': 0, **values}

    def status(self):
        with self._state_lock:
            return dict(self._state)

    def check(self):
        if not self._operation.acquire(blocking=False):
            return {'ok': False, 'error': '正在检查或下载更新，请稍候'}
        try:
            self._release = None
            self._set_state(state='checking')
            with _open(API_URL) as response:
                content = response.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError('更新信息过大，请到官方发布页查看')
            try:
                release = json.loads(content)
            except (ValueError, UnicodeError):
                raise ValueError('更新信息无法读取，请稍后重试') from None
            if not isinstance(release, dict) or release.get('draft') or release.get('prerelease'):
                raise ValueError('未找到可用的正式版本')
            tag = release.get('tag_name', '')
            latest = _version(tag)
            current = _version(self.current_version)
            version = tag.removeprefix('v')
            assets = release.get('assets', [])
            if not isinstance(assets, list):
                raise ValueError('安装包信息无效，请到官方发布页查看')
            asset = next((a for name in (f'carkit-{version}.exe', 'carkit.exe')
                          for a in assets if isinstance(a, dict) and a.get('name') == name
                          and a.get('state') == 'uploaded'), None)
            digest = ''
            if asset:
                expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{asset["name"]}'
                if asset.get('browser_download_url') != expected:
                    raise ValueError('安装包地址与官方版本不一致，已停止')
                if type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_DOWNLOAD:
                    raise ValueError('安装包大小无效，请到官方发布页查看')
                value = asset.get('digest') or ''
                if re.fullmatch(r'sha256:[0-9a-fA-F]{64}', str(value)):
                    digest = value.split(':', 1)[1].lower()
            same_version = latest == current
            available = latest > current
            reason = '发现新版本，可下载后更新' if available else '当前已是最新正式版本'
            if latest < current:
                reason = '当前程序版本高于 GitHub 正式版本，不提供降级'
            elif same_version and self.executable:
                if digest:
                    if self._current_digest is None:
                        self._current_digest = _sha256(self.executable)
                    available = self._current_digest != digest
                    reason = '同版本有补充更新，可下载后更新' if available else '当前安装包已是最新'
                else:
                    reason = '版本号相同，但缺少安装包摘要，无法确认是否有同版本补丁'
            supported = self.executable is not None
            if not supported:
                reason += '；当前为源码或非 Windows 单文件运行，请在官方发布页查看'
            elif not asset:
                reason += '；该版本尚未提供 Windows 安装包'
            elif available and not digest:
                reason += '；安装包缺少 SHA256 摘要，已禁用程序内下载'
            result = {'ok': True, 'current_version': self.current_version,
                      'latest_version': version, 'same_version': same_version,
                      'available': available, 'supported': supported,
                      'can_download': bool(available and supported and asset and digest),
                      'release_url': f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
                      'release_name': str(release.get('name') or tag),
                      'release_notes': str(release.get('body') or '本次发布未填写更新说明'),
                      'published_at': str(release.get('published_at') or ''),
                      'asset_name': asset['name'] if asset else '',
                      'asset_size': asset['size'] if asset else 0, 'reason': reason}
            from datetime import datetime, timezone
            result['checked_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            self._release = {**result, 'asset': asset, 'digest': digest}
            self._set_state(state='idle')
            return result
        except Exception as error:
            message = _message(error)
            self._set_state(state='error', error=message)
            return {'ok': False, 'error': message}
        finally:
            self._operation.release()

    def download_to(self, destination):
        if not self._operation.acquire(blocking=False):
            return {'ok': False, 'error': '正在检查或下载更新，请稍候'}
        temporary = None
        try:
            release = self._release
            if not release or not release['can_download']:
                raise ValueError('请先检查并选择可校验的 Windows 更新')
            target = Path(destination)
            if not target.is_absolute() or target.suffix.lower() != '.exe':
                raise ValueError('请选择新的 .exe 文件保存位置')
            if target.resolve() == self.executable or (target.exists() and self.executable.exists()
                                                       and os.path.samefile(target, self.executable)):
                raise ValueError('不能覆盖正在运行的程序，请选择其他文件名或文件夹')
            if target.exists() or target.is_symlink():
                raise ValueError('该文件已存在，请选择新的文件名，以保留原程序')
            asset = release['asset']
            total, downloaded = asset['size'], 0
            self._set_state(state='downloading', total=total)
            fd, temporary = tempfile.mkstemp(prefix='.carkit-download-', suffix='.part', dir=target.parent)
            digest = hashlib.sha256()
            prefix = b''
            with os.fdopen(fd, 'wb') as output, _open(asset['browser_download_url'], 'application/octet-stream') as response:
                while chunk := response.read(1024 * 1024):
                    downloaded += len(chunk)
                    if downloaded > total:
                        raise ValueError('下载文件大小与发布记录不一致，已丢弃')
                    prefix = (prefix + chunk)[:2]
                    output.write(chunk)
                    digest.update(chunk)
                    self._set_state(state='downloading', downloaded=downloaded, total=total)
                output.flush()
                os.fsync(output.fileno())
            if downloaded != total or digest.hexdigest() != release['digest'] or prefix != b'MZ':
                raise ValueError('安装包完整性校验失败，已丢弃；请重新检查更新后下载')
            # Windows rename fails if the destination appeared while downloading.
            # The offline test path uses an equally exclusive, atomic POSIX link.
            if os.name == 'nt':
                os.rename(temporary, target)
            else:
                os.link(temporary, target)
            result = {'ok': True, 'path': str(target), 'sha256': digest.hexdigest()}
            self._set_state(state='complete', downloaded=total, total=total, path=str(target))
            return result
        except Exception as error:
            message = _message(error)
            self._set_state(state='error', error=message)
            return {'ok': False, 'error': message}
        finally:
            if temporary:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass  # A locked partial file is never treated as an update.
            self._operation.release()
