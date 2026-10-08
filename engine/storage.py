"""Keep existing user data intact if a save fails before replacement."""
import os
import datetime
import re
import tempfile
import uuid


def unique_filename(stem, suffix):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(stem)).strip(' .') or '未命名'
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S-%f')
    return f'{stem}-{stamp}-{uuid.uuid4().hex[:8]}{suffix}'


def atomic_write_text(path, text):
    path = os.path.abspath(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                         dir=os.path.dirname(path),
                                         prefix='.' + os.path.basename(path) + '.',
                                         suffix='.tmp', delete=False) as output:
            temporary = output.name
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
