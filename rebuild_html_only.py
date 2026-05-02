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

from src.config import DIST_IMGDIR, CACHE_DIR, DIST_DIR
from src.data_tables import KEYWORD_CARD_IMAGES
from src.overrides import (
    find_card_art, find_card_art_credit,
    _kw_lookup_key, _get_ext, safe_filename,
    apply_manual_overlays,
)
from src.scrape import find_pdf, extract_keywords_from_pdf
from src.images import download_images
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
                    overlaid += 1
            print(f"  {overlaid}/{len(card_data)} definitions replaced with PDF versions")
        else:
            print("  PDF extraction returned nothing — keeping cached definitions")
    except Exception as e:
        print(f"  PDF overlay failed: {e} — keeping cached definitions")
else:
    print("PDF not found — keeping cached definitions")
    print("  (place SWQ_Rulebook_2.6.0-1.pdf in the project root or documents/ folder)")

# ── 4. Apply manual overrides (always last — they win over everything) ────────
manual_count = apply_manual_overlays(card_data)
if manual_count:
    print(f"  {manual_count} definitions overridden from manual/ folder")

# ── 5. Build HTML ─────────────────────────────────────────────────────────────
print("Building HTML...")
html = build_html(card_data)
out = os.path.join(DIST_DIR, "index.html")
os.makedirs(DIST_DIR, exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

kb = os.path.getsize(out) // 1024
print(f"Done! dist/index.html ({kb} KB)")
