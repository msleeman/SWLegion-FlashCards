"""
Override and filename helper functions for SWLegion-FlashCards.
Handles card_art/ and manual/ file lookups.
"""
import os
import re

from src.config import (
    CARD_ART_DIR, MANUAL_DIR, DIST_IMGDIR,
)
from src.data_tables import KEYWORD_CARD_IMAGES, KEYWORD_CARDS  # noqa: F401 — re-exported for callers


def safe_filename(name, ext=".jpg"):
    """Return a safe filename stem + extension."""
    stem = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:60]
    return stem + ext


def _get_ext(url):
    """Return '.webp', '.jpg', or '.png' based on the URL."""
    if re.search(r"\.webp", url, re.I):
        return ".webp"
    if re.search(r"\.png", url, re.I):
        return ".png"
    return ".jpg"


def _kw_lookup_key(keyword_name):
    """Normalise a keyword display name to the lookup key used in KEYWORD_CARD_IMAGES."""
    k = re.sub(r"\s*\[\]$", "", keyword_name).strip()
    k = re.sub(r"\s+X$", "", k).strip()
    return k


def _keyword_stem(keyword_name):
    """Normalize a keyword name to a filename stem for card_art/ and manual/ lookups.
    Strips variable placeholders (X), bracket suffixes, and subtype qualifiers."""
    name = re.sub(r'\[.*?\]', '', keyword_name)
    name = re.sub(r'\s+X\b.*$', '', name, flags=re.I)
    name = re.sub(r'\s*[:/].*$', '', name)
    return safe_filename(name.strip(), ext="").rstrip("_")


# Keep old name as alias so any external callers aren't broken
_card_art_stem = _keyword_stem


def find_card_art(keyword_name):
    """Return 'images/<file>' (dist-relative) using the actual on-disk filename from
    OVERRIDES_DIR (case-insensitive match). Checks .png, .webp, .jpg in that order.
    Also copies the file into DIST_IMGDIR so dist/index.html can reference it."""
    import shutil as _shutil
    if not os.path.isdir(CARD_ART_DIR):
        return None
    stem_lower = _keyword_stem(keyword_name).lower()
    try:
        entries = os.listdir(CARD_ART_DIR)
    except OSError:
        return None
    for ext in ('.png', '.webp', '.jpg'):
        for entry in entries:
            name, e = os.path.splitext(entry)
            if name.lower() == stem_lower and e.lower() == ext:
                src = os.path.join(CARD_ART_DIR, entry)
                os.makedirs(DIST_IMGDIR, exist_ok=True)
                dst = os.path.join(DIST_IMGDIR, entry)
                try:
                    _shutil.copy2(src, dst)
                except OSError:
                    pass
                return f"images/{entry}"
    return None


def find_card_art_credit(keyword_name):
    """Return text content of card_art/<stem>.txt if present (up to 1000 chars), else None."""
    if not os.path.isdir(CARD_ART_DIR):
        return None
    stem_lower = _keyword_stem(keyword_name).lower()
    try:
        entries = os.listdir(CARD_ART_DIR)
    except OSError:
        return None
    for entry in entries:
        name, e = os.path.splitext(entry)
        if name.lower() == stem_lower and e.lower() == '.txt':
            try:
                with open(os.path.join(CARD_ART_DIR, entry), encoding='utf-8') as f:
                    return f.read(1000).strip()
            except OSError:
                return None
    return None


def _manual_read(keyword_name, suffix):
    """Return text from manual/<stem><suffix> (case-insensitive), else None."""
    if not os.path.isdir(MANUAL_DIR):
        return None
    stem_lower = _keyword_stem(keyword_name).lower()
    try:
        entries = os.listdir(MANUAL_DIR)
    except OSError:
        return None
    for entry in entries:
        if entry.lower() == stem_lower + suffix:
            try:
                with open(os.path.join(MANUAL_DIR, entry), encoding='utf-8') as f:
                    return f.read().strip()
            except OSError:
                return None
    return None


def find_manual_definition(keyword_name):
    """Return content of manual/<stem>.md if present, else None."""
    return _manual_read(keyword_name, '.md')


def find_manual_summary(keyword_name):
    """Return content of manual/<stem>.summary.md if present, else None."""
    return _manual_read(keyword_name, '.summary.md')


def has_manual_override(keyword_name):
    """True if any manual file exists for this keyword."""
    return find_manual_definition(keyword_name) is not None \
        or find_manual_summary(keyword_name) is not None


def apply_manual_overlays(card_data):
    """Apply manual/ definition and summary files. Manual files always win.
    Returns count of cards that had a definition overridden."""
    applied = 0
    for c in card_data:
        defn = find_manual_definition(c["name"])
        summ = find_manual_summary(c["name"])
        if defn:
            c["definition"] = defn
            c["credit"] = "Manual"
            applied += 1
        if summ:
            c["summary"] = summ
    return applied
