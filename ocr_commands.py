"""OCR the rules text off Command Card art.

Neither LegionHQ2 nor Tabletop Admiral has text for every command card (TTA
covers about 109 of 236), and no other reliable source was found -- but the
card images carry the rules, so we read them off the art.

Output goes to data/command_ocr.json, which IS committed, so a normal rebuild
never needs the OCR dependencies installed. Re-run this only when new command
cards appear:

    py -m pip install pillow rapidocr-onnxruntime
    py ocr_commands.py

Extraction relies on two properties that hold across the card frame:
  * rules text is horizontal (box wider than tall), while the artist credit is
    rotated 90 degrees up the edge (taller than wide)
  * rules text is sentence case, while the title, the "1 UNIT" orders banner and
    the commander name at the foot are all set in caps

Caveats worth knowing when reading the output:
  * inline rules ICONS (range, order tokens) are invisible to OCR and simply
    drop out, leaving a gap -- e.g. "an allied unit within  of Boba Fett"
  * on cards whose only text is flavour text, the flavour gets captured, since
    it is visually indistinguishable from rules text
"""
import json
import os
import re
import sys

CACHE = os.path.join('data', 'command_ocr.json')


def _horizontal(box):
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return (max(xs) - min(xs)) > (max(ys) - min(ys))


def _is_caps(txt):
    lower = sum(1 for c in txt if c.islower())
    upper = sum(1 for c in txt if c.isupper())
    return upper > lower


def extract_rules(res, img_h):
    """Pull the rules paragraph out of a card's OCR result.

    Position-based, not case-based. Rules text is sometimes typeset in italic
    small-caps (keyword callouts like "Eyes on the Prize: Low Profile and
    Nimble"), which OCR reads as ALL CAPS -- a "mostly lowercase" filter throws
    exactly those lines away.

    The furniture is identified structurally instead:
      * artist credit  -- rotated, so its box is taller than wide
      * orders banner  -- everything down to the FIRST sentence-case line is
        furniture (title, then the banner). Its depth varies far too much for a
        fixed cutoff (44% of the way down on one card, 74% on another) and it is
        not always "N UNITS": it can read "SHAAK TI & 2 UNITS" or "BO-KATAN
        KRYZE". Anchoring on the first body line also protects mid-paragraph
        caps callouts -- picking the LAST caps line instead silently deleted the
        opening paragraph of any card with an inline "DANGER SENSE 1 and
        INDOMITABLE." style line.
      * commander name -- trailing all-caps line(s) at the very foot. Rules text
        can also end in caps, so only strip ones that do not end in a full stop.
    """
    raw = [(box, txt.strip()) for box, txt, _ in (res or [])
           if _horizontal(box) and txt.strip()]
    if not raw:
        return '', []

    # Group boxes into visual rows before reading order is decided. An inline
    # rules icon splits a line into two boxes at slightly different heights;
    # sorting purely on y then interleaves them and scrambles the sentence.
    rows = []
    for box, txt in sorted(raw, key=lambda t: min(p[1] for p in t[0])):
        top = min(p[1] for p in box)
        bot = max(p[1] for p in box)
        placed = False
        for row in rows:
            if top < row['bot'] - (row['bot'] - row['top']) * 0.4:
                row['items'].append((min(p[0] for p in box), txt))
                row['bot'] = max(row['bot'], bot)
                placed = True
                break
        if not placed:
            rows.append({'top': top, 'bot': bot,
                         'items': [(min(p[0] for p in box), txt)]})
    lines = [(r['top'], None, ' '.join(t for _x, t in sorted(r['items'])))
             for r in rows]

    # Foot: commander / battle force name. "...LOWPROFILEANDNIMBLE." is rules
    # text that merely reads as caps, so keep anything ending in a full stop.
    while (len(lines) > 1 and _is_caps(lines[-1][2])
           and lines[-1][0] > img_h * 0.88 and not lines[-1][2].rstrip().endswith('.')):
        lines.pop()

    # Body starts at the first sentence-case line.
    start = next((i for i, (_y, _b, t) in enumerate(lines) if not _is_caps(t)), 0)

    body = lines[start:]
    kept = [t for _y, _b, t in body if len(t) > 3]
    # Lines OCR read as run-together caps lost their spacing; flag for review.
    suspect = [t for t in kept if _is_caps(t) and ' ' not in t and len(t) > 12]
    return re.sub(r'\s+', ' ', ' '.join(kept)).strip(), suspect


def main():
    from rapidocr_onnxruntime import RapidOCR

    with open(os.path.join('cache', 'commands.json'), encoding='utf-8') as f:
        cards = json.load(f)

    out = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding='utf-8') as f:
            out = json.load(f)

    todo = [c for c in cards
            if not (c.get('d') or '').strip()
            and c.get('i')
            and c['n'] not in out]
    print(f'{len(cards)} command cards, {len(todo)} need OCR '
          f'({len(out)} already cached)')

    from PIL import Image
    ocr = RapidOCR()
    vocab = build_vocab()
    print(f'repair vocabulary: {len(vocab)} words')
    imgdir = os.path.join('dist', 'images', 'commands')
    flagged = []
    for n, card in enumerate(todo, 1):
        path = os.path.join(imgdir, card['i'])
        if not os.path.exists(path):
            print(f'  [{n}/{len(todo)}] MISSING ART {card["n"]}')
            continue
        try:
            with Image.open(path) as im:
                img_h = im.size[1]
            res, _ = ocr(path)
        except Exception as e:
            print(f'  [{n}/{len(todo)}] FAILED {card["n"]}: {e}')
            continue
        text, suspect = extract_rules(res, img_h)
        text = repair(text, vocab)
        if text:
            out[card['n']] = text
        if suspect:
            flagged.append((card['n'], suspect))
        mark = '  <-- REVIEW' if suspect else ''
        print(f'  [{n}/{len(todo)}] {card["n"][:44]:44} {len(text):4d} chars{mark}')

    os.makedirs('data', exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f'\nwrote {CACHE}: {len(out)} cards')
    if flagged:
        print(f'\n{len(flagged)} card(s) have run-together caps needing manual review:')
        for name, sus in flagged:
            print(f'  {name}: {sus}')


# ─── Post-processing ─────────────────────────────────────────────────────────
# Two artifacts show up on the lower-resolution card scans:
#   1. spaces vanish  -> "alliedunitgains1ormoreAimtokens"
#   2. italic small-caps keywords mangle -> "ReLENTLEss", "PiERce", "MARKsMAN"
# Both are repaired with a vocabulary built from text we already trust: the
# Tabletop Admiral card descriptions, the keyword catalogue, and the OCR lines
# that came out correctly spaced. A domain-specific vocabulary beats a generic
# dictionary here because the corpus is full of terms like "Suppression" and
# "faceup" that a normal wordlist would miss or mis-split.

def build_vocab():
    words = {}

    def add(text):
        if isinstance(text, list):
            text = ' '.join(str(x) for x in text)
        for w in re.findall(r"[A-Za-z][A-Za-z'\-]+", text or ''):
            key = w.lower()
            # Prefer the capitalisation seen most often in trusted text.
            words.setdefault(key, {})
            words[key][w] = words[key].get(w, 0) + 1

    cmds_path = os.path.join('cache', 'commands.json')
    if os.path.exists(cmds_path):
        with open(cmds_path, encoding='utf-8') as f:
            for c in json.load(f):
                # Skip descriptions that are themselves OCR output, otherwise
                # earlier OCR errors get fed back in as trusted vocabulary.
                if not c.get('o'):
                    add(c.get('d'))
                add(c.get('n'))
                add(c.get('c'))

    kw_path = os.path.join('cache', 'tta_keywords.json')
    if os.path.exists(kw_path):
        with open(kw_path, encoding='utf-8') as f:
            for k in json.load(f).values():
                add(k.get('name'))
                add(k.get('description'))

    # The scraped keyword catalogue and the hand-written summaries widen the
    # vocabulary considerably -- without them ordinary rules words that happen
    # not to appear on a command card ("slots") are unknown, and the splitter
    # mangles "upgradeslotsspends" into "upgrades lots spends".
    cd_path = os.path.join('cache', 'card_data.json')
    if os.path.exists(cd_path):
        try:
            with open(cd_path, encoding='utf-8') as f:
                for c in json.load(f):
                    add(c.get('name'))
                    add(c.get('definition'))
        except Exception:
            pass
    ov = 'overrides'
    if os.path.isdir(ov):
        for fn in os.listdir(ov):
            if fn.endswith('.md'):
                try:
                    with open(os.path.join(ov, fn), encoding='utf-8') as f:
                        add(f.read())
                except Exception:
                    pass

    canon = {}
    for key, variants in words.items():
        best = max(variants.items(), key=lambda kv: (kv[1], kv[0][:1].isupper()))[0]
        canon[key] = (best, sum(variants.values()))
    return canon


def split_run_on(token, vocab):
    """Segment a run-together token using the vocabulary.

    Tolerates unrecognised stretches rather than giving up on the whole token:
    a single OCR typo like "OUTMANUEVER" would otherwise block the split of
    "PRECISE1andOUTMANUEVER" entirely. Unknown characters are carried through
    at a penalty and merged back into one piece.
    """
    low = token.lower()
    n = len(low)
    best = [None] * (n + 1)          # (score, pieces) where a piece may be ('?', ch)
    best[0] = (0, [])
    for i in range(1, n + 1):
        for j in range(max(0, i - 18), i):
            if best[j] is None:
                continue
            piece = low[j:i]
            if piece.isdigit():
                cand = (best[j][0] + len(piece) ** 2, best[j][1] + [piece])
            elif piece in vocab and (len(piece) > 2 or piece in ('a', 'i', 'x', 'of',
                                                                'or', 'to', 'it', 'is',
                                                                'in', 'an', 'at', 'be',
                                                                'no', 'on', 'up', 'do')):
                # Corpus frequency breaks ties that length alone gets wrong:
                # "upgrades|lots" outscores "upgrade|slots" on length, but
                # "slots" is common in this corpus and "lots" essentially absent.
                word, freq = vocab[piece]
                cand = (best[j][0] + len(piece) ** 2 + min(freq, 12),
                        best[j][1] + [word])
            elif i - j == 1:
                cand = (best[j][0] - 3, best[j][1] + [('?', token[j])])
            else:
                continue
            if best[i] is None or cand[0] > best[i][0]:
                best[i] = cand
    if not best[n]:
        return ''
    # Merge runs of unknown characters back into single words.
    merged, buf = [], []
    for p in best[n][1]:
        if isinstance(p, tuple):
            buf.append(p[1])
        else:
            if buf:
                merged.append(''.join(buf)); buf = []
            merged.append(p)
    if buf:
        merged.append(''.join(buf))
    return ' '.join(merged)


def _mangled_case(word):
    """True if capitalisation looks OCR-damaged (ReLENTLEss, MARKsMAN, PiERce).

    Detected as an uppercase letter appearing after a lowercase one. Ordinary
    words ("This", "at", "OUTMANEUVER") never match, so their original casing
    -- including sentence-initial capitals -- is left alone.
    """
    seen_lower = False
    for ch in word[1:]:
        if ch.islower():
            seen_lower = True
        elif ch.isupper() and seen_lower:
            return True
    return False


def repair(text, vocab):
    """Re-space run-together tokens and normalise mangled keyword casing."""
    PUNCT = '.,;:!?()"\u2019'

    def fix_word(core):
        if not core:
            return core
        low = core.lower()
        if low in vocab:
            # Only restyle words whose case is actually damaged; otherwise a
            # legitimate sentence-initial "This" would be lowercased to "this".
            return vocab[low][0] if _mangled_case(core) else core
        # Never re-split possessives/contractions -- "Kryze's" is one word.
        if "'" in core or len(core) <= 4 or not re.fullmatch(r'[A-Za-z0-9\-]+', core):
            return core
        split = split_run_on(core, vocab)
        if not split or ' ' not in split:
            return core
        pieces = split.split(' ')
        known = sum(len(p) for p in pieces if p.lower() in vocab or p.isdigit())
        # Only accept a confident segmentation. A single OCR typo such as
        # "OUTMANUEVER" otherwise gets shredded into "Out Man U ever", which is
        # worse than leaving the original token alone.
        tiny = [p for p in pieces
                if len(p) < 2 and not p.isdigit() and p.lower() not in ('a', 'i', 'x')]
        if (tiny or len(pieces) > 14
                or known < 0.65 * len(core.replace('-', ''))):
            return core
        return split

    out = []
    for token in re.split(r'(\s+)', text):
        if not token.strip():
            out.append(token)
            continue
        # Repair each punctuation-delimited chunk, so "resolved,youmay" is split
        # on the comma and both halves get looked at.
        out.append(''.join(
            part if part and part[0] in PUNCT else fix_word(part)
            for part in re.split(r'([' + re.escape(PUNCT) + r']+)', token)))
    joined = re.sub(r'\s+', ' ', ''.join(out)).strip()
    # OCR frequently drops the space after sentence punctuation ("Round,allied").
    return re.sub(r'([,.;:])(?=[A-Za-z])', r'\1 ', joined)


if __name__ == "__main__":
    sys.exit(main())
