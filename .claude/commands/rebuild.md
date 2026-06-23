# SWLegion FlashCards — Rebuild

Run `py rebuild_html_only.py` to regenerate `dist/index.html` from cached data.
This updates the version number and build timestamp. Always do this after editing
`template/app.js`, `template/index.html`, or `template/app.css` — and before committing.

```bash
py rebuild_html_only.py
```

---

## Project structure

| Path | Purpose |
|------|---------|
| `template/app.js` | Main JS source — **edit this, never `dist/`** |
| `template/index.html` | HTML template with `{{VERSION}}` and `{{BUILD_DATE}}` placeholders |
| `template/app.css` | Stylesheet |
| `src/render.py` | Build engine — `get_version()` runs `git describe`, `build_html()` injects placeholders |
| `rebuild_html_only.py` | Fast rebuild from cache (no scraping) — use this for JS/template changes |
| `dist/index.html` | Built output — **never edit directly** |
| `overrides/<Stem>.md` | Manual keyword definition overrides — win over everything including PDF |
| `overrides/<Stem>.webp/png/jpg` | Manual keyword card art |
| `legionhq2_units.json` | Cached unit DB from LegionHQ2 (root of project) |
| `cards_cache.json` | Cached keyword card data (root of project) |
| `cache/card_data.json` | Processed card data used by rebuild |

Full rebuild (re-scrapes everything): `py -m src.build`

Python executable: `C:\Program Files\Python314\python.exe` — use the `py` command.

---

## Keyword system

### Card definitions
- Scraped from `legion.takras.net`, cached in `cards_cache.json`
- PDF rulebook overlays the cache (`pdfplumber` required — `pip install pdfplumber`)
- **Manual overrides always win**: create `overrides/<Stem>.md` for a definition,
  `overrides/<Stem>.summary.md` for a short summary
- Stem is computed by `_keyword_stem()` in `src/overrides.py`:
  strips `X`, `[]`, colon subtypes, converts spaces to `_`
  e.g. `"Weak Point X"` → `"Weak_Point"` → file is `overrides/Weak_Point.md`

### Unit DB (LegionHQ2)
- Built from LegionHQ2's JS bundle, cached in `legionhq2_units.json`
- Injected into `dist/index.html` at build time as `const UNIT_DB = {...}`
- Each unit entry: `{ n, t, f, r, k[], i }` (name, title, faction, rank, keywords, image)

### LegionHQ2 URL format
```
https://legionhq2.com/list/{faction}/{points}:{subfaction}:{codes}
```
- Old format omits subfaction: `{points}:{codes}`
- `parseLegionHQUrl()` in `app.js` handles both by splitting on `:` and checking for 2 vs 3 parts
- `codes` is comma-separated — unit codes start with a count digit (e.g. `1at0pqdydv`)
- Command/battle card codes are 2 chars with no count prefix and get skipped

### Parametric keyword normalization
LegionHQ2 encodes parametric keywords differently from the card DB:

| LegionHQ2 stores | Card DB name |
|-----------------|--------------|
| `"Compel Corps"` | `"Compel"` |
| `"Weak Point 1: Rear"` | `"Weak Point X"` |
| `"Teamwork Han Solo"` | `"Teamwork"` |
| `"Entourage Imperial Death Troopers"` | `"Entourage"` |
| `"Immune: Pierce"` | `"Immune: Pierce"` (already canonical) |

**`kwNormalize(kw)`** in `app.js` fixes this:
1. Strips trailing `\d+.*` (handles `"Weak Point 1: Rear"` → `"Weak Point"`)
2. For colon-free keywords, progressively truncates words from the right until
   a prefix matches a known card name (handles `"Compel Corps"` → `"Compel"`)

**`normKw(name)`** (module-level in `app.js`) normalises a card name for lookup:
strips `[]`, trailing ` X`, and everything after `:` → lowercase.
e.g. `"Compel: Rank/Unit Type[]"` → `"compel"`

**`printListKeywords()`** uses the same progressive truncation as a fallback so
already-saved lists with old-format keywords still find their card definitions.

---

## Git / deploy workflow

1. Edit `template/app.js` or `template/index.html`
2. Run `/rebuild` (this command) — confirms build succeeds and updates `dist/`
3. `git add template/app.js dist/index.html` (and any new `overrides/` files)
4. `git commit` with a clear message
5. `git push` — remote is `git@github.com:msleeman/SWLegion-FlashCards.git`

Test locally by opening `dist/index.html` directly in a browser — no server needed.
