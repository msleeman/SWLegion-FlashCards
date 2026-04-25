# SW Legion Flashcards — v5 Architecture Proposal

*Status: Draft for review · Owner: msleeman*

This is a refactor, not a rewrite. The web app behavior stays the same. What changes is how the source is organized, how the build works, and how overrides are layered.

---

## 1. Guiding principles

1. **One source of truth per concern.** No file should exist in two places.
2. **Three layers, in order: scrape → cache → overrides.** The build mixes them in that order. Overrides always win.
3. **HTML / CSS / JS live in their own files.** Python orchestrates; it does not embed front-end code in raw strings.
4. **Generated artifacts live in `dist/`.** Source code never sits next to its own output.
5. **GitHub is the source of truth for the running app.** Friends only need to pull and open.
6. **Versioning is automatic and conflict-free** across PCs.
7. **Every override is a plain file** named after the keyword stem.

---

## 2. New directory structure

```
SWLegion-FlashCards/
│
├── README.md
├── VERSION                         ← derived from `git describe`; not committed alone
├── pyproject.toml                  ← modern Python packaging
├── .gitignore                      ← ignores cache/, __pycache__, etc.
│
├── documents/                      ← architecture, PRD, this proposal, transcripts
│
├── data/                           ← canonical input data (committed)
│   ├── unit_db.json                ← extracted from LegionHQ2 (moved out of parent dir)
│   ├── keyword_aliases.json        ← spelling fixes: scrape-name → canonical-name
│   ├── unit_keyword_mappings.json  ← unit-keyword string → canonical keyword name
│   └── rulebook.pdf                ← SWQ rulebook (renamed for stability)
│
├── overrides/                      ← USER-CURATED LAYER (committed; the only place to edit)
│   ├── README.md                   ← explains naming convention
│   ├── <stem>.summary.md           ← one-line summary
│   ├── <stem>.md                   ← full rules text
│   ├── <stem>.<ext>                ← image (png/webp/jpg)
│   ├── <stem>.credit.txt           ← image credit line
│   └── ...all flat in one folder, keyed by stem
│
├── cache/                          ← GITIGNORED. Regenerated. Never edit.
│   ├── scraped_keywords.json       ← raw web scrape
│   ├── card_data.json              ← merged data (was cards_cache.json)
│   └── images/                     ← downloaded from CDN/Wikimedia
│
├── src/                            ← Python build modules (small, focused)
│   ├── __init__.py
│   ├── build.py                    ← entry point: `python -m src.build`
│   ├── scrape.py                   ← legion.takras.net + PDF
│   ├── images.py                   ← CDN + Wikimedia download
│   ├── overrides.py                ← apply_overrides() — single source of truth
│   ├── units.py                    ← inject 'units' field
│   ├── render.py                   ← stamp template files into dist/
│   ├── version.py                  ← `git describe`-based versioning
│   └── refresh.py                  ← targeted definition re-scrape
│
├── template/                       ← FRONT-END SOURCE (edit here, not in dist!)
│   ├── index.html                  ← HTML with placeholders: {{CARD_JSON}}, {{VERSION}}
│   ├── style.css                   ← all CSS
│   └── app.js                      ← all JavaScript
│
├── dist/                           ← BUILD OUTPUT (committed for distribution)
│   ├── index.html                  ← was swlegion_flashcards.html — open this
│   └── images/                     ← final image set, copied from cache + overrides
│
└── tests/                          ← pytest tests (existing)
```

### What's gone, what's renamed

| Old | New | Why |
|---|---|---|
| `build_swlegion_v4.py` (4,153 lines) | `src/*.py` (split modules) | Editable, testable, no version in name |
| `swlegion_flashcards.html` | `dist/index.html` | Clearly an output, conventional name |
| `cards_cache.json` | `cache/card_data.json` (gitignored) | Cache, not source. Stops polluting diffs. |
| `images/` (407 files, committed) | `cache/images/` (gitignored) + `dist/images/` (committed) | Clear "cache vs distribution" |
| `card_art/` (166 files) | `overrides/` (flat) | One override folder for everything |
| `manual/` | `overrides/` (flat) | Same. One place. |
| `version.txt` + `build_number.txt` | `VERSION` (from `git describe`) | One source. No conflicts. |
| `legionhq2_units.json` | `cache/legionhq2_units.json` | It's a cache. |
| `../unit_db.json` | `data/unit_db.json` | Inside the repo, not in parent dir |
| `HTML_TEMPLATE` raw string | `template/index.html` | Real front-end file |

---

## 3. The override system (simplified)

**One folder. Flat. Filename = stem + role suffix.**

```
overrides/
├── backup.summary.md          ← summary line
├── backup.md                  ← full rules
├── backup.png                 ← image
├── backup.credit.txt          ← image credit
├── pierce.summary.md
├── pierce.webp
├── coordinate.md
└── ...
```

**Resolution order** (in `src/overrides.py`):
1. Image: `<stem>.png` → `<stem>.webp` → `<stem>.jpg` → fall back to cache → fall back to CDN search
2. Summary: `<stem>.summary.md` → fall back to first sentence of rules
3. Rules: `<stem>.md` → fall back to PDF → fall back to scrape → fall back to bundled
4. Image credit: `<stem>.credit.txt` → fall back to default

**`<stem>` rules** (unchanged from v4):
- `Backup[]` → `backup`
- `Pierce X` → `pierce`
- `Coordinate: Type/Name[]` → `coordinate`

### Why one flat folder beats two folders + subdirs

- **One mental model**: "all overrides for keyword X start with `x.`"
- **Easy to grep**: `ls overrides/backup.*` shows everything for that keyword
- **No "which folder?" confusion** when adding a new override type later
- **Sortable** by stem in any file browser

---

## 4. Versioning that works across PCs

**Use `git describe --tags --always --dirty`.**

```python
# src/version.py
import subprocess
def get_version():
    try:
        v = subprocess.check_output(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            cwd=REPO_ROOT, text=True
        ).strip()
        return v
    except Exception:
        return 'dev'
```

Output examples:
- `v5.0.0` (on a tag)
- `v5.0.0-3-gabc1234` (3 commits past tag, current SHA)
- `v5.0.0-3-gabc1234-dirty` (uncommitted changes)

**Benefits:**
- Zero merge conflicts (no version file)
- Always honest — tells you exactly what build is running
- Tags are explicit releases (`git tag v5.0.0` then push)
- Friends see the same version no matter which PC built the artifact

**Migration from `version.txt`/`build_number.txt`:** delete both, tag the v5 release as `v5.0.0`, never look back.

---

## 5. The new build flow

```
                        ┌────────────────────────────┐
                        │     EXTERNAL SOURCES       │
                        │ legion.takras.net  CDN  PDF│
                        └─────────────┬──────────────┘
                                      │
                     ┌────────────────▼──────────────────┐
                     │   src/scrape.py  +  src/images.py │
                     │   (idempotent; respects cache)    │
                     └────────────────┬──────────────────┘
                                      │
                                      ▼
                     ┌─────────────────────────────────┐
                     │   cache/scraped_keywords.json   │
                     │   cache/images/*.webp           │
                     │   (gitignored, regenerable)     │
                     └────────────────┬────────────────┘
                                      │
                                      ▼
              ┌───────────────────────────────────────────────┐
              │   src/overrides.py  +  src/units.py           │
              │   merge: cache + overrides/ + data/unit_db    │
              │   → produces final card_data list             │
              └───────────────────────┬───────────────────────┘
                                      │
                                      ▼
                     ┌────────────────────────────────┐
                     │   src/render.py                │
                     │   reads template/index.html,   │
                     │   style.css, app.js;           │
                     │   stamps placeholders;         │
                     │   copies images to dist/       │
                     └────────────────┬───────────────┘
                                      │
                                      ▼
                     ┌──────────────────────────────┐
                     │   dist/index.html            │
                     │   dist/images/*.webp         │
                     │   (committed for friends)    │
                     └──────────────────────────────┘
```

### Entry points

```bash
# Full rebuild (scrape, download, merge, render)
python -m src.build

# HTML-only rebuild (no scraping; uses cache)
python -m src.build --no-scrape

# Refresh definitions only
python -m src.refresh

# Inspect a single card's resolved data
python -m src.build --inspect "Backup"
```

---

## 6. Multi-PC workflow

```bash
# Always start with this:
git pull --rebase

# Make changes (templates, overrides, data, src/...)
# Run build:
python -m src.build

# Commit & push:
git add -A
git commit -m "..."
git push
```

**No version-file conflicts** because version is computed from git, not from a file.
**No cache pollution** because `cache/` is gitignored.
**`dist/` is committed** so friends just clone and open `dist/index.html`.

---

## 7. What about GitHub Pages?

`dist/` is already a perfect static-site root. Future option:
1. Move `dist/` to `docs/` (or configure Pages to serve from `dist/`)
2. Enable GitHub Pages
3. Friends visit `https://msleeman.github.io/SWLegion-FlashCards/` instead of cloning

This is a **2-line change** in v5 architecture, not a redesign.

---

## 8. Migration plan (v4 → v5)

A weekend's work, in this order. Each step keeps the app working.

### Step 1 · Reorganize files (no code changes)
- Create `dist/`, move `swlegion_flashcards.html` → `dist/index.html`
- Create `cache/`, move `cards_cache.json` → `cache/card_data.json`, move `images/` → `cache/images/`
- Add `cache/` to `.gitignore`
- Move `card_art/*` and `manual/*` → `overrides/` (flat)
- Move `unit_db.json` → `data/unit_db.json`
- Update path constants in `build_swlegion_v4.py`
- Run build, verify it still works
- **Commit.**

### Step 2 · Extract front-end from Python
- Create `template/index.html` containing the HTML_TEMPLATE string (without the Python triple-quote)
- Replace `/*CARD_JSON*/` etc. with `{{CARD_JSON}}` style placeholders (cosmetic; or keep as-is)
- Extract embedded `<style>` block to `template/style.css`
- Extract embedded `<script>` blocks to `template/app.js`
- `index.html` references them: `<link rel="stylesheet" href="style.css">` etc. — but for offline distribution, the build inlines them
- `build_html()` becomes: read 3 files, stamp placeholders, write 1 file
- **Commit.**

### Step 3 · Split the build script
- Create `src/` package, move chunks of `build_swlegion_v4.py` into focused modules
- `src/build.py` becomes the orchestrator (~100 lines)
- Tests still pass (this is mostly file moves with import fixes)
- Delete `build_swlegion_v4.py` (or leave a one-line shim)
- **Commit.**

### Step 4 · Switch to git-based versioning
- Implement `src/version.py`
- Tag the current state: `git tag v5.0.0`
- Delete `version.txt` and `build_number.txt`
- Build prints version from `git describe`
- **Commit + push tag.**

### Step 5 · Consolidate manual mappings
- Move `KEYWORD_CARDS`, `UNIT_IMAGE_MAP`, the `_manual` aliases dict, the spelling fixes — all into `data/keyword_aliases.json` and `data/unit_keyword_mappings.json`
- Code reads them at startup
- A single keyword rename now requires **one JSON edit**, not 4 source edits
- **Commit.**

### Step 6 · Update the `swlegion-build` skill
- Reflect new paths and entry points
- Keep the "never edit dist/ directly" warning
- Add "edit `template/*` for front-end changes"
- **Commit.**

---

## 9. What stays the same

The user-facing app is byte-equivalent (modulo version string). All localStorage data (learned, lists, notes, in-browser edits) survives because the storage keys don't change. Friends pull the new commit and notice nothing different — except things just work better next time you ship a feature.
