"""USB/Type-C 接口统一按总数显示。"""
import re


def usb_total(value):
    text = str(value or '')
    if text.strip() in ('', '✕', '×', 'X', '-', '无'):
        return 3
    front = re.search(r'前(?:排)?\s*(\d+)', text)
    rear = re.search(r'后(?:排)?\s*(\d+)', text)
    if front or rear:
        return int(front[1]) if front and not rear else int(rear[1]) if rear and not front else int(front[1]) + int(rear[1])
    count = re.search(r'(\d+)\s*个', text)
    return int(count[1]) if count else None


def usb_label(value):
    count = usb_total(value)
    return f'USB/Type-C {count}个' if count is not None else value
