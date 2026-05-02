"""
Web scraping and PDF extraction for SWLegion-FlashCards.
"""
import os
import re
import time

import requests

from src.config import HERE, BASE, HEADERS, RULEBOOK_PDFS
from src.data_tables import KEYWORD_PAGES, BUNDLED_KEYWORDS


# ── Locate the PDF ────────────────────────────────────────────────────────────
def find_pdf():
    """Return the path to the first rulebook PDF found on disk.

    Searches each filename in RULEBOOK_PDFS (newest first) inside documents/
    then the project root. Update RULEBOOK_PDFS in src/config.py when a new
    rulebook drops — no other code needs to change.
    """
    search_dirs = [os.path.join(HERE, "documents"), HERE]
    for filename in RULEBOOK_PDFS:
        for d in search_dirs:
            p = os.path.join(d, filename)
            if os.path.exists(p):
                return p
    return None


# ── PDF keyword extraction ─────────────────────────────────────────────────────
#
# AMG rulebooks since the 2026-05-01 update use a font-size-based layout:
#   • Section headers (UNIT KEYWORDS / WEAPON KEYWORDS / UPGRADE AND COMMAND
#     CARD KEYWORDS) are size ~18 ALL CAPS, may span multiple lines.
#   • Keyword names are size ~14 ALL CAPS, may span multiple lines
#     (e.g. "ADVANCED TARGETING: UNIT" / "TYPE X").
#   • Body text is size ~9.5.
#   • Inline game-icon glyphs render at ~size 15 — those are skipped.
#
# Older rulebooks (≤ 2.6.0-1) used parenthetical "(UNIT KEYWORD)" markers.
# We auto-detect which layout the PDF uses and dispatch to the right parser.

_HEADER_SIZE = 17.0          # section header font size lower bound
_NAME_SIZE   = 13.5          # keyword name font size lower bound
_ICON_SIZE   = 14.5          # inline icon glyphs are around 15.0
_BODY_SIZE_MAX = 13.0        # body text is well below the name/header threshold

_SECTION_TYPES = {
    "UNIT KEYWORDS":                      "unit",
    "WEAPON KEYWORDS":                    "weapon",
    "UPGRADE AND COMMAND CARD KEYWORDS":  "upgrade",
    "UPGRADE KEYWORDS":                   "upgrade",
    "COMMAND CARD KEYWORDS":              "upgrade",
}


def _clean_text(s):
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s or '')
    return re.sub(r'\s+', ' ', s).strip()


def _title_kw(n):
    """Title-case a keyword name preserving 'X', 'LOS', digits, and the
    capitalization of each hyphen-separated subword (so 'ANTI-MATERIEL X'
    becomes 'Anti-Materiel X', matching the web-scraped convention)."""
    def cap_part(p):
        if p in ('X', 'LOS') or p.isdigit():
            return p
        # Title-case each hyphen-separated piece.
        return '-'.join(seg.capitalize() if seg else seg for seg in p.split('-'))
    return ' '.join(cap_part(w) for w in n.split())


def _looks_like_kw_name(text):
    """ALL-CAPS, mostly letters, plausible keyword-name length."""
    if not text or len(text) < 3 or len(text) > 70:
        return False
    if text != text.upper():
        return False
    # Must contain at least one letter (skip pure-glyph lines)
    if not re.search(r'[A-Z]', text):
        return False
    return True


def _extract_keywords_new_format(pdf):
    """Parser for AMG rulebooks using the font-size-based layout (2026-05-01+)."""
    keywords = {}

    # Locate the keyword glossary by looking for the size-20 "KEYWORD GLOSSARY"
    # header that opens the section (not a cross-reference from the appendix).
    # The header is rendered with spaced glyphs ("K E Y WOR D / GL OSS A R Y"),
    # so collapse all whitespace before matching.
    start_page = None
    for i in range(20, len(pdf.pages)):
        page_words = pdf.pages[i].extract_words(extra_attrs=['size']) or []
        big_text = ''.join(
            w['text'] for w in page_words if (w.get('size') or 0) >= 19.5
        ).upper()
        big_text = re.sub(r'\s+', '', big_text)
        if 'KEYWORDGLOSSARY' in big_text:
            start_page = i
            break
    if start_page is None:
        return keywords

    current_section = "unit"
    current_name_parts = []
    current_def_parts = []
    in_name = False  # True while accumulating consecutive name-sized lines

    def flush():
        nonlocal current_name_parts, current_def_parts, in_name
        name = _clean_text(' '.join(current_name_parts))
        defn = _clean_text(' '.join(current_def_parts))
        if name and len(defn) > 20:
            display = _title_kw(name)
            keywords[display] = {
                "name": display,
                "type": current_section,
                "definition": defn,
            }
        current_name_parts = []
        current_def_parts = []
        in_name = False

    pending_section = []  # accumulator for multi-line size-18 section headers

    for pidx in range(start_page, len(pdf.pages)):
        page = pdf.pages[pidx]
        words = page.extract_words(x_tolerance=2, y_tolerance=3, extra_attrs=['size'])
        if not words:
            continue

        # Some pages place columns at x≈45/302, others at x≈68/324 — both
        # have content that crosses any fixed midpoint. Split at 0.49 × width
        # (≈ 300pt for a 612pt page) without a gap, and exclude the narrow
        # margins where the rotated "LEGION RULEBOOK" spine text lives.
        mid = page.width * 0.49
        columns = [
            [w for w in words if 30 < w['x0'] < mid],
            [w for w in words if mid <= w['x0'] < page.width - 30],
        ]

        # Detect end of glossary: no name-sized words in either column.
        has_kw_content = any(
            (w.get('size') or 0) >= _NAME_SIZE for col in columns for w in col
        )
        # Allow one bridge page (e.g. mid-section transition) before bailing.
        if not has_kw_content and pidx > start_page + 1:
            break

        for col_words in columns:
            # Group words into lines by rounded top coordinate.
            rows = {}
            for w in col_words:
                y = round(w['top'] / 4) * 4
                rows.setdefault(y, []).append(w)

            for y in sorted(rows):
                line_words = sorted(rows[y], key=lambda w: w['x0'])
                line_text = _clean_text(' '.join(w['text'] for w in line_words))
                if not line_text:
                    continue
                max_size = max((w.get('size') or 0) for w in line_words)

                # Section header (size ~18, may span multiple lines)
                if max_size >= _HEADER_SIZE:
                    pending_section.append(line_text.upper())
                    continue
                # Resolve any pending section header now that we've left header-size lines.
                if pending_section:
                    joined = ' '.join(pending_section).strip()
                    pending_section = []
                    for marker, kind in _SECTION_TYPES.items():
                        if marker in joined:
                            flush()
                            current_section = kind
                            break
                    # Drop "KEYWORD GLOSSARY" and similar non-section headers silently.

                # Keyword name (size ~14, ALL CAPS)
                if max_size >= _NAME_SIZE and _looks_like_kw_name(line_text):
                    if in_name:
                        # Continuation of the same multi-line name
                        current_name_parts.append(line_text)
                    else:
                        flush()
                        current_name_parts = [line_text]
                        in_name = True
                    continue

                # Inline icon glyphs (≈ size 15, single chars). Treat as body filler.
                if max_size >= _ICON_SIZE and len(line_text) <= 6:
                    in_name = False
                    continue

                # Body text — definition continuation.
                if current_name_parts:
                    current_def_parts.append(line_text)
                    in_name = False

    flush()
    return keywords


def _extract_keywords_legacy_format(pdf):
    """Parser for AMG rulebooks ≤ 2.6.0-1 (parenthetical type markers)."""
    keywords = {}

    NOISE = re.compile(r'^(\d{1,3}|RULEBOOK|LEGION|LEGIONRULEBOOK|[•*—©])$', re.IGNORECASE)

    def fix_spaced(name):
        tokens = name.split()
        singles = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        if singles > len(tokens) * 0.5:
            name = ''.join(tokens)
        return name

    def get_type(s):
        su = s.upper()
        if 'WEAPON' in su: return 'weapon'
        if 'COMMAND' in su or 'UPGRADE' in su: return 'upgrade'
        return 'unit'

    KW_INLINE = re.compile(
        r'^(.{3,60}?)\s*\(([^)]*(?:KEYWORD|KEYWO\s*RD)[^)]*)\)\s*$',
        re.IGNORECASE)
    KW_TYPE = re.compile(
        r'^\(([^)]*(?:KEYWORD|KEYWO\s*RD)[^)]*)\)$',
        re.IGNORECASE)
    KW_NAME = re.compile(r'^[A-Z][A-Z0-9\s\-\':\/\.]{2,59}$')
    SKIP = {'WEAPON KEYWORDS', 'UNIT KEYWORDS', 'UPGRADE AND', 'COMMAND CARD',
            'KEYWORDS', 'KEYWORD GLOSSARY', 'LINE OF SIGHT', 'SILHOUETTE TEMPLATES',
            'RULEBOOK', 'LEGION', 'LEGIONRULEBOOK'}

    state = {'name': None, 'type': None, 'def': []}

    def flush():
        if not state['name']:
            return
        defn = _clean_text(' '.join(state['def']))
        if len(defn) > 20:
            name = _title_kw(fix_spaced(state['name']))
            keywords[name] = {'name': name, 'type': state['type'] or 'unit', 'definition': defn}
        state['name'] = None
        state['type'] = None
        state['def'] = []

    for pg_idx in range(44, min(61, len(pdf.pages))):
        page = pdf.pages[pg_idx]
        words = page.extract_words(x_tolerance=2, y_tolerance=3)
        if not words:
            continue
        mid = page.width * 0.50

        def col_lines(wlist):
            if not wlist: return []
            rows = {}
            for w in wlist:
                y = round(w['top'] / 4) * 4
                rows.setdefault(y, []).append(w)
            return [' '.join(w['text'] for w in sorted(rows[y], key=lambda w: w['x0']))
                    for y in sorted(rows)]

        for col_words in ([w for w in words if w['x0'] < mid],
                          [w for w in words if w['x0'] >= mid]):
            pending = None
            for line in col_lines(col_words):
                line = _clean_text(line)
                if not line or NOISE.match(line):
                    continue
                m = KW_INLINE.match(line)
                if m:
                    flush()
                    state['name'] = m.group(1).strip()
                    state['type'] = get_type(m.group(2))
                    state['def'] = []
                    pending = None
                    continue
                if KW_TYPE.match(line):
                    if pending:
                        flush()
                        state['name'] = pending
                        state['type'] = get_type(line)
                        state['def'] = []
                    pending = None
                    continue
                if KW_NAME.match(line) and len(line) < 65 and line.upper() not in SKIP:
                    pending = line
                    continue
                if state['name']:
                    state['def'].append(line)
                pending = None
    flush()
    return keywords


def _detect_pdf_format(pdf):
    """Return 'new' or 'legacy' based on glossary layout.

    The new format uses size-based typography; the legacy format uses
    parenthetical "(UNIT KEYWORD)" markers right after the keyword name.
    """
    sample_pages = min(len(pdf.pages), 65)
    for i in range(20, sample_pages):
        text = pdf.pages[i].extract_text() or ""
        if "KEYWORD GLOSSARY" not in text.upper():
            continue
        # Look at the next few pages for parenthetical markers.
        for j in range(i, min(i + 5, len(pdf.pages))):
            t = (pdf.pages[j].extract_text() or "")
            if re.search(r'\((?:UNIT|WEAPON|UPGRADE|COMMAND CARD)\s+KEYWORD\)', t, re.I):
                return 'legacy'
        return 'new'
    return 'new'


def extract_keywords_from_pdf(pdf_path):
    try:
        import pdfplumber
    except ImportError:
        print("  ERROR: pdfplumber not installed. Run: py -m pip install pdfplumber")
        return {}

    print(f"  Reading: {os.path.basename(pdf_path)}")
    with pdfplumber.open(pdf_path) as pdf:
        fmt = _detect_pdf_format(pdf)
        print(f"  Detected layout: {fmt}")
        if fmt == 'legacy':
            keywords = _extract_keywords_legacy_format(pdf)
        else:
            keywords = _extract_keywords_new_format(pdf)

    print(f"  Extracted {len(keywords)} keywords from PDF")
    return keywords


# ── Scrape keywords from legion.takras.net ────────────────────────────────────
def scrape_keyword_page(slug, display_name, session):
    """Fetch a single keyword page and extract type + definition."""
    display_name = display_name.replace("[]", "").strip()
    url = f"{BASE}/{slug}/"
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  FETCH ERROR {slug}: {e}")
        return None

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        _ICON_TITLE_MAP = {
            "hit":          "[HIT]",
            "hit surge":    "[SURGE: HIT]",
            "hit critical": "[CRIT]",
            "block":        "[BLOCK]",
            "block surge":  "[SURGE: BLOCK]",
            "range melee":    "[MELEE]",
            "range half":     "[RANGE 1/2]",
            "range 1":        "[RANGE 1]",
            "range 2":        "[RANGE 2]",
            "range 3":        "[RANGE 3]",
            "range 4":        "[RANGE 4]",
            "range 5":        "[RANGE 5]",
            "range infinite": "[RANGE ∞]",
            "rank commander": "[COMMANDER]",
            "rank operative": "[OPERATIVE]",
            "rank corps":     "[CORPS]",
            "rank specialist":"[SPECIALIST]",
            "rank support":   "[SUPPORT]",
            "rank heavy":     "[HEAVY]",
            "courage": "[COURAGE]",
        }
        _TOKEN_NAME_MAP = {
            "aim":        "[AIM TOKEN]",
            "dodge":      "[DODGE TOKEN]",
            "surge":      "[SURGE TOKEN]",
            "standby":    "[STANDBY TOKEN]",
            "observation":"[OBSERVATION TOKEN]",
            "smoke":      "[SMOKE TOKEN]",
            "damage":     "[DAMAGE TOKEN]",
            "order":      "[ORDER TOKEN]",
            "commander":  "[COMMANDER TOKEN]",
            "ion":        "[ION TOKEN]",
            "poison":     "[POISON TOKEN]",
            "immobilize": "[IMMOBILIZE TOKEN]",
            "shield":     "[SHIELD TOKEN]",
            "charge":     "[CHARGE TOKEN]",
            "wheel-mode": "[WHEEL MODE TOKEN]",
            "incognito":  "[INCOGNITO TOKEN]",
            "graffiti":   "[GRAFFITI TOKEN]",
            "poi":        "[POI TOKEN]",
            "asset":      "[ASSET TOKEN]",
            "advantage":  "[ADVANTAGE TOKEN]",
        }

        if soup.head:
            soup.head.decompose()

        for img_tag in soup.find_all("img"):
            src   = img_tag.get("src", "")
            title = (img_tag.get("title") or "").strip().lower()
            alt   = (img_tag.get("alt")   or "").strip().lower()

            replacement = None

            if title and title in _ICON_TITLE_MAP:
                replacement = _ICON_TITLE_MAP[title]

            if replacement is None and "/images/tokens/" in src:
                stem = re.sub(r"\.[^.]+$", "", src.rsplit("/", 1)[-1]).lower()
                replacement = _TOKEN_NAME_MAP.get(stem, f"[{stem.upper()} TOKEN]")

            if replacement is None and "/images/black/" in src:
                stem = re.sub(r"\.[^.]+$", "", src.rsplit("/", 1)[-1]).lower()
                if stem in _ICON_TITLE_MAP:
                    replacement = _ICON_TITLE_MAP[stem]
                elif stem.startswith("range-"):
                    rng = stem[len("range-"):]
                    replacement = f"[RANGE {rng.upper()}]"
                elif stem.startswith("rank-"):
                    rank = stem[len("rank-"):].upper()
                    replacement = f"[{rank}]"
                else:
                    label = (alt or title or stem).upper()
                    replacement = f"[{label}]"

            if replacement:
                img_tag.replace_with(replacement)

        text = soup.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"  PARSE ERROR {slug}: {e}")
        return None

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    ktype = "concept"
    type_line_idx = -1
    for i, line in enumerate(lines):
        if re.search(r'\bUnit\s+Keyword\b', line, re.I):
            ktype = "unit";    type_line_idx = i; break
        if re.search(r'\bWeapon\s+Keyword\b', line, re.I):
            ktype = "weapon";  type_line_idx = i; break
        if re.search(r'\bUpgrade\s+Keyword\b', line, re.I):
            ktype = "upgrade"; type_line_idx = i; break
        if re.search(r'\bCommand\s+Card\s+Keyword\b', line, re.I):
            ktype = "upgrade"; type_line_idx = i; break

    STOP = {"Related keywords", "Related Keywords", "Get sharable image",
            "Share keyword", "This website uses cookies"}

    def is_stop(line):
        return any(line.startswith(s) for s in STOP)

    def is_noise(line):
        return line in ("Back to Legion Helper", "I am One with the Force",
                        "I'm a Star Wars Muggle", display_name, "×")

    def is_icon_token(line):
        return bool(re.match(r"^\[.+\]$", line))

    start_idx = type_line_idx + 1 if type_line_idx >= 0 else 0
    definition_parts = []
    for line in lines[start_idx:]:
        if is_stop(line):
            break
        if is_noise(line):
            continue
        if not line.startswith("http") and (is_icon_token(line) or len(line) > 3):
            definition_parts.append(line)

    if not definition_parts:
        found_name = False
        for line in lines:
            if is_stop(line):
                break
            if is_noise(line):
                found_name = True
                continue
            if found_name and not line.startswith("http") and (is_icon_token(line) or len(line) > 3):
                definition_parts.append(line)
                if len(definition_parts) >= 12:
                    break

    definition = " ".join(definition_parts).strip()
    definition = re.sub(r"\s+", " ", definition)
    if len(definition) > 2000:
        definition = definition[:1997] + "..."

    if len(definition) < 15:
        print(f"  WARN: short definition for {display_name!r}")

    return {"name": display_name, "definition": definition, "type": ktype}


def scrape_keywords():
    print("  Fetching keyword definitions from legion.takras.net...")
    try:
        from bs4 import BeautifulSoup  # noqa: confirm available
    except ImportError:
        print("  ERROR: beautifulsoup4 not installed.")
        print("  Run: py -m pip install beautifulsoup4")
        raise

    session  = requests.Session()
    keywords = []
    total    = len(KEYWORD_PAGES)

    for i, (slug, name) in enumerate(KEYWORD_PAGES, 1):
        print(f"  [{i:3d}/{total}] {name[:50]}", end=" ... ", flush=True)
        kw = scrape_keyword_page(slug, name, session)
        if kw and kw["definition"]:
            print(f"OK ({kw['type']})")
            keywords.append(kw)
        else:
            print("SKIP (no definition)")
        time.sleep(0.25)

    print(f"\n  Scraped {len(keywords)} / {total} keywords")
    return keywords
