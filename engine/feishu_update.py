"""Read signed release metadata and public attachments from the Carkit wiki."""
from __future__ import annotations

from http.cookiejar import CookieJar
import json
import re
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, Request, build_opener

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from engine import updater
from engine.installer_update import InstallerUpdater

WIKI_URL = 'https://my.feishu.cn/wiki/RbVTwWOJFiCjOukyBO8csx2Rnwd'
STREAM_URL = 'https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/all/'
MAX_DOCUMENT = 4 * 1024 * 1024
MAX_MANIFEST = 2 * 1024 * 1024


class IntegrityError(ValueError):
    """A verification failure must not silently switch the update source."""


def _https_url(url):
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == 'https' and not parsed.username and not parsed.password
                 and parsed.port in (None, 443) and parsed.hostname in {
                     'my.feishu.cn', 'accounts.feishu.cn', 'login.feishu.cn',
                     'internal-api-drive-stream.feishu.cn'})
    except ValueError:
        valid = False
    if not valid:
        raise IntegrityError('更新地址不属于指定的飞书下载服务')


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _files(html):
    marker = re.search(r'\bclientVars\s*:\s*Object\s*\(', html)
    if not marker:
        raise ValueError('飞书更新文档暂不可读取，请检查公开访问权限')
    try:
        value, _ = json.JSONDecoder().raw_decode(html[marker.end():].lstrip())
        blocks = value['data']['block_map']
        if not isinstance(blocks, dict):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        raise ValueError('飞书更新文档内容无效') from None
    files = {}
    for key, block in blocks.items():
        data = block.get('data', {}) if isinstance(block, dict) else {}
        if data.get('type') != 'file':
            continue
        file = data.get('file', {})
        if not isinstance(file, dict) or not isinstance(file.get('name'), str):
            continue
        files.setdefault(file['name'], []).append({**file, 'block': block.get('id') or key})
    return files


def _attachment(files, name):
    matches = files.get(name, [])
    if not matches:
        raise ValueError(f'飞书更新文档缺少附件：{name}')
    if len(matches) != 1:
        raise IntegrityError(f'飞书更新附件重名，无法确认版本：{name}')
    file = matches[0]
    if any(not isinstance(file.get(key), str) or not re.fullmatch(r'[A-Za-z0-9]+', file[key])
           for key in ('token', 'block')):
        raise IntegrityError('飞书附件标识无效')
    url = STREAM_URL + file['token'] + '/?' + urlencode({
        'mount_node_token': file['block'], 'mount_point': 'docx_file'})
    return file, url


class FeishuUpdater(updater.AppUpdater):
    def __init__(self, current_version, public_key, executable=None, installed=False, fallback=None):
        super().__init__(current_version, executable)
        self.installed = installed
        if installed:
            self.target = ('windows-x64', '.exe', 'Windows x64')
        self._public_key = Ed25519PublicKey.from_public_bytes(public_key)
        self.fallback = fallback
        self._use_fallback = False
        # This jar starts empty; it never reads the user's browser login cookies.
        self._guest = build_opener(HTTPCookieProcessor(CookieJar()), _Redirects())

    def _open(self, url):
        _https_url(url)
        return self._guest.open(Request(url, headers={
            'Referer': 'https://my.feishu.cn/', 'User-Agent': 'carkit-updater',
            'Cache-Control': 'no-cache'}), timeout=20)

    def _read(self, url, limit):
        with self._open(url) as response:
            content = response.read(limit + 1)
        if len(content) > limit:
            raise IntegrityError('飞书更新信息超过大小限制')
        return content

    def _open_download(self, url):
        if not self._release or url != self._release['asset']['browser_download_url']:
            raise IntegrityError('安装包地址与已核实的飞书附件不一致')
        return self._open(url)

    def _check_feishu(self):
        files = _files(self._read(WIKI_URL, MAX_DOCUMENT).decode('utf-8'))
        _, manifest_url = _attachment(files, 'carkit-update.json')
        _, signature_url = _attachment(files, 'carkit-update.json.sig')
        raw = self._read(manifest_url, MAX_MANIFEST)
        signature = self._read(signature_url, 64)
        try:
            self._public_key.verify(signature, raw)
        except (InvalidSignature, ValueError):
            raise IntegrityError('飞书更新清单签名校验失败') from None
        try:
            manifest = json.loads(raw)
            version = manifest['version']
            if not isinstance(version, str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}', version):
                raise ValueError
            if not isinstance(manifest['packages'], dict) or not isinstance(manifest.get('notes', ''), str):
                raise ValueError
        except (KeyError, ValueError, TypeError):
            raise IntegrityError('飞书更新清单版本或格式无效') from None
        latest, current = updater._version(version), updater._version(self.current_version)
        available = latest > current
        supported = bool(self.executable and self.target)
        asset, digest, path = None, '', None
        if supported:
            kind = 'windows-installer' if self.installed else self.target[0]
            suffix = '-setup.exe' if self.installed else '.exe' if kind == 'windows-x64' else f'-{kind}.dmg'
            name = f'carkit-{version}{suffix}'
            package = manifest['packages'].get(kind)
            if (not isinstance(package, dict) or package.get('name') != name
                    or type(package.get('size')) is not int or not 0 < package['size'] <= updater.MAX_DOWNLOAD
                    or not isinstance(package.get('sha256'), str)
                    or not re.fullmatch(r'[0-9a-fA-F]{64}', package['sha256'])):
                raise IntegrityError('飞书安装包版本、大小或校验值无效')
            file, url = _attachment(files, name)
            if type(file.get('size')) is not int or file['size'] != package['size']:
                raise IntegrityError('飞书附件大小与签名清单不一致')
            asset = {'name': name, 'size': package['size'], 'browser_download_url': url}
            digest = package['sha256'].lower()
            if available:
                path = InstallerUpdater._verified_path(self, {'asset': asset, 'digest': digest})
        reason = '发现新版，可从飞书下载更新' if available else '当前已是最新正式版本'
        if latest < current:
            reason = '当前程序版本高于飞书正式版本，不提供降级'
        if not supported:
            reason += '；当前为源码运行或暂不支持的设备，请打开飞书更新页查看'
        result = {'ok': True, 'source': 'feishu', 'current_version': self.current_version,
                  'latest_version': version, 'same_version': latest == current,
                  'available': available, 'supported': supported, 'installer_update': self.installed,
                  'platform': self.target[0] if self.target else '',
                  'platform_name': self.target[2] if self.target else '',
                  'can_download': bool(available and supported and not path),
                  'downloaded_path': str(path) if path else '', 'release_url': WIKI_URL,
                  'release_name': f'Carkit v{version}', 'release_notes': manifest.get('notes', ''),
                  'asset_name': asset['name'] if asset else '', 'asset_size': asset['size'] if asset else 0,
                  'reason': reason}
        self._release = {**result, 'asset': asset, 'digest': digest}
        if path:
            self._set_state(state='complete', path=str(path), downloaded=asset['size'], total=asset['size'])
        else:
            self._set_state(state='idle')
        return result

    def check(self):
        if not self._operation.acquire(blocking=False):
            return {'ok': False, 'error': '正在检查或下载更新，请稍候'}
        self._release = None
        self._use_fallback = False
        self._set_state(state='checking')
        try:
            return self._check_feishu()
        except IntegrityError as error:
            self._set_state(state='error', error=str(error))
            return {'ok': False, 'source': 'feishu', 'error': str(error)}
        except Exception:
            if self.fallback:
                result = self.fallback.check()
                if result.get('ok'):
                    self._use_fallback = True
                    self._release = self.fallback._release
                    return {**result, 'source': 'github', 'reason': '飞书暂不可用，已切换 GitHub。' + result.get('reason', '')}
            message = '无法读取飞书更新信息；请稍后重试或打开飞书更新页'
            self._set_state(state='error', error=message)
            return {'ok': False, 'source': 'feishu', 'error': message}
        finally:
            self._operation.release()

    def status(self):
        return self.fallback.status() if self._use_fallback else super().status()

    def download_to(self, destination):
        if not self._use_fallback:
            return super().download_to(destination)
        if not self._operation.acquire(blocking=False):
            return {'ok': False, 'error': '正在检查或下载更新，请稍候'}
        try:
            return self.fallback.download_to(destination)
        finally:
            self._operation.release()

    def verified_installer(self):
        if not self.installed:
            raise ValueError('安装版才能安装并重启')
        if self._use_fallback:
            return self.fallback.verified_installer()
        return InstallerUpdater.verified_installer(self)

    _verified_path = InstallerUpdater._verified_path
