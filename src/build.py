"""
Main orchestrator for SWLegion-FlashCards builder.

Usage:
    py -m src.build
    py src/build.py
"""
import os
import re
import json
import time

from src.config import (
    HERE, CACHE_DIR, IMGDIR, DIST_DIR, DIST_IMGDIR, DATA_DIR, OUT,
)
from src.data_tables import BUNDLED_KEYWORDS, KEYWORD_CARDS
from src.scrape import scrape_keywords, find_pdf, extract_keywords_from_pdf
from src.images import download_images
from src.overrides import apply_manual_overlays, find_card_art_credit
from src.units import inject_units
from src.render import build_html


def main():
    os.makedirs(IMGDIR, exist_ok=True)
    os.makedirs(DIST_IMGDIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    print("=" * 62)
    print("  SW Legion Flashcards Builder v4")
    print("  Keywords: Web Scrape (names+types) + PDF (definitions)")
    print("  Images:   legionhq2.com CDN + Wikimedia Commons")
    print("=" * 62)

    # ── Step 1a: Web scrape for full keyword list (names, types, definitions) ──
    print("\n[1/3] Scraping keywords from legion.takras.net...")
    keywords = []
    try:
        keywords = scrape_keywords()
        print(f"      {len(keywords)} keywords from web scraper")
    except Exception as e:
        print(f"      Scrape failed: {e}")

    if not keywords:
        print("      Falling back to bundled keyword definitions...")
        keywords = [{"name": k, "definition": v["definition"], "type": v["type"]}
                    for k, v in BUNDLED_KEYWORDS.items()]
        print(f"      {len(keywords)} bundled keywords")

    # ── Step 1b: Extract official definitions from PDF and overlay ────────────
    pdf_path = find_pdf()
    if pdf_path:
        print(f"\n      Overlaying PDF definitions from {os.path.basename(pdf_path)}...")
        try:
            pdf_dict = extract_keywords_from_pdf(pdf_path)
            if pdf_dict:
                def _norm(s):
                    return re.sub(r'[^a-z0-9]', '', s.lower())
                pdf_lookup = {_norm(k): v for k, v in pdf_dict.items()}
                overlaid = 0
                for kw in keywords:
                    key = _norm(kw["name"])
                    match = pdf_lookup.get(key)
                    if not match:
                        for pk, pv in pdf_lookup.items():
                            if pk.startswith(key) or key.startswith(pk):
                                match = pv
                                break
                    if match and match.get("definition"):
                        kw["definition"] = match["definition"]
                        kw["credit"] = "AMG Rulebook v2.6"
                        overlaid += 1
                print(f"      {overlaid}/{len(keywords)} definitions replaced with PDF versions")
            else:
                print("      PDF extraction returned nothing — keeping web definitions")
        except Exception as e:
            print(f"      PDF overlay failed: {e} — keeping web definitions")
    else:
        print("\n      No PDF found — using web definitions only")
        print("      (Place SWQ_Rulebook_2.6.0-1.pdf in documents/ to use official AMG text)")

    # Fill any empty definitions from bundled fallback
    bundled_lookup = {re.sub(r'[^a-z0-9]', '', k.lower()): v
                      for k, v in BUNDLED_KEYWORDS.items()}
    filled = 0
    for kw in keywords:
        if not kw.get("definition") or len(kw["definition"]) < 15:
            key = re.sub(r'[^a-z0-9]', '', kw["name"].lower())
            if key in bundled_lookup:
                kw["definition"] = bundled_lookup[key]["definition"]
                filled += 1
    if filled:
        print(f"      {filled} empty definitions filled from bundled fallback")

    # Apply manual overrides last — they always win
    manual_count = apply_manual_overlays(keywords)
    if manual_count:
        print(f"      {manual_count} definitions overridden from manual/ folder")

    print(f"\n      {len(keywords)} keywords ready")

    # Step 2: Download images
    print(f"\n[2/3] Downloading images from legionhq2.com CDN...")
    print("      (cached files are skipped automatically)\n")

    card_data = []
    failed = []

    for i, kw in enumerate(keywords, 1):
        name = kw["name"]
        print(f"  [{i:3d}/{len(keywords)}] {name[:42]:<42} ", end="", flush=True)
        img_paths, existed = download_images(name, IMGDIR, max_imgs=2)
        if img_paths:
            if existed:
                print(f"skip ({len(img_paths)} cached)")
            else:
                def _imgsize(p):
                    fname = os.path.basename(p)
                    fpath = os.path.join(IMGDIR, fname)
                    return os.path.getsize(fpath) // 1024 if os.path.exists(fpath) else 0
                total_kb = sum(_imgsize(p) for p in img_paths)
                print(f"OK  ({len(img_paths)} imgs, ~{total_kb} KB)")
            time.sleep(0.3)
        else:
            print("no image")
            failed.append(name)
            time.sleep(0.1)

        cards_mapping = KEYWORD_CARDS.get(name, [])
        card_source = f"See: {cards_mapping[0][0]}" if cards_mapping else ""

        card_data.append({
            "name":        name,
            "definition":  kw["definition"],
            "summary":     kw.get("summary", ""),
            "type":        kw["type"],
            "imgs":        img_paths,
            "credit":      kw.get("credit", "legion.takras.net"),
            "card_source": card_source,
            "art_credit":  find_card_art_credit(name) or "",
        })

    ok = len(keywords) - len(failed)
    print()
    if failed:
        short = ', '.join(failed[:5]) + ('...' if len(failed) > 5 else '')
        print(f"  No image: {short}")
    print(f"  {ok}/{len(keywords)} keywords have images")

    # Inject 'units' field
    inject_units(card_data)

    # Save cache so rebuild_html_only.py picks up fresh data
    cache_path = os.path.join(CACHE_DIR, 'card_data.json')
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(card_data, f, ensure_ascii=False, indent=2)
    print(f"\n      Cached {len(card_data)} cards to cache/card_data.json")

    # Copy cached images → dist/images/
    import shutil as _shutil
    img_copied = 0
    for fname in os.listdir(IMGDIR):
        src = os.path.join(IMGDIR, fname)
        dst = os.path.join(DIST_IMGDIR, fname)
        if os.path.isfile(src):
            _shutil.copy2(src, dst)
            img_copied += 1
    print(f"      Copied {img_copied} images from cache/images/ -> dist/images/")

    # Step 3: Build HTML
    print(f"\n[3/3] Building dist/index.html...")
    html = build_html(card_data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUT) // 1024
    print(f"      dist/index.html  ({kb} KB)")
    print(f"      dist/images/     ({img_copied} images)")
    print()
    print("  Open dist/index.html in your browser.")
    print("  Images are in the dist/images/ folder.")
    print("=" * 62)


if __name__ == "__main__":
    main()
