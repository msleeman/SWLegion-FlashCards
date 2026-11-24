#!/usr/bin/env python3
"""Rebuild dist/index.html from cached card data (no scraping).

Steps:
  1. Load cached keyword data from cache/card_data.json
  2. Re-apply image overrides (download from CDN if missing locally)
  3. Overlay official definitions from the PDF rulebook (if found)
  4. Regenerate dist/index.html
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from src.config import DIST_IMGDIR, CACHE_DIR, DIST_DIR, RULEBOOK_CREDIT, RULEBOOK_PDFS
from src.data_tables import KEYWORD_CARD_IMAGES
from src.overrides import (
    find_card_art, find_card_art_credit,
    _kw_lookup_key, _get_ext, safe_filename,
    _keyword_stem, find_manual_definition, find_manual_summary,
    apply_manual_overlays,
)
from src.scrape import (find_pdf, extract_keywords_from_pdf, fill_from_rulebook,
                        rulebook_matcher, apply_legion_helper_text,
                        retype_from_rulebook)
from src.images import (download_images, download_upgrade_card_images,
                        download_tta_card_images, download_command_card_images)
from src.render import build_html

# ── 1. Load cached card data ──────────────────────────────────────────────────
cache = os.path.join(CACHE_DIR, "card_data.json")
if not os.path.exists(cache):
    print("ERROR: cache/card_data.json not found. Run build_swlegion_v4.py first.")
    sys.exit(1)

with open(cache, "r", encoding="utf-8") as f:
    card_data = json.load(f)

print(f"Loaded {len(card_data)} cards from cache")

# ── 1b. Base cards added to data/base_keywords.json since the cache was made ──
# (e.g. the Flying Vehicles concepts from the 2026-11-30 rules). Their text
# comes from Legion Helper in step 4c; art, if any, from overrides/.
from src.scrape import load_base_keywords
# ...and drop cached base cards the base set no longer lists (Bane Tokens,
# dropped from the 2026-11-30 rules). The cache holds only base cards.
_base_names = {k["name"].lower() for k in load_base_keywords()}
_gone = [c["name"] for c in card_data if c["name"].lower() not in _base_names]
if _base_names and _gone:
    card_data = [c for c in card_data if c["name"].lower() in _base_names]
    print(f"  {len(_gone)} retired base card(s) dropped: {', '.join(_gone)}")
_have = {c["name"].lower() for c in card_data}
_new_base = [k for k in load_base_keywords() if k["name"].lower() not in _have]
for k in _new_base:
    art = find_card_art(k["name"])
    card_data.append({
        "name": k["name"], "definition": k["definition"], "summary": "",
        "type": k["type"], "imgs": [art] if art else [],
        "credit": "", "card_source": "",
        "art_credit": find_card_art_credit(k["name"]) or "", "units": "",
    })
if _new_base:
    print(f"  {len(_new_base)} base cards added that the cache predates")

# ── 2. Re-apply image overrides ───────────────────────────────────────────────
IMGDIR = DIST_IMGDIR
for c in card_data:
    art = find_card_art(c["name"])
    if art:
        c["imgs"] = [art]
        c["art_credit"] = find_card_art_credit(c["name"]) or ""
        continue
    lookup_key = _kw_lookup_key(c["name"])
    card_filename = KEYWORD_CARD_IMAGES.get(lookup_key)
    if card_filename:
        ext = _get_ext(card_filename)
        fname = safe_filename(c["name"], ext=ext)
        filepath = os.path.join(IMGDIR, fname)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            c["imgs"] = [f"images/{fname}"]
        else:
            img_paths, _ = download_images(c["name"], IMGDIR, max_imgs=1)
            if img_paths:
                c["imgs"] = img_paths

# ── 3. Overlay official definitions from PDF ─────────────────────────────────
def _norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

pdf_path = find_pdf()
if pdf_path:
    print(f"Overlaying PDF definitions from {os.path.basename(pdf_path)}...")
    try:
        pdf_dict = extract_keywords_from_pdf(pdf_path)
        if pdf_dict:
            lookup = rulebook_matcher(pdf_dict)
            overlaid = 0
            for c in card_data:
                match = lookup(c["name"])
                if match and match.get("definition"):
                    c["definition"] = match["definition"]
                    c["credit"] = RULEBOOK_CREDIT
                    overlaid += 1
            print(f"  {overlaid}/{len(card_data)} definitions replaced with PDF versions")
        else:
            print("  PDF extraction returned nothing — keeping cached definitions")
    except Exception as e:
        print(f"  PDF overlay failed: {e} — keeping cached definitions")
else:
    print("PDF not found — keeping cached definitions")
    print(f"  (place {RULEBOOK_PDFS[0]!r} in the project root or documents/ folder)")

# ── 4a. Inject cards for keywords that were never scraped but have an override ─
kw_map_path = os.path.join(HERE, 'data', 'unit_keyword_mappings.json')
if os.path.exists(kw_map_path):
    with open(kw_map_path, encoding='utf-8') as _f:
        kw_map = json.load(_f)
    existing_stems = {_keyword_stem(c['name']).lower() for c in card_data}
    injected = 0
    for canonical_name in kw_map.values():
        stem = _keyword_stem(canonical_name).lower()
        if stem not in existing_stems:
            defn = find_manual_definition(canonical_name)
            if defn:
                art = find_card_art(canonical_name)
                card_data.append({
                    'name': canonical_name,
                    'definition': defn,
                    'summary': find_manual_summary(canonical_name) or '',
                    'type': 'unit',
                    'imgs': [art] if art else [],
                    'credit': 'Manual',
                    'card_source': '',
                    'art_credit': find_card_art_credit(canonical_name) or '',
                    'units': '',
                })
                existing_stems.add(stem)
                injected += 1
    if injected:
        print(f"  {injected} new cards injected from overrides (no scraped data existed)")

# ── 4b. Tabletop Admiral keyword text, as a last resort ───────────────────────
# Rules text order: overrides/ > AMG rulebook > Legion Helper > Tabletop
# Admiral. TTA only fills keywords the rulebook and Legion Helper left empty,
# plus TTA keywords with no card yet. Runs BEFORE step 4 so hand-written
# overrides still win over it.
try:
    from src.render import apply_tta_keyword_text
    updated, missing = apply_tta_keyword_text(card_data)
    for disp, desc in missing:
        art = find_card_art(disp)
        card_data.append({
            'name': disp, 'definition': desc, 'summary': '',
            'type': 'unit', 'imgs': [art] if art else [],
            'credit': 'tabletopadmiral.com', 'card_source': '',
            'art_credit': find_card_art_credit(disp) or '', 'units': '',
        })
    print(f"  TTA keyword text: {updated} empty definitions filled, {len(missing)} new cards added")
    # Cards TTA just added never went through step 3: the rulebook still beats TTA.
    print(f"  Rulebook text for {fill_from_rulebook(card_data, RULEBOOK_CREDIT)} "
          f"of those Tabletop Admiral cards")
except Exception as e:
    print(f"  WARN: TTA keyword overlay failed: {e}")

# ── 4c. Legion Helper text (data/legion_helper.json, see legion_helper.py) ─────
# Beats Tabletop Admiral and empty definitions; the rulebook and hand-written
# overrides still win.
lh = apply_legion_helper_text(card_data, keep_credits={RULEBOOK_CREDIT, 'Manual'})
print(f"  Legion Helper text: {lh} definitions")

# ── 4. Apply manual overrides (always last — they win over everything) ────────
manual_count = apply_manual_overlays(card_data)
if manual_count:
    print(f"  {manual_count} definitions overridden from manual/ folder")

# ── 4b2. Art for cards added after step 2 ────────────────────────────────────
# Step 2 only sees the cached cards, so cards added later (override-only,
# Tabletop Admiral, new base cards) had no art even when the image was already
# in dist/images/ under the keyword's name or mapped to a unit card in
# data/keyword_images.json. Order: overrides/ > keyword-named file > mapped
# unit card > Wikimedia fallback photo.
from urllib.parse import unquote as _unquote
_files = {f.lower(): f for f in os.listdir(IMGDIR) if os.path.isfile(os.path.join(IMGDIR, f))}
_kci = {k.lower(): v for k, v in KEYWORD_CARD_IMAGES.items()}

def _art_on_disk(name):
    n = re.sub(r'\s*\[X\]', '', name.replace('➦', '').replace('[]', '')).strip()
    stems = [_keyword_stem(n)]
    stems.append(stems[0] + '_X')
    for s in stems:
        for ext in ('.webp', '.png', '.jpg'):
            if (s + ext).lower() in _files:
                return 'images/' + _files[(s + ext).lower()]
    key = _kw_lookup_key(n)
    mapped = _kci.get(key.lower()) or _kci.get(re.sub(r':.*$', '', key).strip().lower())
    if mapped and _unquote(mapped).lower() in _files:
        return 'images/' + _files[_unquote(mapped).lower()]
    for s in stems:
        if (s + '_1.jpg').lower() in _files:
            return 'images/' + _files[(s + '_1.jpg').lower()]
    return None

_wired = 0
for c in card_data:
    if c.get('imgs'):
        continue
    art = find_card_art(c['name']) or _art_on_disk(c['name'])
    if art:
        c['imgs'] = [art]
        _wired += 1
print(f"  {_wired} cards given art already on disk")

# ── 4b3. Which unit card each flashcard image shows ──────────────────────────
# Most keyword art is a unit card saved under the keyword's name
# ("Inspire.webp" is Leia Organa's card), so the file name can't say whose
# card it is. Match by content against the LegionHQ2 unit cards; failing that,
# trust data/keyword_images.json if the image still has unit-card proportions
# (older crops of the same card). c['iu'][i] is the unit image for c['imgs'][i]
# ('' = not a unit card); the Study screen uses it to show current points.
import hashlib as _hashlib
def _md5(path):
    with open(path, 'rb') as _f:
        return _hashlib.md5(_f.read()).hexdigest()
# The same unit list UNIT_DB is built from.
try:
    with open(os.path.join(CACHE_DIR, 'legionhq2_units.json'), encoding='utf-8') as _f:
        _unit_files = {u.get('i') for u in json.load(_f).values()
                       if isinstance(u, dict) and u.get('i')}
except Exception:
    _unit_files = set()
_unit_by_hash = {}
for _uf in _unit_files:
    _p = os.path.join(IMGDIR, _uf)
    if os.path.exists(_p):
        _unit_by_hash.setdefault(_md5(_p), _uf)
try:
    from PIL import Image as _Image
except ImportError:
    _Image = None

def _unit_card_shaped(path):
    if _Image is None:
        return False
    try:
        with _Image.open(path) as _im:
            w, h = _im.size
        return h and 1.35 <= w / h <= 1.5
    except Exception:
        return False

_iu_n = 0
for c in card_data:
    iu = []
    for im in c.get('imgs') or []:
        p = os.path.join(DIST_DIR, im)
        hit = ''
        if os.path.exists(p):
            base = os.path.basename(im)
            if base in _unit_files:
                hit = base
            else:
                hit = _unit_by_hash.get(_md5(p), '')
                if not hit:
                    mapped = _kci.get(_kw_lookup_key(c['name'].replace('[]', '')).lower())
                    mapped = _unquote(mapped) if mapped else ''
                    if mapped in _unit_files and _unit_card_shaped(p):
                        hit = mapped
        iu.append(hit)
    if any(iu):
        c['iu'] = iu
        _iu_n += 1
print(f"  {_iu_n} cards' art matched to a unit card (for points on the Study screen)")

# Cards injected above default to 'unit'; the rulebook knows which are weapon
# and upgrade keywords.
print(f"  {retype_from_rulebook(card_data)} cards retyped from the rulebook glossary")

# ── 4c. Current Tabletop Admiral card art ─────────────────────────────────────
# Must run BEFORE build_html: render.py decides whether a card has current art
# by checking for the file on disk.
try:
    res = download_tta_card_images(DIST_IMGDIR)
    for kind, (dl, sk, ms) in res.items():
        if dl or ms:
            print(f"  TTA {kind} art: {dl} downloaded, {sk} cached, {ms} unavailable")
except Exception as e:
    print(f"  WARN: TTA card art download failed: {e}")

# ── 5. Build HTML ─────────────────────────────────────────────────────────────
print("Building HTML...")
html = build_html(card_data)

# ── 5a. Upgrade card art for the print-by-unit sheet ──────────────────────────
# Runs after build_html() because that's what populates the upgrade cache.
try:
    dl, sk, fl = download_upgrade_card_images(DIST_IMGDIR)
    if dl or fl:
        print(f"  Upgrade art (LegionHQ2): {dl} downloaded, {sk} cached, {fl} failed")
    dl, sk, fl = download_command_card_images(DIST_IMGDIR)
    if dl or fl:
        print(f"  Command card art: {dl} downloaded, {sk} cached, {fl} failed")
except Exception as e:
    print(f"  WARN: upgrade art download failed: {e}")
out = os.path.join(DIST_DIR, "index.html")
os.makedirs(DIST_DIR, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

kb = os.path.getsize(out) // 1024
print(f"Done! dist/index.html ({kb} KB)")
