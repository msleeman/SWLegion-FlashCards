"""
HTML rendering and unit DB builder for SWLegion-FlashCards.
"""
import os
import re
import json

import requests

from src.config import HERE, CACHE_DIR, TEMPLATE_DIR, HEADERS


def build_unit_db_js():
    """Return a compact JavaScript const UNIT_DB = {...}; string from the LegionHQ2 bundle.

    Downloads and parses the LegionHQ2 JS bundle (cached to legionhq2_units.json).
    Returns an empty object string if download fails.
    """
    cache_path = os.path.join(CACHE_DIR, "legionhq2_units.json")
    unit_db = None

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                unit_db = json.load(f)
            print(f"  (unit DB loaded from cache: {len(unit_db)} units)")
        except Exception:
            unit_db = None

    if unit_db is None:
        print("  Fetching LegionHQ2 unit database...")
        try:
            r = requests.get("https://legionhq2.com/list/empire", headers=HEADERS, timeout=15)
            m = re.search(r'src="(/static/js/main\.[^"]+\.js)"', r.text)
            if not m:
                print("  WARN: could not find JS bundle URL")
                return "const UNIT_DB = {};"
            bundle_url = "https://legionhq2.com" + m.group(1)
            print(f"  Fetching bundle: {bundle_url}")
            rb = requests.get(bundle_url, headers=HEADERS, timeout=60)
            rb.raise_for_status()
            content = rb.text

            start_marker = "JSON.parse('"
            start = content.find(start_marker)
            if start < 0:
                print("  WARN: could not find unit JSON in bundle")
                return "const UNIT_DB = {};"
            start += len(start_marker)

            i = start
            json_end = -1
            while i < len(content):
                c = content[i]
                if c == '\\':
                    i += 2
                    continue
                if c == "'":
                    json_end = i
                    break
                i += 1

            if json_end < 0:
                print("  WARN: could not find end of unit JSON")
                return "const UNIT_DB = {};"

            json_str = content[start:json_end]

            def js_unescape(s):
                result = []
                i = 0
                while i < len(s):
                    if s[i] == '\\' and i + 1 < len(s):
                        nc = s[i+1]
                        if nc == '\\': result.append('\\')
                        elif nc == "'": result.append("'")
                        elif nc == '"': result.append('"')
                        elif nc == 'n': result.append('\n')
                        elif nc == 'r': result.append('\r')
                        elif nc == 't': result.append('\t')
                        elif nc == '/': result.append('/')
                        else: result.append('\\'); result.append(nc)
                        i += 2
                    else:
                        result.append(s[i]); i += 1
                return ''.join(result)

            json_decoded = js_unescape(json_str)
            data = json.loads(json_decoded)

            def extract_kw_names(kw_list):
                names = []
                for kw in (kw_list or []):
                    if isinstance(kw, str):
                        names.append(kw)
                    elif isinstance(kw, dict):
                        n = kw.get('name', '')
                        v = kw.get('value')
                        names.append(f"{n} {v}" if v is not None else n)
                return names

            unit_db = {}
            for uid, card in data.items():
                if card.get('cardType') != 'unit':
                    continue
                unit_db[uid] = {
                    'n': card.get('cardName', ''),
                    't': card.get('title', ''),
                    'f': card.get('faction', ''),
                    'r': card.get('rank', ''),
                    'k': extract_kw_names(card.get('keywords', [])),
                    'i': card.get('imageName', ''),
                }

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(unit_db, f, ensure_ascii=False)
            print(f"  Unit DB: {len(unit_db)} units cached to legionhq2_units.json")

        except Exception as e:
            print(f"  WARN: could not build unit DB: {e}")
            return "const UNIT_DB = {};"

    lines = ['const UNIT_DB = {']
    for uid, u in sorted(unit_db.items()):
        entry = json.dumps({k: v for k, v in u.items() if v}, ensure_ascii=False)
        lines.append(f'  {json.dumps(uid)}:{entry},')
    lines.append('};')
    return '\n'.join(lines)


def build_tta_db_js():
    """Return a compact JS const TTA_UNITS = {...}; mapping hex unit ID -> {n, f} from TTA API."""
    cache_path = os.path.join(CACHE_DIR, "tta_units.json")
    data = None

    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding='utf-8') as f:
                data = json.load(f)
            print(f"  (TTA units loaded from cache: {len(data)} units)")
        except Exception:
            data = None

    if data is None:
        print("  Fetching TTA unit database...")
        try:
            r = requests.get('https://tabletopadmiral.com/api/units', headers=HEADERS, timeout=30)
            r.raise_for_status()
            units = r.json()
            faction_map = {'1': 'rebels', '2': 'empire', '3': 'neutral',
                           '4': 'republic', '5': 'separatist', '6': 'mercenary'}
            data = {}
            for u in units:
                uid = int(u['id'])
                hex_id = format(uid, 'x')
                entry = {'n': u.get('name', '')}
                fkey = str(u.get('faction_fkey') or '')
                if fkey in faction_map:
                    entry['f'] = faction_map[fkey]
                data[hex_id] = entry
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"  TTA DB: {len(data)} units cached to tta_units.json")
        except Exception as e:
            print(f"  WARN: could not build TTA DB: {e}")
            return "const TTA_UNITS = {};"

    lines = ['const TTA_UNITS = {']
    for hex_id, u in sorted(data.items(), key=lambda x: int(x[0], 16)):
        entry = json.dumps(u, ensure_ascii=False)
        lines.append(f'  {json.dumps(hex_id)}:{entry},')
    lines.append('};')
    return '\n'.join(lines)


def get_version():
    """Return version string from git describe, e.g. 'v5.0.0' or 'v5.0.0-3-gabc1234'."""
    import subprocess
    try:
        ver = subprocess.check_output(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            cwd=HERE, text=True, stderr=subprocess.DEVNULL
        ).strip()
        return ver
    except Exception:
        return 'dev'


def build_html(card_data):
    with open(os.path.join(TEMPLATE_DIR, 'index.html'), encoding='utf-8') as f:
        html = f.read()
    with open(os.path.join(TEMPLATE_DIR, 'app.css'), encoding='utf-8') as f:
        css = f.read()
    with open(os.path.join(TEMPLATE_DIR, 'app.js'), encoding='utf-8') as f:
        js = f.read()

    fish_js    = json.dumps(card_data, ensure_ascii=False)
    base_names = json.dumps([c["name"] for c in card_data], ensure_ascii=False)
    unit_db_js = build_unit_db_js()
    tta_db_js  = build_tta_db_js()
    js = js.replace("/*CARD_JSON*/", fish_js)
    js = js.replace("/*BASE_NAMES*/", base_names)
    js = js.replace("/*UNIT_DB_JSON*/", unit_db_js)
    js = js.replace("/*TTA_DB_JS*/", tta_db_js)

    html = html.replace("/*STYLE_CSS*/", css)
    html = html.replace("/*APP_JS*/", js)

    ver = get_version()
    html = html.replace("{{VERSION}}", ver)
    print(f"  Version: {ver}")
    return html
