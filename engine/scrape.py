"""scrape — 汽车之家配置页抓取（playwright channel 驱动系统 Edge/Chrome）+ HTML 兜底

三步降级链：
1. scrape_open() 打开真实浏览器（headful，反爬特征最弱）→ 使用者手动勾年款/隐藏相同参数
2. scrape_capture() 跑生产级 EVALUATE_JS 抓全表 → canonical RawTable
3. 失败兜底：parse_saved_html()（浏览器 Ctrl+S 另存的 HTML）或 rawschema 直接吃旧 JSON

EVALUATE_JS 为 2026-09-11 启源Q05 实战验证版：
- 行 div[class*="style_row"]；列 = 行【直接子级】filter /style_col/i
  （切勿 querySelectorAll 递归——会匹配内层 i.style_col_dot_* 导致列数膨胀错位，元UP 踩坑）
- 双子项 style_col_sub 拆分保留各自 ●/○（506Max 中控 ●14.6|○15.6 案例）
- 符号 class 部分匹配 solid/outline（hash 后缀之家会换）
"""
from __future__ import annotations
import json
import re
from copy import deepcopy

CONFIG_URL = "https://www.autohome.com.cn/config/series/{sid}.html"

EVALUATE_JS = """
() => {
  const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
  const headers = Array.from(document.querySelectorAll('a[class*="style_col_spec_name"]'))
    .map(a => clean(a.textContent));
  const cell = c => {
    const subs = Array.from(c.querySelectorAll('div[class*="style_col_sub"]'))
      .filter(s => !s.querySelector('div[class*="style_col_sub"]'));
    if (subs.length) return subs.map(cell).join(' | ');
    const clone = c.cloneNode(true);
    clone.querySelectorAll('i').forEach(i => i.replaceWith(
      /outline/.test(i.className) ? '○' : /solid/.test(i.className) ? '●' : ''));
    return clean(clone.textContent) || '-';
  };
  const rows = Array.from(document.querySelectorAll('div[class*="style_row"]'));
  const out = [];
  for (const r of rows) {
    const cols = Array.from(r.children).filter(c => /(?:^|\\s)style_col(?:__|\\s|$)/i.test(c.className || ''));
    if (cols.length < 2) continue;
    const name = clean(cols[0].textContent).replace(/[●○]/g, '');
    const vals = cols.slice(1).map(cell);
    if (name) out.push({n: name, v: vals});
  }
  return JSON.stringify({headers, rowCount: out.length, rows: out});
}
"""

# 两步式抓取的全局会话状态（GUI 单窗口场景足够）
_SESSION = {"pw": None, "browser": None, "page": None, "series_id": ""}


def detect_browser() -> dict:
    """检测目标机可用的 playwright channel"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"available": False,
                "error": "playwright 未安装（pip install playwright；无需下载浏览器，走系统 Edge/Chrome）"}
    for ch in ("msedge", "chrome"):
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(channel=ch, headless=True)
                b.close()
            return {"available": True, "channel": ch}
        except Exception:
            continue
    return {"available": False, "error": "未检测到系统 Edge/Chrome，或 playwright driver 缺失"}


def scrape_open(series_id: str, channel: str = "msedge") -> dict:
    """第1步：打开配置页（headful），等使用者勾年款 + 隐藏相同参数"""
    from playwright.sync_api import sync_playwright
    sid = re.sub(r"\D", "", series_id) or series_id
    pw = sync_playwright().start()
    browser = pw.chromium.launch(channel=channel, headless=False)
    page = browser.new_page()
    page.goto(CONFIG_URL.format(sid=sid), wait_until="domcontentloaded", timeout=60000)
    _SESSION.update(pw=pw, browser=browser, page=page, series_id=sid)
    return {"ok": True, "url": page.url,
            "hint": "请在弹出的浏览器中：①勾选目标年款、取消其他年款 ②勾选「隐藏相同参数」，然后回本窗口点「确认抓取」"}


def scrape_capture(model: str = "") -> "RawTable":
    """第2步：跑 EVALUATE_JS 抓全表 → canonical RawTable，随后关闭浏览器"""
    from . import rawschema
    from .acquire import validate
    page = _SESSION.get("page")
    if page is None:
        raise RuntimeError("未打开配置页，请先执行 scrape_open")
    page.wait_for_selector('div[class*="style_row"]', timeout=30000)
    out = page.evaluate(EVALUATE_JS)
    close_browser()
    data = json.loads(out) if isinstance(out, str) else out
    if not data.get("rows"):
        raise RuntimeError("抓到 0 行——页面可能未加载完整或被反爬拦截；请重试或用「导入 HTML」兜底")
    if any(not header for header in data.get('headers', [])):
        raise ValueError('未找到完整版型表头，请等配置表加载完成后重试。')
    validate(data)
    raw = rawschema.from_compact(data, series_id=_SESSION.get("series_id", ""))
    if model:
        raw.model = model
    return raw


def close_browser():
    for key in ("browser", "pw"):
        obj = _SESSION.get(key)
        if obj is not None:
            try:
                obj.close() if key == "browser" else obj.stop()
            except Exception:
                pass
    _SESSION.update(pw=None, browser=None, page=None)


def scrape_series(series_id: str, channel: str = "msedge", model: str = "") -> "RawTable":
    """一步式自动抓取（不推荐：年款 checkbox 未人工确认，可能混入老款）"""
    scrape_open(series_id, channel)
    page = _SESSION["page"]
    try:
        page.wait_for_timeout(3000)
        return scrape_capture(model)
    finally:
        close_browser()


# ---------- HTML 兜底解析 ----------

def parse_saved_html(path: str, series_id: str = "") -> "RawTable":
    """解析浏览器另存的汽车之家配置页 HTML（lxml），逻辑与 EVALUATE_JS 对齐"""
    try:
        from lxml import html as LH
    except ImportError:
        raise RuntimeError("HTML 解析需要 lxml：pip install lxml")
    from . import rawschema
    from .acquire import validate
    with open(path, encoding="utf-8", errors="ignore") as f:
        doc = LH.fromstring(f.read())
    rows_el = doc.xpath('//div[contains(@class,"style_row")]')
    if not rows_el:
        raise RuntimeError("HTML 中未找到 style_row——可能保存时页面未加载完整（动态页需等表格出现后再 Ctrl+S）")

    def clean(text):
        return re.sub(r"\s+", " ", text or "").strip()

    def cell_text(el):
        subs = el.xpath('.//div[contains(@class,"style_col_sub")][not(.//div[contains(@class,"style_col_sub")])]')
        if subs:
            return ' | '.join(cell_text(sub) for sub in subs)
        clone = deepcopy(el)
        for icon in clone.xpath('.//i'):
            cls = icon.get('class') or ''
            icon.clear(keep_tail=True)
            icon.text = '○' if 'outline' in cls else ('●' if 'solid' in cls else '')
        return clean(clone.text_content()) or '-'

    headers = [clean(h.text_content()) for h in doc.xpath('//a[contains(@class,"style_col_spec_name")]')]
    if not headers or any(not h for h in headers):
        raise ValueError('HTML 中未找到完整版型表头，请等配置表加载完成后重新保存。')
    rows = []
    for r in rows_el:
        cols = [c for c in r if re.search(r'(?:^|\s)style_col(?:__|\s|$)', c.get("class") or "", re.I)]
        if len(cols) < 2:
            continue
        name = re.sub(r"[●○]", "", clean(cols[0].text_content()))
        if name:
            rows.append({'n': name, 'v': [cell_text(c) for c in cols[1:]]})
    data = {'headers': headers, 'rows': rows}
    validate(data)
    raw = rawschema.from_compact(data, series_id=series_id)
    raw.source = 'html'
    return raw
