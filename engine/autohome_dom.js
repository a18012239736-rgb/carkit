() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const heads = [...document.querySelectorAll('a[class*="style_col_spec_name"]')];
  const headers = heads.map(a => clean(a.textContent));
  const ids = heads.map(a => (a.href.match(/\/spec\/(\d+)/) || [])[1] || '');
  const filters = [...document.querySelectorAll('label')].filter(l => /隐藏相同参数|隐藏暂无内容/.test(l.textContent));
  if (filters.some(l => l.querySelector('input')?.checked)) throw Error('请取消隐藏相同参数和隐藏暂无内容后再抓取');
  const cell = el => {
    const subs = [...el.querySelectorAll('div[class*="style_col_sub"]')];
    if (subs.length) return subs.map(cell).join(' | ');
    const clone = el.cloneNode(true);
    clone.querySelectorAll('i').forEach(i => i.replaceWith(/outline/.test(i.className) ? '○' : /solid/.test(i.className) ? '●' : ''));
    // Keep position-specific symbols (主●/副○), not a single symbol for the whole cell.
    return clean(clone.textContent) || '-';
  };
  const rows = [...document.querySelectorAll('div[class*="style_row"]')].map(r => {
    const cols = [...r.children].filter(c => /(?:^|\s)style_col__/.test(c.className || ''));
    if (cols.length < 2) return null;
    return {n:clean(cols[0].textContent), v:cols.slice(1).map(cell)};
  }).filter(Boolean);
  const total = (document.body.innerText.match(/共\s*(\d+)\s*款车型/) || [])[1];
  const years = [...document.querySelectorAll('input[type="checkbox"]')].map(i=>i.value).filter(v=>/^\d{4}$/.test(v));
  return {headers, ids, rows, rowCount:rows.length, expectedCount:total ? Number(total) : null, years, url:location.href};
}
