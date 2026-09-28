"""OCR the rules text off Upgrade Card art.

Neither LegionHQ2 nor Tabletop Admiral carries upgrade card text, and both
drop keyword values that only appear in a card's prose -- Sonic Charge
Saboteur's "other Ranged weapons ... gain Assault 1" is stored as a bare
"Assault" / "Assault X". The card images carry both, so we read them off the
art, the same way ocr_commands.py does for command cards.

Output goes to data/upgrade_ocr.json, which IS committed, so a normal rebuild
never needs the OCR dependencies installed. Re-run this only when new upgrade
cards appear (already-read cards are skipped; pass --all to redo them, or
--tidy to re-apply the text clean-up to the cached output only):

    py -m pip install pillow rapidocr-onnxruntime
    py ocr_upgrades.py

Each entry is keyed "<name>|<cost>" (names repeat across card variants) and
holds:
  t  rules text        -- restriction lines ("SCOUT TROOPERS ONLY.") and the
                          card title are dropped
  w  weapon bar text   -- weapon name and keyword line, e.g. "SONIC CHARGE
                          BLAST. IMPACT 4. SUPPRESSIVE"
  m  miniatures added  -- from "Add N ... miniature(s)", when present

Art: the LegionHQ2 scans (725px wide) are preferred because they read far more
cleanly; Tabletop Admiral's 420px art is upscaled 2x as a fallback. Inline
rules ICONS (exhaust, range) are invisible to OCR and drop out, leaving a gap.
"""
import json
import os
import re
import sys

from ocr_commands import build_vocab, repair, _horizontal, _is_caps

CACHE = os.path.join('data', 'upgrade_ocr.json')
LHQ_DIR = os.path.join('dist', 'images', 'upgrades')
TTA_DIR = os.path.join('dist', 'images', 'upgrades', 'tta')


def _rows(res):
    """Group OCR boxes into visual rows, left-to-right within a row."""
    raw = [(box, txt.strip()) for box, txt, _ in (res or [])
           if _horizontal(box) and txt.strip()]
    rows = []
    for box, txt in sorted(raw, key=lambda t: min(p[1] for p in t[0])):
        top = min(p[1] for p in box)
        bot = max(p[1] for p in box)
        for row in rows:
            if top < row['bot'] - (row['bot'] - row['top']) * 0.4:
                row['items'].append((min(p[0] for p in box), txt))
                row['bot'] = max(row['bot'], bot)
                break
        else:
            rows.append({'top': top, 'bot': bot,
                         'items': [(min(p[0] for p in box), txt)]})
    return [(r['top'], ' '.join(t for _x, t in sorted(r['items']))) for r in rows]


def extract(res, img_h):
    """Split an upgrade card's OCR into (rules text, weapon bar text)."""
    rows = [(y, t) for y, t in _rows(res)
            if y > img_h * 0.10                 # cost, top right
            and y < img_h * 0.87                # card title (and version) at the foot
            and not re.fullmatch(r'v\d+(\.\d+)*', t.strip())]
    # Restriction lines lead the text box: "SCOUT TROOPERS ONLY.",
    # "NON-DROID TROOPER ONLY." (sometimes wrapped over two rows).
    while rows and re.search(r'ONLY\.?\s*$', rows[0][1].replace(' ', '').upper()) \
            and _is_caps(rows[0][1]):
        rows.pop(0)
    # Weapon bar: from the first caps row in the lower part of the card that is
    # followed by another caps row (name, then keyword line) or ends the card.
    split = len(rows)
    for i, (y, t) in enumerate(rows):
        if y < img_h * 0.70 or not _is_caps(t):
            continue
        rest = rows[i + 1:]
        if all(_is_caps(rt) for _ry, rt in rest):
            split = i
            break
    rules = ' '.join(t for _y, t in rows[:split])
    weapon = ' '.join(t for _y, t in rows[split:])
    # The range icon reads as junk ("必-1"); drop non-Latin runs.
    weapon = re.sub(r'[^\x20-\x7E]+\S*', ' ', weapon)
    return re.sub(r'\s+', ' ', rules).strip(), re.sub(r'\s+', ' ', weapon).strip()


def tidy(text):
    """Put back what OCR reliably loses on upgrade cards.

    The exhaust icon in "you may <exhaust> this card" is invisible to OCR and
    leaves "you may this card" -- restore it as [TAP]. Small digits also run
    into the next word ("choose 1of the drawn Order tokens").
    """
    text = re.sub(r'\bmay\s+this card\b', 'may [TAP] this card', text)
    text = re.sub(r'\b(\d)(of|or|and)\b', r'\1 \2', text)
    return re.sub(r'\s+([.,;:])', r'\1', text)


def minis_added(rules):
    """N from "Add N ... miniature(s)" -- the card art sometimes misspells it
    ("Add 1 Electrostaff Pirate minature")."""
    m = re.search(r'Add\s*(\d+)\s*.*?\bmini?a?tures?\b', rules, re.I)
    return int(m.group(1)) if m else None


def _cards():
    """Every upgrade as (key, name, image path, needs upscale)."""
    lhq = json.load(open(os.path.join('cache', 'legionhq2_upgrades.json'), encoding='utf-8'))
    tta = json.load(open(os.path.join('cache', 'tta_upgrades.json'), encoding='utf-8'))
    out = {}
    for u in lhq.values():
        p = os.path.join(LHQ_DIR, u.get('i') or '')
        if u.get('i') and os.path.exists(p):
            out.setdefault(f"{u['n']}|{u.get('c', 0)}", (u['n'], p, False))
    for u in tta.values():
        key = f"{u['n']}|{u.get('c', 0)}"
        p = os.path.join(TTA_DIR, u.get('a') or '')
        if key not in out and u.get('a') and os.path.exists(p):
            out[key] = (u['n'], p, True)
    return out


def main():
    import numpy as np
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR

    redo = '--all' in sys.argv
    out = {}
    if os.path.exists(CACHE) and not redo:
        with open(CACHE, encoding='utf-8') as f:
            out = json.load(f)
    if '--tidy' in sys.argv:
        # Re-apply tidy() to what is already cached, without re-reading art.
        for e in out.values():
            e['t'] = tidy(e['t'])
            if minis_added(e['t']):
                e['m'] = minis_added(e['t'])
        _save(out)
        print(f'tidied {len(out)} cached cards')
        return

    cards = _cards()
    todo = [(k, v) for k, v in sorted(cards.items()) if k not in out]
    print(f'{len(cards)} upgrade cards, {len(todo)} need OCR ({len(out)} already cached)')

    ocr = RapidOCR()
    vocab = build_vocab()
    for n, (key, (name, path, upscale)) in enumerate(todo, 1):
        try:
            with Image.open(path) as im:
                im = im.convert('RGB')
                if upscale:
                    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
                img_h = im.height
                res, _ = ocr(np.array(im))
        except Exception as e:
            print(f'  [{n}/{len(todo)}] FAILED {key}: {e}')
            continue
        rules, weapon = extract(res, img_h)
        rules = tidy(repair(rules, vocab))
        entry = {'t': rules}
        if weapon:
            entry['w'] = repair(weapon, vocab)
        if minis_added(rules):
            entry['m'] = minis_added(rules)
        out[key] = entry
        print(f'  [{n}/{len(todo)}] {key[:48]:48} {len(rules):4d} chars'
              f'{"  (tta)" if upscale else ""}')
        if n % 25 == 0:
            _save(out)
    _save(out)
    print(f'\nwrote {CACHE}: {len(out)} cards')


def _save(out):
    os.makedirs('data', exist_ok=True)
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)


if __name__ == '__main__':
    sys.exit(main())
