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
from src.scrape import find_pdf, extract_keywords_from_pdf
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
            pdf_lookup = {_norm(k): v for k, v in pdf_dict.items()}
            overlaid = 0
            for c in card_data:
                key = _norm(c["name"])
                match = pdf_lookup.get(key)
                if not match:
                    for pk, pv in pdf_lookup.items():
                        if pk.startswith(key) or key.startswith(pk):
                            match = pv
                            break
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

# ── 4b. Overlay Tabletop Admiral keyword text (authoritative over the scrape) ──
# TTA carries current 2.6 wording; the older legion.takras.net scrape had at
# least one outright wrong rule (Ruthless described removing suppression when
# the card actually lets the unit suffer a wound for a free action). Runs BEFORE
# step 4 so hand-written overrides still win over it.
try:
    from src.render import fetch_tta_keywords
    tta_kws = fetch_tta_keywords()
    if tta_kws:
        def _tk(n):
            n = re.sub(r'\[\]', '', n)
            n = re.sub(r'\s+X$', '', n)
            n = re.sub(r':\s*.+$', '', n)
            return n.strip().lower()

        by_norm = {}
        for k in tta_kws.values():
            desc = (k.get('description') or '').strip()
            if desc:
                by_norm.setdefault(_tk(k.get('name', '')), (k.get('name', ''), desc))

        updated = 0
        for c in card_data:
            hit = by_norm.get(_tk(c['name']))
            if hit and hit[1] != c.get('definition'):
                c['definition'] = hit[1]
                c['credit'] = 'tabletopadmiral.com'
                updated += 1

        existing = {_tk(c['name']) for c in card_data}
        added = 0
        for norm_name, (disp, desc) in by_norm.items():
            if norm_name in existing:
                continue
            art = find_card_art(disp)
            card_data.append({
                'name': disp, 'definition': desc, 'summary': '',
                'type': 'unit', 'imgs': [art] if art else [],
                'credit': 'tabletopadmiral.com', 'card_source': '',
                'art_credit': find_card_art_credit(disp) or '', 'units': '',
            })
            existing.add(norm_name)
            added += 1
        print(f"  TTA keyword text: {updated} definitions refreshed, {added} new cards added")
except Exception as e:
    print(f"  WARN: TTA keyword overlay failed: {e}")

# ── 4. Apply manual overrides (always last — they win over everything) ────────
manual_count = apply_manual_overlays(card_data)
if manual_count:
    print(f"  {manual_count} definitions overridden from manual/ folder")

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
