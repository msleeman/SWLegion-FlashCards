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


def _tta_card_art(rows, kind, outdir, path_tpl):
    """Fetch current Tabletop Admiral card art for units or upgrades.

    Addressed by the record's `id` and `image_version` on the CDN the live site
    actually serves from (d26oqf9i6fvic.cloudfront.net). This is NOT the same as
    the API's `image_url` field, which still points at old Cloudinary scans that
    carry the pre-revamp layout with the point cost and card type along the
    bottom edge.

    Returns (downloaded, skipped, missing).
    """
    os.makedirs(outdir, exist_ok=True)
    downloaded = skipped = missing = 0
    for rec in rows:
        rid = rec.get('id')
        if rid is None:
            continue
        fname = f"{rid}.webp"
        dest = os.path.join(outdir, fname)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            skipped += 1
            continue
        url = path_tpl.format(id=rid, ver=rec.get('image_version') or 1)
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code != 200 or len(r.content) < 1000:
                missing += 1
                continue
            with open(dest, 'wb') as f:
                f.write(r.content)
            downloaded += 1
        except Exception:
            missing += 1
    return downloaded, skipped, missing


TTA_CDN = 'https://d26oqf9i6fvic.cloudfront.net/'


def download_tta_card_images(imgdir):
    """Download current TTA art for both upgrades and units.

    Runs before the HTML build so render.py can tell which cards actually have
    current art simply by looking on disk.
    """
    out = {}
    try:
        ups = requests.get('https://tabletopadmiral.com/api/upgrades',
                           headers=HEADERS, timeout=30).json()
        out['upgrades'] = _tta_card_art(
            ups, 'upgrade', os.path.join(imgdir, 'upgrades', 'tta'),
            TTA_CDN + 'upgrades-new/trimmed/{id}.webp?version={ver}')
    except Exception as e:
        print(f"  WARN: TTA upgrade art failed: {e}")
    try:
        units = requests.get('https://tabletopadmiral.com/api/units',
                             headers=HEADERS, timeout=30).json()
        out['units'] = _tta_card_art(
            units, 'unit', os.path.join(imgdir, 'units', 'tta'),
            TTA_CDN + 'new-unit-cards/front/420/{id}.webp?version={ver}')
    except Exception as e:
        print(f"  WARN: TTA unit art failed: {e}")
    return out


def download_command_card_images(imgdir):
    """Download Command Card art from the LegionHQ CDN into images/commands/.

    Command cards matter more than most art here: Tabletop Admiral only has
    rules text for about half of them, so for the rest the card image IS the
    rules reference.

    Returns (downloaded, skipped, failed).
    """
    from src.config import CACHE_DIR

    cache_path = os.path.join(CACHE_DIR, "commands.json")
    if not os.path.exists(cache_path):
        return 0, 0, 0
    import json
    with open(cache_path, encoding="utf-8") as f:
        cards = json.load(f)

    outdir = os.path.join(imgdir, "commands")
    os.makedirs(outdir, exist_ok=True)
    cdn = LEGIONHQ_CDN.replace("/unitCards/", "/commandCards/")

    downloaded = skipped = failed = 0
    for c in cards:
        img = c.get("i")
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
