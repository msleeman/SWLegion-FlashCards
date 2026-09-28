"""Read keyword rules text from Legion Helper (https://legion.takras.net/).

Legion Helper renders each keyword page in the browser: the HTML it serves
has no rules text, which is why the old requests/BeautifulSoup scraper came
back empty for every keyword (Spur, Deflect, Low Profile...) and only got a
one-line meta description for concept pages. This script loads the pages the
way a visitor does -- a headless browser, one page at a time, with a pause
between pages -- and reads the rendered text. Nothing else about the site is
touched; robots.txt allows these pages.

The page list is the site's own keyword index: the home page, with every
letter expanded (about 310 entries).

Output goes to data/legion_helper.json, which IS committed, so a normal
rebuild never needs to visit the site. Keyed by page slug:

    {"spur": {"n": "Spur", "t": "When a unit with the Spur keyword ..."}}

  n  the page's keyword name (its heading)
  t  the rules text: paragraphs, then any example, separated by blank lines.
     Rules icons are written as text ([SURGE: BLOCK], [RANGE 1], ...).

Run it when Legion Helper updates its rules reference:

    py legion_helper.py            # read pages not cached yet
    py legion_helper.py --all      # re-read every page
    py legion_helper.py spur aim   # re-read just these slugs
"""
import json
import os
import re
import sys
import time

from src.config import BASE
from src.scrape import _ICON_TITLE_MAP, _TOKEN_NAME_MAP

CACHE = os.path.join('data', 'legion_helper.json')
PAUSE = 1.0   # seconds between pages -- be a polite visitor

# Runs in the page: expand every letter of the home page index and list the
# keyword links it shows.
_INDEX_JS = r'''async () => {
  const heads=[...document.querySelectorAll('*')]
    .filter(e=>e.children.length===0&&/^[A-Z]$/.test(e.textContent.trim()));
  for(const h of heads){ h.click(); await new Promise(r=>setTimeout(r,150)); }
  await new Promise(r=>setTimeout(r,800));
  const seen=new Map();
  for(const a of document.querySelectorAll('a[class*="keyword"]')){
    const h=a.getAttribute('href')||'';
    const m=/^\/([a-z0-9_\-]+)\/?$/i.exec(h);
    if(m&&!seen.has(m[1])) seen.set(m[1], a.innerText.trim().replace(/\s+/g,' '));
  }
  return [...seen.entries()];
}'''

# Runs in the page: the rendered rules text. Icons become their title text,
# mapped by Python afterwards; the "Related keywords" block is dropped.
_PAGE_JS = r'''() => {
  const c=document.querySelector('div[class*="contentContainer"]');
  if(!c) return null;
  const h=document.querySelector('h2');
  const clone=c.cloneNode(true);
  clone.querySelectorAll('[id="related"], [class*="related"]').forEach(e=>e.remove());
  clone.querySelectorAll('img').forEach(img=>{
    const key=(img.getAttribute('title')||img.getAttribute('alt')||'').trim();
    img.replaceWith(document.createTextNode('\u0000'+key+'\u0001'));
  });
  // Accordion headers ("Example: ...") are labels, not rules.
  clone.querySelectorAll('button').forEach(b=>b.remove());
  const blocks=[];
  const walk=e=>{
    for(const k of e.children){
      const cls=String(k.className||'');
      if(/paragraph/.test(cls)||k.tagName==='P'||k.tagName==='LI'){
        const t=k.textContent.replace(/\s+/g,' ').trim(); if(t) blocks.push(t);
      } else walk(k);
    }
  };
  walk(clone);
  if(!blocks.length){ const t=clone.textContent.replace(/\s+/g,' ').trim(); if(t) blocks.push(t); }
  return {n:h?h.textContent.trim():'', blocks};
}'''


def _icon(key):
    """Text for an icon's title/alt: "block surge" -> "[SURGE: BLOCK]"."""
    k = key.strip().lower()
    if k in _ICON_TITLE_MAP:
        return _ICON_TITLE_MAP[k]
    stem = re.sub(r'\.[^.]+$', '', k.rsplit('/', 1)[-1])
    if '/tokens/' in k or 'tokens/' in k:
        return _TOKEN_NAME_MAP.get(stem, f'[{stem.upper()} TOKEN]')
    if stem in _ICON_TITLE_MAP:
        return _ICON_TITLE_MAP[stem]
    return f'[{stem.replace("-", " ").upper()}]' if stem else ''


def _clean(text):
    text = re.sub('\u0000([^\u0001]*)\u0001', lambda m: _icon(m.group(1)), text)
    return re.sub(r'\s+([.,;:])', r'\1', re.sub(r'[ \t]+', ' ', text)).strip()


def main():
    from playwright.sync_api import sync_playwright

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    redo_all = '--all' in sys.argv
    out = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding='utf-8') as f:
            out = json.load(f)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(BASE + '/', wait_until='networkidle')
        index = page.evaluate(_INDEX_JS)
        print(f'Legion Helper index: {len(index)} entries ({len(out)} cached)')

        if args:
            todo = [(s, n) for s, n in index if s in args]
        else:
            todo = [(s, n) for s, n in index if redo_all or s not in out]
        print(f'{len(todo)} page(s) to read')

        for i, (slug, label) in enumerate(todo, 1):
            try:
                page.goto(f'{BASE}/{slug}/', wait_until='domcontentloaded')
                page.wait_for_selector('div[class*="contentContainer"]', timeout=15000)
                page.wait_for_timeout(300)
                got = page.evaluate(_PAGE_JS)
            except Exception as e:
                print(f'  [{i}/{len(todo)}] {slug}: FAILED {e.__class__.__name__}')
                time.sleep(PAUSE)
                continue
            text = '\n\n'.join(_clean(b) for b in (got or {}).get('blocks', []) if _clean(b))
            if text:
                out[slug] = {'n': (got.get('n') or label).strip(), 't': text}
            print(f'  [{i}/{len(todo)}] {slug[:40]:40} {len(text):5d} chars')
            if i % 25 == 0:
                _save(out)
            time.sleep(PAUSE)
        browser.close()
    _save(out)
    print(f'\nwrote {CACHE}: {len(out)} pages')


def _save(out):
    os.makedirs('data', exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == '__main__':
    sys.exit(main())
