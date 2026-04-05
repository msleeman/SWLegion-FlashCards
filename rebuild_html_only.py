#!/usr/bin/env python3
"""Rebuild swlegion_flashcards.html from cached card data (no scraping)."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Import the build script
import build_swlegion_v3 as bld

# Load cached card data
cache = os.path.join(HERE, "cards_cache.json")
if not os.path.exists(cache):
    print("ERROR: cards_cache.json not found. Run build_swlegion_v3.py first.")
    sys.exit(1)

with open(cache, "r", encoding="utf-8") as f:
    card_data = json.load(f)

print(f"Loaded {len(card_data)} cards from cache")

# Update image paths using new KEYWORD_CARD_IMAGES mappings
# Re-apply image assignments (the images may already be cached)
IMGDIR = os.path.join(HERE, "images")
for c in card_data:
    lookup_key = bld._kw_lookup_key(c["name"])
    card_filename = bld.KEYWORD_CARD_IMAGES.get(lookup_key)
    if card_filename:
        ext = bld._get_ext(card_filename)
        fname = bld.safe_filename(c["name"], ext=ext)
        filepath = os.path.join(IMGDIR, fname)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            c["imgs"] = [f"images/{fname}"]
        else:
            # Try to download it
            img_paths, _ = bld.download_images(c["name"], IMGDIR, max_imgs=1)
            if img_paths:
                c["imgs"] = img_paths
            # else keep existing

print("Building HTML...")
html = bld.build_html(card_data)
out = os.path.join(HERE, "swlegion_flashcards.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)

kb = os.path.getsize(out) // 1024
print(f"Done! swlegion_flashcards.html ({kb} KB)")
