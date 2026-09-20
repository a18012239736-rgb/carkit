"""Screen values shared by manual editing, import and comparison."""
import re

SCREEN_NAMES = {21: '中控屏', 22: '副驾娱乐屏', 29: '仪表'}


def normalize_screen(value, no, strict=False):
    text = str(value or '').strip()
    if text in ('✕', '×', '无', '无配置', '-', '不适用'):
        return '不适用' if text == '不适用' else '✕'
    if '[待定]' in text:
        return text
    # Prefer explicit inches; never mistake 2K/4K resolution for size.
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:英寸|吋|寸)', text)
    if not match:
        match = re.match(r'^[●○]?\s*(\d+(?:\.\d+)?)(?![\d.]|\s*[kK])', text)
    if match and not (match.start() and text[match.start()-1] == '-') and 0 < float(match[1]) <= 100:
        first = re.search(r'\d+(?:\.\d+)?', text)
        if first and float(first[0]) == float(match[1]):
            return text
        size = f'{float(match[1]):g}'
        suffix = '全液晶仪表' if no == 29 and '全液晶' in text else SCREEN_NAMES[no]
        optional = '○' if text.startswith('○') else ''
        extra = re.search(r'[,，]\s*(○[\d.]+选装)', text)
        return optional + size + '寸' + suffix + (',' + extra[1] if extra else '')
    if strict:
        raise ValueError(f'{SCREEN_NAMES[no]}：请填写有效尺寸（英寸），或选择无配置／待定；当前值：{text or "空"}')
    return '[待定]' + (text or SCREEN_NAMES[no] + '尺寸未填写')


def validate_snapshot_screens(snap):
    for cell in snap.cells:
        no = cell['no']
        if no in SCREEN_NAMES:
            for trim, value in cell['values'].items():
                try:
                    cell['values'][trim] = normalize_screen(value, no, strict=True)
                except ValueError as exc:
                    raise ValueError(f'{trim} · {exc}') from exc
    return snap
