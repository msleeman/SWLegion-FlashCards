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
