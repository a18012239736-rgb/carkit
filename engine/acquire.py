"""Standalone acquisition. All Playwright objects stay on one owning worker thread."""
from __future__ import annotations
from pathlib import Path
import datetime
import re
import time
from urllib.parse import quote, urlparse
from . import rawschema

DOM_JS = Path(__file__).with_name('autohome_dom.js').read_text(encoding='utf-8')
SEARCH_JS = r'''() => {
 const found = new Map();
 for (const e of document.querySelectorAll('[data-ext],a[href]')) {
   let d={}; try {d=JSON.parse(e.getAttribute('data-ext')||'{}')} catch {}
   const u=d.url || e.href || '';
   const m=u.match(/^https:\/\/www\.autohome\.com\.cn\/(?:config\/series\/)?(\d+)(?:\.html|\/)/);
   if (!m) continue;
   const text=e.textContent.trim();
   if (text.endsWith('_最新车系信息')) found.set(m[1],{id:m[1],name:text.replace(/_最新车系信息$/,'')});
 }
 return [...found.values()];
}'''


def series_id(value):
    value = str(value).strip()
    if re.fullmatch(r'\d{1,8}', value):
        return value
    u = urlparse(value)
    if u.hostname == 'www.autohome.com.cn':
        m = re.fullmatch(r'/(?:config/series/)?(\d+)(?:\.html|/)', u.path)
        if m:
            return m[1]
    return None


def validate(data, live=False):
    headers, rows = data.get('headers', []), data.get('rows', [])
    if not headers or not rows:
        raise ValueError('没有读到完整配置表，请检查页面加载或网站验证。')
    if len(set(headers)) != len(headers):
        raise ValueError('版型列头重复，无法可靠绑定配置。')
    bad = [r['n'] for r in rows if len(r.get('v', [])) != len(headers)]
    if bad:
        raise ValueError('配置列数与版型不一致：'+'、'.join(bad[:5]))
    if live:
        if data.get('expectedCount') != len(headers):
            raise ValueError('网页显示的版型总数与已读取列数不一致，已停止导出，避免漏版型。')
        names = {r['n'] for r in rows}
        # 行数随汽车之家改版和车型类别变化；用稳定的关键行判断完整加载，
        # 不把“短车型配置表”误判成失败，也不把半截动态表当成无配置。
        required = {'厂商指导价(元)', '能源类型', '车身结构'}
        range_names = {'CLTC纯电续航里程(km)', 'WLTC纯电续航里程(km)', 'NEDC纯电续航里程(km)'}
        if len(rows) < 30 or not required <= names or not names & range_names:
            raise ValueError('配置表未完整加载，不能将缺失行当作无配置。')
    price = next((r for r in rows if r['n'] == '厂商指导价(元)'), None)
    if not price or any(rawschema._parse_price(v) is None for v in price['v']):
        raise ValueError('有版型缺少有效指导价，请先核对网页，不能以0元代替。')


class Acquirer:
    def __init__(self):
        self.pw = self.browser = self.page = None
        self.sid = ''
        self.mode = ''
        self.year = ''

    def close(self):
        if self.browser:
            try: self.browser.close()
            except Exception: pass
        if self.pw:
            try: self.pw.stop()
            except Exception: pass
        self.pw = self.browser = self.page = None

    def start(self):
        from playwright.sync_api import sync_playwright
        self.close()
        self.pw = sync_playwright().start()
        errors = []
        for channel in ('msedge', 'chrome'):
            try:
                self.browser = self.pw.chromium.launch(channel=channel, headless=False)
                self.page = self.browser.new_page(viewport={'width':1440,'height':960})
                return
            except Exception as exc: errors.append(str(exc).splitlines()[0])
        self.close()
        raise RuntimeError('未能启动Edge或Chrome，请安装其中一个浏览器。'+'; '.join(errors))

    def search(self, query, year=''):
        if not str(query).strip(): raise ValueError('请输入车型名称。')
        self.start()
        self.mode = 'search'
        self.year = str(year or '').strip()
        sid = series_id(query)
        if sid:
                return self.fetch(sid, year=year)
        self.page.goto('https://sou.autohome.com.cn/zonghe?q='+quote(query)+'&charset=utf8', wait_until='domcontentloaded', timeout=45000)
        return self.search_results(year=year)

    def search_results(self, year=''):
        deadline = time.monotonic()+20
        while time.monotonic()<deadline:
            results=self.page.evaluate(SEARCH_JS)
            if results:
                if len(results)==1: return self.fetch(results[0]['id'], year=year)
                return {'candidates':results}
            self.page.wait_for_timeout(500)
        return {'needs_browser':True,'message':'未读到车型结果。若浏览器提示验证，请完成后点“继续读取”；也可输入汽车之家配置页网址。'}

    def fetch(self, sid, year=None):
        sid = series_id(sid)
        if not sid: raise ValueError('车系编号或汽车之家网址无效。')
        if self.page is None: self.start()
        if year is not None:
            self.year = str(year or '').strip()
        self.sid, self.mode = sid, 'config'
        self.page.goto(f'https://www.autohome.com.cn/config/series/{sid}.html', wait_until='domcontentloaded', timeout=45000)
        return self.capture(year=self.year)

    def _select_year(self, year=''):
        boxes = self.page.locator('input[type="checkbox"][value^="20"]')
        years = []
        for i in range(boxes.count()):
            value = boxes.nth(i).get_attribute('value')
            if value and re.fullmatch(r'20\d{2}', value): years.append(value)
        years = sorted(set(years), reverse=True)
        target = str(year).strip() if year else (years[0] if years else '')
        if not target or target not in years:
            if year: raise ValueError(f'网页没有找到{year}款，当前可选年款：{"、".join(years) or "未识别"}')
            return years
        box = self.page.locator(f'input[type="checkbox"][value="{target}"]').first
        if box.count() and not box.is_checked():
            box.check()
            self.page.wait_for_timeout(800)
        return years

    def capture(self, year=''):
        try:
            self.page.locator('a[class*="style_col_spec_name"]').first.wait_for(timeout=20000)
        except Exception:
            return {'needs_browser':True,'message':'配置页尚未加载。请在浏览器完成网站验证，再点“继续读取”。'}
        years = self._select_year(year)
        for name in ('隐藏相同参数','隐藏暂无内容'):
            inp = self.page.locator('label').filter(has_text=name).locator('input')
            if inp.count() and inp.first.is_checked(): inp.first.uncheck()
        previous = None
        data = None
        for _ in range(20):
            self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            self.page.wait_for_timeout(400)
            data = self.page.evaluate(DOM_JS)
            signature=(data['headers'],data['rows'])
            if signature==previous and len(data['rows'])>=60: break
            previous=signature
        validate(data, live=True)
        self.page.evaluate('window.scrollTo(0,0)')
        raw = rawschema.from_compact(data, series_id=self.sid, scraped_at=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
        raw.source=data['url']
        # Keep exact labels including 版; duplicate short names across years remain distinguishable.
        short=[re.sub(r'^.*?\d{4}款\s*','',h) for h in data['headers']]
        for t,name in zip(raw.trims,short):
            t.short = name if short.count(name)==1 else t.full
        return {'raw':raw.to_dict(),'years':years or data.get('years',[]),'complete':True}

    def resume(self):
        if not self.page: raise ValueError('请先输入车型开始抓取。')
        return self.search_results(year=self.year) if self.mode=='search' else self.capture(year=self.year)
