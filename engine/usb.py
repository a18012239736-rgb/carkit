"""USB/Type-C 接口统一按总数显示。"""
import re


def usb_total(value, default=3):
    text = str(value or '')
    if text.strip() in ('', '✕', '×', 'X', '-', '无'):
        return default
    scoped = re.findall(r'(?:前|第?二|后|第?三)(?:排)?\s*(\d+)', text)
    if scoped:
        return sum(int(n) for n in scoped)
    count = re.search(r'(\d+(?:\.\d+)?)\s*个', text)
    return (float(count[1]) if '.' in count[1] else int(count[1])) if count else None


def usb_label(value, *, default=3, preserve_default=False):
    text = str(value or '')
    if '[待' in text or '?' in text or '○' in text:
        return value
    if preserve_default and text.strip() in ('', '✕', '×', 'X', '-', '无'):
        return '✕'  # Resolve unspecified counts only when the active pricing rule is known.
    count = usb_total(value, default=default)
    return f'USB/Type-C {count}个' if count is not None else value
