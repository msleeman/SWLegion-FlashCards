"""
Web scraping and PDF extraction for SWLegion-FlashCards.
"""
import os
import re
import time

import requests

from src.config import HERE, BASE, HEADERS
from src.data_tables import KEYWORD_PAGES, BUNDLED_KEYWORDS


# ── Locate the PDF ────────────────────────────────────────────────────────────
def find_pdf():
    candidates = [
        os.path.join(HERE, "SWQ_Rulebook_2.6.0-1.pdf"),
        os.path.join(HERE, "SWQ_Rulebook_2_6_0-1.pdf"),
        os.path.join(HERE, "documents", "SWQ_Rulebook_2.6.0-1.pdf"),
        os.path.join(HERE, "documents", "SWQ_Rulebook_2_6_0-1.pdf"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# ── PDF keyword extraction ─────────────────────────────────────────────────────
def extract_keywords_from_pdf(pdf_path):
    try:
        import pdfplumber
    except ImportError:
        print("  ERROR: pdfplumber not installed. Run: py -m pip install pdfplumber")
        return {}

    print(f"  Reading: {os.path.basename(pdf_path)}")
    keywords = {}

    NOISE = re.compile(r'^(\d{1,3}|RULEBOOK|LEGION|LEGIONRULEBOOK|[•*—©])$', re.IGNORECASE)

    def clean(s):
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s or '')
        return re.sub(r'\s+', ' ', s).strip()

    def fix_spaced(name):
        tokens = name.split()
        singles = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        if singles > len(tokens) * 0.5:
            name = ''.join(tokens)
        return name

    def title_kw(n):
        return ' '.join(
            w if w in ('X', 'LOS') or w.isdigit() else w.capitalize()
            for w in n.split()
        )

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

    current_name = current_type = None
    current_def = []

    def flush():
        nonlocal current_name, current_type, current_def
        if not current_name: return
        defn = clean(' '.join(current_def))
        if len(defn) > 20:
            name = title_kw(fix_spaced(current_name))
            keywords[name] = {'name': name, 'type': current_type or 'unit', 'definition': defn}
        current_name = current_type = None
        current_def = []

    with pdfplumber.open(pdf_path) as pdf:
        for pg_idx in range(44, min(61, len(pdf.pages))):
            page = pdf.pages[pg_idx]
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            if not words: continue
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
                    line = clean(line)
                    if not line or NOISE.match(line): continue
                    m = KW_INLINE.match(line)
                    if m:
                        flush()
                        current_name = m.group(1).strip()
                        current_type = get_type(m.group(2))
                        current_def = []
                        pending = None
                        continue
                    if KW_TYPE.match(line):
                        if pending:
                            flush()
                            current_name = pending
                            current_type = get_type(line)
                            current_def = []
                        pending = None
                        continue
                    if KW_NAME.match(line) and len(line) < 65 and line.upper() not in SKIP:
                        pending = line
                        continue
                    if current_name:
                        current_def.append(line)
                    pending = None
    flush()

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
