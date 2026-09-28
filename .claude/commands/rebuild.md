# SWLegion FlashCards — Rebuild

Run this after any change to `template/` or `overrides/` to regenerate `dist/index.html`
with an updated version number and build timestamp. Always rebuild before committing.

```bash
py rebuild_html_only.py
```

---

## Project reference

**Read `README.md` first** — it is the authoritative reference for:
- Quick-start commands (`py -m src.build`, `py rebuild_html_only.py`, `py refresh_definitions.py`)
- Full folder structure and what each file does
- The golden rule: never edit `dist/` directly — always edit `template/` or `overrides/`
- Override system: stem rules, file types, survival guarantee
- Image priority chain
- Versioning (`git describe --tags --always --dirty`)
- Multi-PC workflow

Key things to remember from the README:

| Need to… | Do this |
|-----------|---------|
| Change JS/CSS/HTML | Edit `template/`, then `/rebuild` |
| Override a keyword definition | Create `overrides/<Stem>.md` |
| Override a summary | Create `overrides/<Stem>.summary.md` |
| Override card art | Drop `overrides/<Stem>.webp\|png\|jpg` |
| Full rescrape | `py -m src.build` |
| Fix one bad definition | `py refresh_definitions.py` |
| Tag a release | `git tag v5.x.y && git push origin v5.x.y` |

Python executable on this machine: `C:\Program Files\Python314\python.exe` (use `py`).

---

## Keyword normalization (not in README)

This section covers implementation details Claude needs when working on the keyword/list system.

### LegionHQ2 URL format
```
https://legionhq2.com/list/{faction}/{points}:{subfaction}:{codes}
```
Old format omits subfaction: `{points}:{codes}`. `parseLegionHQUrl()` in `app.js`
handles both by splitting on `:` and checking part count.

Unit codes in `{codes}` are comma-separated. Each unit code starts with a count digit
(`1at0pqdydv` = 1× unit "at" with upgrades). 2-char codes with no count prefix are
command/battle cards and are skipped.

### Parametric keyword encoding

LegionHQ2 stores parametric keywords differently from the card database:

| LegionHQ2 stores | Canonical card name |
|-----------------|---------------------|
| `"Compel Corps"` | `"Compel"` |
| `"Weak Point 1: Rear"` | `"Weak Point X"` |
| `"Teamwork Han Solo"` | `"Teamwork"` |
| `"Entourage Imperial Death Troopers"` | `"Entourage"` |
| `"Immune: Pierce"` | `"Immune: Pierce"` (already canonical — preserved) |

**`kwNormalize(kw)`** (module-level in `app.js`) fixes this at parse time:
1. Strip trailing `\d+.*` → `"Weak Point 1: Rear"` → `"Weak Point"`
2. For colon-free keywords only, progressively truncate words from the right until
   a prefix matches a known card name → `"Compel Corps"` → `"Compel"`

**`normKw(name)`** (module-level in `app.js`) normalises a card name for DB lookup:
strips `[]`, trailing ` X`, and everything after `:`, then lowercases.
e.g. `"Compel: Rank/Unit Type[]"` → `"compel"`

**`printListKeywords()`** applies the same progressive truncation as a fallback so
already-saved lists with old-format keywords still resolve to the right card definition.

### Override stem examples

`_keyword_stem()` in `src/overrides.py` strips `X`, `[]`, colon subtypes, and
converts spaces to underscores:

| Keyword name | File to create |
|-------------|----------------|
| `Weak Point X` | `overrides/Weak_Point.md` |
| `Compel: Rank/Unit Type[]` | `overrides/Compel.md` |
| `Immune: Pierce` | `overrides/Immune.md` |
| `Master of the Force X` | `overrides/Master_of_the_Force.md` |

### Checking for missing keyword definitions

After any change that expands keyword coverage (e.g. adding upgrade weapons, new unit
data), run this to find keywords in the UNIT_DB/UPGRADE_DB that have no flashcard:

```python
import re, json

with open('dist/index.html', encoding='utf-8') as f:
    html = f.read()

# Extract CARDS normset
idx = html.find('const CARDS =')
start = html.index('[', idx)
depth = 0
for i, c in enumerate(html[start:], start):
    if c=='[': depth+=1
    elif c==']':
        depth-=1
        if depth==0: end=i+1; break
cards = json.loads(html[start:end])

def normKw(n):
    n = re.sub(r'\[\]','',n); n = re.sub(r'\s+X$','',n)
    n = re.sub(r':\s*.+$','',n); return n.strip().lower()

card_norms = {normKw(c['name']) for c in cards}

# Collect all unit+upgrade keywords and check against CARDS
with open('cache/legionhq2_units.json') as f: units = json.load(f)
with open('cache/legionhq2_upgrades.json') as f: upgrades = json.load(f)

missing = set()
for db in [units, upgrades]:
    for entry in db.values():
        for kw in entry.get('k', []):
            base = re.sub(r'\s+\d+.*$', '', str(kw)).strip()
            base = re.sub(r'\s*:\s*.+$', '', base).strip()
            if base.lower() not in card_norms:
                missing.add(base)

print(sorted(missing))
```

Any keyword in `missing` needs either a scraped definition or an `overrides/<Stem>.md`
file. **Never write definitions from memory.**

### Rules text sources (highest priority first)

1. `overrides/<Stem>.md` — hand-written, always wins
2. The AMG rulebook PDF in `documents/` (newest in `src/config.RULEBOOK_PDFS`,
   currently `DOC56_SWQ_Rulebook.pdf`)
3. Legion Helper — `data/legion_helper.json`
4. Tabletop Admiral keyword descriptions — only where nothing above has text

### Legion Helper (legion.takras.net)

Legion Helper's keyword pages are rendered in the browser: the HTML they serve
has **no rules text**, so a plain `requests` fetch (the old scraper in
`src/scrape.py`) gets nothing for keywords, and only a one-line meta
description for concept pages. `legion_helper.py` loads each page in headless
Chromium, one page at a time with a pause, and saves the rendered text to
`data/legion_helper.json` (committed). The builds read that file; they never
visit the site. The page list is the site's own A–Z keyword index.

```bash
py legion_helper.py            # read pages not cached yet
py legion_helper.py --all      # re-read everything (after a rules update)
py legion_helper.py spur aim   # re-read specific slugs
```

Re-run it when Legion Helper's "rules reference updated" date on its home page
changes. If a keyword has no text anywhere, ask the user for the correct rule text.

Also ensure `data/unit_keyword_mappings.json` has an entry for each missing keyword
(key = lowercase, value = canonical card name). Without it the injection system won't
pick up the override file.
