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

            def all_kw_names(card):
                """Collect keywords from both the card level and all weapon entries."""
                seen = set()
                result = []
                for kw in extract_kw_names(card.get('keywords', [])):
                    if kw not in seen:
                        seen.add(kw); result.append(kw)
                for weapon in card.get('weapons', []):
                    for kw in extract_kw_names(weapon.get('keywords', [])):
                        if kw not in seen:
                            seen.add(kw); result.append(kw)
                return result

            unit_db = {}
            for uid, card in data.items():
                if card.get('cardType') != 'unit':
                    continue
                unit_db[uid] = {
                    'n': card.get('cardName', ''),
                    't': card.get('title', ''),
                    'f': card.get('faction', ''),
                    'r': card.get('rank', ''),
                    'c': card.get('cost', 0),
                    'k': all_kw_names(card),
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


def build_upgrade_db_js():
    """Return a compact JS const UPGRADE_DB = {...}; mapping 2-char upgrade ID ->
    {n, c, k, i} (name, cost, keywords, card-art filename).

    Reuses the LegionHQ2 bundle cache (legionhq2_units.json stores only units, so we
    fetch the full raw bundle and pull upgrade cardType entries separately, cached to
    legionhq2_upgrades.json).
    """
    cache_path = os.path.join(CACHE_DIR, "legionhq2_upgrades.json")
    upgrade_db = None

    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                upgrade_db = json.load(f)
            print(f"  (upgrade DB loaded from cache: {len(upgrade_db)} upgrades)")
        except Exception:
            upgrade_db = None

    if upgrade_db is None:
        print("  Fetching LegionHQ2 upgrade database...")
        try:
            r = requests.get("https://legionhq2.com/list/empire", headers=HEADERS, timeout=15)
            m = re.search(r'src="(/static/js/main\.[^"]+\.js)"', r.text)
            if not m:
                print("  WARN: could not find JS bundle URL for upgrades")
                return "const UPGRADE_DB = {};"
            bundle_url = "https://legionhq2.com" + m.group(1)
            rb = requests.get(bundle_url, headers=HEADERS, timeout=60)
            rb.raise_for_status()
            content = rb.text

            start_marker = "JSON.parse('"
            start = content.find(start_marker)
            if start < 0:
                return "const UPGRADE_DB = {};"
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
                return "const UPGRADE_DB = {};"

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

            data = json.loads(js_unescape(json_str))

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

            def all_upgrade_kw_names(card):
                seen = set()
                result = []
                for kw in extract_kw_names(card.get('keywords', [])):
                    if kw not in seen:
                        seen.add(kw); result.append(kw)
                for weapon in card.get('weapons', []):
                    for kw in extract_kw_names(weapon.get('keywords', [])):
                        if kw not in seen:
                            seen.add(kw); result.append(kw)
                return result

            upgrade_db = {}
            for uid, card in data.items():
                if card.get('cardType') != 'upgrade':
                    continue
                # Include EVERY upgrade, even keyword-less ones. Two reasons:
                #  - freeform-text upgrades (Fire Control, Hit the Dirt) are
                #    themselves flashcards and must be name-matchable
                #  - the print-by-unit sheet needs cost + card art for whatever
                #    is actually equipped, keywords or not (Improvised Orders...)
                upgrade_db[uid] = {
                    'n': card.get('cardName', ''),
                    'c': card.get('cost', 0),
                    'k': all_upgrade_kw_names(card),
                    'i': card.get('imageName', ''),
                }

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(upgrade_db, f, ensure_ascii=False)
            print(f"  Upgrade DB: {len(upgrade_db)} upgrades with keywords cached")

        except Exception as e:
            print(f"  WARN: could not build upgrade DB: {e}")
            return "const UPGRADE_DB = {};"

    lines = ['const UPGRADE_DB = {']
    for uid, u in sorted(upgrade_db.items()):
        entry = json.dumps(u, ensure_ascii=False)
        lines.append(f'  {json.dumps(uid)}:{entry},')
    lines.append('};')
    return '\n'.join(lines)


def _tta_cost(rec):
    """Current points for a Tabletop Admiral unit/upgrade record.

    TTA carries four cost columns and picking the wrong one silently skews a
    whole list's total. Verified precedence, checked against what TTA's own
    listbuilder renders:

      revamp_cost        current (2.6 "revamp" edition) points -- authoritative
      current_cost       latest points update for cards with no revamp entry
      recent_active_cost
      original_cost      launch points; only right when nothing above is set

    e.g. XS-IV Assault Cannon is revamp 49 but original 48 / current 55, and
    Improvised Orders is current 5 but original 10.
    """
    for field in ('revamp_cost', 'current_cost', 'recent_active_cost', 'original_cost'):
        value = rec.get(field)
        if value is not None:
            return value
    return 0


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
            # TTA's rank enum, decoded by sampling known units per value.
            rank_map = {1: 'commander', 2: 'corps', 3: 'special',
                        4: 'support', 5: 'heavy', 6: 'operative'}
            data = {}
            for u in units:
                pub_id = u.get('public_id')
                if pub_id is None:
                    continue  # no public_id means this unit can't appear in a listbuilder URL
                hex_id = format(int(pub_id), 'x')
                entry = {'n': u.get('name', ''), 'c': _tta_cost(u)}
                fkey = str(u.get('faction_fkey') or '')
                if fkey in faction_map:
                    entry['f'] = faction_map[fkey]
                rank = rank_map.get(u.get('rank_fkey'))
                if rank:
                    entry['r'] = rank
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


def build_tta_upgrades_db_js():
    """Return a compact JS const TTA_UPGRADES = {...}; mapping hex upgrade ID -> {n} from TTA API.

    Mirrors build_tta_db_js() but for /api/upgrades. Tabletop Admiral listbuilder URLs encode
    both units and upgrades using each card's `public_id` field (NOT the database `id` field --
    those only coincide by chance for a handful of early/base-game cards, which is why only
    Stormtroopers/Scout Troopers used to resolve while everything else silently vanished).
    """
    cache_path = os.path.join(CACHE_DIR, "tta_upgrades.json")
    data = None

    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding='utf-8') as f:
                data = json.load(f)
            print(f"  (TTA upgrades loaded from cache: {len(data)} upgrades)")
        except Exception:
            data = None

    if data is None:
        print("  Fetching TTA upgrade database...")
        try:
            r = requests.get('https://tabletopadmiral.com/api/upgrades', headers=HEADERS, timeout=30)
            r.raise_for_status()
            upgrades = r.json()
            data = {}
            for u in upgrades:
                pub_id = u.get('public_id')
                if pub_id is None:
                    continue
                hex_id = format(int(pub_id), 'x')
                data[hex_id] = {'n': u.get('name', ''), 'c': _tta_cost(u)}
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"  TTA upgrade DB: {len(data)} upgrades cached to tta_upgrades.json")
        except Exception as e:
            print(f"  WARN: could not build TTA upgrade DB: {e}")
            return "const TTA_UPGRADES = {};"

    lines = ['const TTA_UPGRADES = {']
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
    unit_db_js       = build_unit_db_js()
    upgrade_db_js    = build_upgrade_db_js()
    tta_db_js        = build_tta_db_js()
    tta_upgrades_js  = build_tta_upgrades_db_js()
    js = js.replace("/*CARD_JSON*/", fish_js)
    js = js.replace("/*BASE_NAMES*/", base_names)
    js = js.replace("/*UNIT_DB_JSON*/", unit_db_js)
    js = js.replace("/*UPGRADE_DB_JSON*/", upgrade_db_js)
    js = js.replace("/*TTA_DB_JS*/", tta_db_js)
    js = js.replace("/*TTA_UPGRADES_JSON*/", tta_upgrades_js)

    html = html.replace("/*STYLE_CSS*/", css)
    html = html.replace("/*APP_JS*/", js)

    ver = get_version()
    from datetime import datetime, timezone
    build_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = html.replace("{{VERSION}}", ver)
    html = html.replace("{{BUILD_DATE}}", build_date)
    print(f"  Version: {ver}  Built: {build_date}")
    return html
