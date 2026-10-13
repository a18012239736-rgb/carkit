"""USB/Type-C 接口统一按总数显示。"""
import re


def usb_total(value, default=3):
    text = str(value or '')
    if text.strip() in ('', '✕', '×', 'X', '-', '无'):
        return default
    front = re.search(r'前(?:排)?\s*(\d+)', text)
    rear = re.search(r'后(?:排)?\s*(\d+)', text)
    if front or rear:
        return int(front[1]) if front and not rear else int(rear[1]) if rear and not front else int(front[1]) + int(rear[1])
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
