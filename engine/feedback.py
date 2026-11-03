"""Prepare user-reviewed public feedback without credentials or network writes."""
from __future__ import annotations

import base64
import binascii
import datetime
from pathlib import Path
import platform
import re
import shutil
import tempfile
from urllib.parse import urlencode

from .storage import atomic_write_text


ISSUE_URL = 'https://github.com/a18012239736-rgb/carkit/issues/new'
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 3


def prepare_feedback(workdir, payload, current_version):
    """Save only explicitly entered text/images and return a GitHub draft URL."""
    if not isinstance(payload, dict):
        raise ValueError('反馈内容格式无效')
    title, description = payload.get('title', ''), payload.get('description', '')
    if not isinstance(title, str) or not 0 < len(title.strip()) <= 120:
        raise ValueError('请填写反馈标题（最多120字）')
    if not isinstance(description, str) or len(description) > 10000:
        raise ValueError('反馈说明最多10000字')
    images = payload.get('images', [])
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise ValueError('最多添加3张截图')
    if not description.strip() and not images:
        raise ValueError('请填写反馈说明或添加截图')
    decoded, total = [], 0
    for index, image in enumerate(images, 1):
        data_url = image.get('data_url') if isinstance(image, dict) else None
        if not isinstance(data_url, str):
            raise ValueError('截图格式无效')
        if len(data_url) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 1100:
            raise ValueError('截图仅支持PNG/JPEG，单张不超过5MB')
        match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\r\n]+)', data_url)
        if not match or len(match[2]) > (MAX_IMAGE_BYTES + 2) // 3 * 4 + 1024:
            raise ValueError('截图仅支持PNG/JPEG，单张不超过5MB')
        try:
            content = base64.b64decode(match[2].replace('\r', '').replace('\n', ''), validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('截图编码无效') from None
        png = content.startswith(b'\x89PNG\r\n\x1a\n')
        jpeg = content.startswith(b'\xff\xd8\xff') and content.endswith(b'\xff\xd9')
        if not content or len(content) > MAX_IMAGE_BYTES or not (png if match[1] == 'png' else jpeg):
            raise ValueError('截图不是有效的PNG/JPEG，或单张超过5MB')
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ValueError('截图总大小不能超过10MB')
        # User filenames may contain usernames, local paths or unsafe extensions.
        decoded.append((f'截图-{index}.{"png" if png else "jpg"}', content))

    body = (f'## 使用反馈\n\n{description.strip() or "请见截图。"}\n\n'
            f'## 运行环境\n\n- 程序版本：{current_version}\n- 系统：{platform.system()}\n')
    if decoded:
        body += '\n## 截图\n\n请在提交前将本地反馈文件夹中的截图拖入或粘贴到此处上传。\n'
    query = {'title': '[使用反馈] ' + title.strip(), 'body': body}
    issue_url = ISSUE_URL + '?' + urlencode(query)
    requires_paste = len(issue_url) > 6000
    if requires_paste:
        query['body'] = '完整反馈已在程序中准备。请将反馈窗口复制的正文粘贴到这里，再上传截图并确认提交。'
        issue_url = ISSUE_URL + '?' + urlencode(query)

    workspace = Path(workdir).resolve()
    root = workspace / '反馈'
    if root.resolve().parent != workspace:
        raise ValueError('反馈目录路径无效')
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S-')
    folder = Path(tempfile.mkdtemp(prefix='反馈-' + stamp, dir=root))
    try:
        for name, content in decoded:
            (folder / name).write_bytes(content)
        note = ('# ' + title.strip() + '\n\n' + body +
                '\n---\n此文件及截图仅在本地准备，尚未上传或提交。\n'
                '请先核对是否含内部资料、个人信息，再前往公开GitHub页面上传截图并提交。\n')
        atomic_write_text(folder / '反馈说明.md', note)
    except Exception:
        shutil.rmtree(folder)
        raise
    return {'ok': True, 'issue_url': issue_url, 'folder': str(folder), 'body': body,
            'has_images': bool(decoded), 'requires_paste': requires_paste,
            'image_names': [name for name, _ in decoded]}
