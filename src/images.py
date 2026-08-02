"""
Image download functions for SWLegion-FlashCards.
Handles CDN unit card images and Wikimedia Commons fallback.
"""
import os
import re
import time

import requests

from src.config import LEGIONHQ_CDN, WIKI_COMMONS_API, HEADERS
from src.data_tables import KEYWORD_CARD_IMAGES, UNIT_IMAGE_MAP  # noqa: F401
from src.overrides import _kw_lookup_key, safe_filename, _get_ext, find_card_art


def search_images_wiki(keyword_name, max_imgs=2):
    """Fallback: search Wikimedia Commons for images."""
    clean = re.sub(r"\s*[\(\[].*?[\)\]]", "", keyword_name).strip()
    clean = re.sub(r"\s+X$", "", clean).strip()
    search_terms = [f"Star Wars Legion {clean}", f"Star Wars {clean}"]
    found_urls, seen_urls = [], set()
    for term in search_terms:
        if len(found_urls) >= max_imgs:
            break
        try:
            r = requests.get(WIKI_COMMONS_API, headers=HEADERS, timeout=10, params={
                "action": "query", "generator": "search",
                "gsrnamespace": "6", "gsrsearch": term, "gsrlimit": "8",
                "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": "1200",
                "format": "json",
            })
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for page in sorted(pages.values(), key=lambda p: p.get("index", 999)):
                info = (page.get("imageinfo") or [{}])[0]
                url  = info.get("thumburl") or info.get("url", "")
                mime = info.get("mime", "")
                if (url and "image" in mime
                        and re.search(r"\.(jpe?g|png)$", url, re.I)
                        and url not in seen_urls):
                    found_urls.append(url)
                    seen_urls.add(url)
                if len(found_urls) >= max_imgs:
                    break
        except Exception:
            pass
        time.sleep(0.3)
    return found_urls


def download_images(keyword_name, imgdir, max_imgs=2):
    """Download images for a keyword.

    Priority:
    1. Use unit card image from legionhq2.com CloudFront CDN if available.
    2. Fall back to Wikimedia Commons search.

    Returns (list_of_relative_paths, already_cached: bool).
    """
    # ── card_art/ folder takes priority over everything ───────────────────────
    art = find_card_art(keyword_name)
    if art:
        return [art], True

    lookup_key = _kw_lookup_key(keyword_name)
    card_filename = KEYWORD_CARD_IMAGES.get(lookup_key)

    # ── Try CloudFront unit card first ────────────────────────────────────────
    if card_filename:
        card_url = LEGIONHQ_CDN + card_filename
        ext      = _get_ext(card_url)
        fname    = safe_filename(keyword_name, ext=ext)
        filepath = os.path.join(imgdir, fname)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return [f"images/{fname}"], True
        try:
            r = requests.get(card_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
            print(f"(card)", end=" ")
            return [f"images/{fname}"], False
        except Exception as exc:
            print(f"(card-fail:{exc})", end=" ")
            # Fall through to Wikimedia

    # ── Wikimedia Commons fallback ────────────────────────────────────────────
    base     = safe_filename(keyword_name, ext="").rstrip("_")
    existing, needed = [], []
    for i in range(1, max_imgs + 1):
        found = None
        for ext in (".png", ".webp", ".jpg"):
            candidate = f"{base}_{i}{ext}"
            fp = os.path.join(imgdir, candidate)
            if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                found = candidate
                break
        if found:
            existing.append(f"images/{found}")
        else:
            fname = f"{base}_{i}.jpg"
            needed.append((i, fname, os.path.join(imgdir, fname)))
    if not needed:
        return existing, True
    urls = search_images_wiki(keyword_name, max_imgs=len(needed))
    saved = list(existing)
    for (i, fname, filepath), url in zip(needed, urls):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
            saved.append(f"images/{fname}")
        except Exception:
            pass
    return saved, False


def download_upgrade_card_images(imgdir):
    """Download upgrade card art for every upgrade in the LegionHQ2 upgrade cache.

    Upgrade art lives at a different CDN path than unit art (/upgradeCards/ vs
    /unitCards/) and is saved under images/upgrades/ rather than alongside unit
    art, because some names collide -- e.g. "Shaak Ti" is both a unit card and a
    personnel upgrade card.

    Returns (downloaded, skipped, failed).
    """
    from src.config import CACHE_DIR

    cache_path = os.path.join(CACHE_DIR, "legionhq2_upgrades.json")
    if not os.path.exists(cache_path):
        return 0, 0, 0
    import json
    with open(cache_path, encoding="utf-8") as f:
        upgrade_db = json.load(f)

    outdir = os.path.join(imgdir, "upgrades")
    os.makedirs(outdir, exist_ok=True)

    cdn = LEGIONHQ_CDN.replace("/unitCards/", "/upgradeCards/")
    downloaded = skipped = failed = 0

    for u in upgrade_db.values():
        img = u.get("i")
        if not img:
            continue
        dest = os.path.join(outdir, img)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            skipped += 1
            continue
        try:
            r = requests.get(cdn + img, headers=HEADERS, timeout=20)
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            downloaded += 1
        except Exception:
            failed += 1

    return downloaded, skipped, failed


def download_tta_upgrade_images(imgdir):
    """Download Tabletop Admiral's own upgrade card art, keyed by public_id.

    Complements download_upgrade_card_images(): LegionHQ2 has broader coverage
    (433 of 434) but has to be matched by name, which is ambiguous for the 13
    upgrade names shared by several cards -- that is how a Bo-Katan Darksaber
    ended up rendered on Moff Gideon. TTA art is addressed by public_id, so it
    is always the right card; where TTA has none we fall back to LegionHQ2.

    Returns (downloaded, skipped, failed).
    """
    from src.config import CACHE_DIR

    cache_path = os.path.join(CACHE_DIR, "tta_upgrades.json")
    if not os.path.exists(cache_path):
        return 0, 0, 0
    import json
    with open(cache_path, encoding="utf-8") as f:
        db = json.load(f)

    raw_path = os.path.join(CACHE_DIR, "tta_upgrades_raw.json")
    if os.path.exists(raw_path):
        with open(raw_path, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        try:
            r = requests.get("https://tabletopadmiral.com/api/upgrades",
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            raw = r.json()
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
        except Exception:
            return 0, 0, 0

    url_by_hex = {}
    for u in raw:
        pid = u.get("public_id")
        if pid is None:
            continue
        art = u.get("image_url") or u.get("cloudinary_image_url")
        if art:
            url_by_hex[format(int(pid), "x")] = art

    outdir = os.path.join(imgdir, "upgrades", "tta")
    os.makedirs(outdir, exist_ok=True)

    downloaded = skipped = failed = 0
    for hex_id, entry in db.items():
        fname = entry.get("a")
        url = url_by_hex.get(hex_id)
        if not fname or not url:
            continue
        dest = os.path.join(outdir, fname)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            skipped += 1
            continue
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            downloaded += 1
        except Exception:
            failed += 1

    return downloaded, skipped, failed
