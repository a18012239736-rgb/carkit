"""Standalone acquisition. All Playwright objects stay on one owning worker thread."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import datetime
import json
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
        if len(rows) < 30 or not required <= names:
            raise ValueError('配置表未完整加载，不能将缺失行当作无配置。')
    price = next((r for r in rows if r['n'] == '厂商指导价(元)'), None)
    if not price or not any(rawschema._parse_price(v) is not None for v in price['v']):
        raise ValueError('配置表没有读到任何有效指导价，请先核对网页，不能以0元代替。')


def filter_years(data, years):
    """Keep the requested model-year columns even when a site popup blocks its filters."""
    years = sorted({str(y).strip() for y in years if re.fullmatch(r'20\d{2}', str(y).strip())})
    if not years:
        return data
    indexes = [i for i, header in enumerate(data.get('headers', []))
               if any(re.search(rf'{re.escape(year)}\s*款', header) for year in years)]
    if not indexes:
        available = sorted(set(re.findall(r'20\d{2}(?=\s*款)', ' '.join(data.get('headers', [])))))
        raise ValueError(f'抓取结果中没有找到所选年款：{"、".join(years)}；当前读取到：{"、".join(available) or "未识别"}')
    data['headers'] = [data['headers'][i] for i in indexes]
    for row in data.get('rows', []):
        row['v'] = [row.get('v', [])[i] for i in indexes]
    data['expectedCount'] = len(indexes)
    return data


class Acquirer:
    def __init__(self):
        self.pw = self.browser = self.page = None
        self.sid = ''
        self.mode = ''
        self.year = ''
        self.selected_years = []
        self.discontinued_year = ''

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
        for channel in ('chrome','msedge'):
            try:
                self.browser = self.pw.chromium.launch(channel=channel, headless=False)
                self.page = self.browser.new_page(viewport={'width':1440,'height':960})
                return
            except Exception as exc:
                errors.append(str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
                if self.browser is not None:
                    try: self.browser.close()
                    except Exception: pass
                self.browser = self.page = None
        self.close()
        raise RuntimeError('未能启动Edge或Chrome，请安装其中一个浏览器。'+'; '.join(errors))

    def search(self, query, year=''):
        if not str(query).strip(): raise ValueError('请输入车型名称。')
        self.start()
        self.mode = 'search'
        self.year = str(year or '').strip()
        self.selected_years = []
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
                if len(results)==1: return self.fetch(results[0]['id'])
                return {'candidates':results}
            self.page.wait_for_timeout(500)
        return {'needs_browser':True,'message':'未读到车型结果。若浏览器提示验证，请完成后点“继续读取”；也可输入汽车之家配置页网址。'}

    def fetch(self, sid, year=None):
        sid = series_id(sid)
        if not sid: raise ValueError('车系编号或汽车之家网址无效。')
        if self.page is None: self.start()
        if year is not None:
            self.year = str(year or '').strip()
        self.selected_years = []
        self.discontinued_year = ''
        self.sid, self.mode = sid, 'config'
        self.page.goto(f'https://www.autohome.com.cn/config/series/{sid}.html', wait_until='domcontentloaded', timeout=45000)
        return self.filter_options()

    def filter_options(self):
        self.page.locator('a[class*="style_col_spec_name"]').first.wait_for(timeout=20000)
        filters = self.page.evaluate("""() => [...document.querySelectorAll('div.tw-mb-3')].map(g => {
          const title=g.querySelector(':scope > span')?.textContent.trim();
          const values=[...g.querySelectorAll('input[type=checkbox]')].map(i=>({value:i.value,label:i.parentElement.parentElement.textContent.trim()}));
          return title && values.length ? {label:title,values} : null;
        }).filter(Boolean)""")
        menu = self._discontinued_menu()
        if menu is not None:
            values = [{'value': 'unsale:'+name.strip(), 'label': name.strip()+'（停售）', 'exclusive': True}
                      for name in menu.get_by_role('menuitem').all_text_contents() if name.strip()]
            self.page.keyboard.press('Escape')
            self.page.mouse.move(0, 0)
            year_filter = next((f for f in filters if f['label'] == '年款'), None)
            if year_filter is None:
                year_filter = {'label': '年款', 'values': []}
                filters.insert(0, year_filter)
            year_filter['values'].extend(values)
        return {'filters': filters}

    def _filter_group(self, label):
        return self.page.locator('div.tw-mb-3').filter(
            has=self.page.locator(':scope > span', has_text=re.compile(r'^'+re.escape(label)+r'$'))).first

    def _discontinued_menu(self):
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        trigger = self._filter_group('年款').locator('[class*="dropdown-trigger"]').first
        if not trigger.count():
            return None
        menu = self.page.locator('[role="menu"]:visible').first
        for _ in range(3):
            try:
                close = self.page.locator('.ant-modal-wrap:visible .cps-drop-modal button[aria-label="关闭"]').first
                if close.count():
                    close.click(timeout=2000)
                # Re-enter the trigger and wait for actual options, not an empty menu container.
                self.page.mouse.move(0, 0)
                trigger.hover(timeout=2000)
                menu.get_by_role('menuitem').first.wait_for(timeout=2000)
                return menu
            except PlaywrightTimeoutError:
                pass
        raise ValueError('未能展开停售年款，请关闭汽车之家页面的遮挡弹窗，再重新搜索车型。')

    def _select_year_source(self, stopped=''):
        group = self._filter_group('年款')
        if not group.count():
            if stopped:
                raise ValueError('网页没有找到停售年款筛选，请重新搜索车型。')
            return
        heads = self.page.locator('a[class*="style_col_spec_name"]')
        before = heads.evaluate_all('(els) => els.map(e => e.href)')
        if stopped:
            trigger = group.locator('span').filter(has_text=re.compile(r'^(?:20\d{2}款\s*)?停售$')).first
            if trigger.count() and trigger.inner_text().strip() == stopped+' 停售':
                return
            menu = self._discontinued_menu()
            if menu is None:
                raise ValueError('网页没有找到停售年款筛选，请重新搜索车型。')
            menu.get_by_role('menuitem', name=stopped, exact=True).click(timeout=5000)
        else:
            onsale = group.locator('input[type="radio"][value="onsale"]')
            if not onsale.count() or onsale.is_checked():
                return
            was_stopped = group.locator('span').filter(has_text=re.compile(r'^20\d{2}款\s+停售$')).count()
            onsale.check(force=True)
            if not was_stopped:
                return
        # A discontinued year loads a different table asynchronously; the old table stays visible meanwhile.
        self.page.wait_for_function("""before => {
          const heads=[...document.querySelectorAll('a[class*="style_col_spec_name"]')];
          return heads.length && JSON.stringify(heads.map(e=>e.href)) !== JSON.stringify(before);
        }""", arg=before, timeout=30000)

    def apply_filters(self, selected=None):
        selected = selected or {}
        year_values = [str(v) for label, values in selected.items() if '年' in str(label) for v in values]
        stopped = [v.removeprefix('unsale:') for v in year_values if v.startswith('unsale:')]
        if stopped and (len(stopped) != 1 or len(year_values) != 1):
            raise ValueError('停售年款请一次选择一个，不能与在售年款同时抓取。')
        self.year = ''
        self.selected_years = sorted({match.group(0) for label, values in selected.items() if '年' in str(label)
                                      for value in values if (match := re.search(r'20\d{2}', str(value)))})
        try: self.page.keyboard.press('Escape')
        except Exception: pass
        self._select_year_source(stopped[0] if stopped else '')
        self.discontinued_year = stopped[0] if stopped else ''
        labels = self.page.locator('div.tw-mb-3').evaluate_all("""groups => groups
          .filter(g=>g.querySelector('input[type="checkbox"]'))
          .map(g=>g.querySelector(':scope > span')?.textContent.trim()).filter(Boolean)""")
        for label in dict.fromkeys(labels + list(selected)):
            values = selected.get(label, [])
            if '年' in str(label) and stopped:
                continue
            group = self._filter_group(label)
            boxes = group.locator('input[type="checkbox"]')
            for value in boxes.evaluate_all('(els) => els.filter(e=>e.checked).map(e=>e.value)'):
                if value not in values:
                    group.locator(f'input[type="checkbox"][value={json.dumps(value, ensure_ascii=False)}]').uncheck(force=True)
            for value in values:
                box = group.locator(f'input[type="checkbox"][value={json.dumps(str(value), ensure_ascii=False)}]').first
                if not box.count():
                    raise ValueError(f'网页没有找到筛选条件：{label} / {value}，请重新搜索车型。')
                if not box.is_checked():
                    try:
                        box.check(force=True)
                    except Exception:
                        # Autohome rerenders the filter group after a selection;
                        # the requested value may already be selected in the new DOM.
                        self.page.wait_for_timeout(250)
                        if box.count() and not box.is_checked():
                            box.click(force=True)
                if not box.is_checked():
                    raise ValueError(f'筛选条件未生效：{label} / {value}，请重新抓取。')
        self.page.wait_for_timeout(900)
        return self.capture(year='')

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
        if self.discontinued_year:
            selected = self._filter_group('年款').locator('span').filter(
                has_text=re.compile(r'^'+re.escape(self.discontinued_year)+r'\s+停售$'))
            if not selected.count():
                raise ValueError('停售年款筛选已变化，请重新选择抓取条件，避免混入在售车型。')
        years = self._select_year(year) if year else []
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
        filter_years(data, [year] if year else self.selected_years)
        validate(data)
        self.page.evaluate('window.scrollTo(0,0)')
        raw = rawschema.from_compact(data, series_id=self.sid, scraped_at=datetime.datetime.now().astimezone().isoformat(timespec='seconds'))
        raw.source=data['url']
        # Keep exact labels including 版; duplicate short names across years remain distinguishable.
        short=[re.sub(r'^.*?\d{4}款\s*','',h) for h in data['headers']]
        short_counts = Counter(short)
        for t,name in zip(raw.trims,short):
            t.short = name if short_counts[name]==1 else t.full
        return {'raw':raw.to_dict(),'years':years or data.get('years',[]),'complete':True}

    def resume(self):
        if not self.page: raise ValueError('请先输入车型开始抓取。')
        return self.search_results(year=self.year) if self.mode=='search' else self.capture(year=self.year)
