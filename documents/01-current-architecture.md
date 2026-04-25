# SW Legion Flashcards — Architecture (v5, complete)

*Last updated: 2026-04-25 — v5 migration complete*

This document describes the system as it currently exists. The v5 refactor is done.
See `03-proposed-v5-architecture.md` for the original proposal (now marked implemented).

---

## 1. High-level data flow

```
                    ┌────────────────────────────────────┐
                    │   EXTERNAL SOURCES (network)       │
                    │  • legion.takras.net (web scrape)  │
                    │  • LegionHQ2 CDN (unit images)     │
                    │  • Wikimedia Commons (fallback)    │
                    │  • documents/SWQ_Rulebook_2.6.0.pdf│
                    └─────────────────┬──────────────────┘
                                      │
                     ┌────────────────▼──────────────────┐
                     │   src/scrape.py  +  src/images.py │
                     └────────────────┬──────────────────┘
                                      │
                                      ▼
                     ┌─────────────────────────────────┐
                     │   cache/card_data.json          │
                     │   cache/images/*.webp           │
                     │   (gitignored, regenerable)     │
                     └────────────────┬────────────────┘
                                      │
              ┌───────────────────────▼───────────────────────┐
              │   src/overrides.py  +  src/units.py           │
              │   merge: cache + overrides/ + data/unit_db    │
              └───────────────────────┬───────────────────────┘
                                      │
                     ┌────────────────▼────────────────┐
                     │   src/render.py                 │
                     │   reads template/index.html,    │
                     │   template/app.css,             │
                     │   template/app.js;              │
                     │   stamps placeholders;          │
                     │   copies images to dist/        │
                     └────────────────┬────────────────┘
                                      │
                     ┌────────────────▼────────────────┐
                     │   dist/index.html               │
                     │   dist/images/*.webp            │
                     │   (committed for friends)       │
                     └─────────────────────────────────┘
```

### Entry-point scripts

| Script | What it does | Network? |
|---|---|---|
| `py -m src.build` | Full rebuild: scrape, download, merge, render | Yes |
| `py rebuild_html_only.py` | Re-render HTML from cache (skips scraping) | Only if image missing |
| `py refresh_definitions.py` | Re-scrape only bad definitions | Yes (defs only) |

---

## 2. Files & folders

```
SWLegion-FlashCards/
│
├── src/                          # Python build modules
│   ├── build.py                  # main() orchestrator
│   ├── config.py                 # path constants
│   ├── data_tables.py            # KEYWORD_PAGES, KEYWORD_CARDS, BUNDLED_KEYWORDS
│   │                             # KEYWORD_CARD_IMAGES loaded from data/keyword_images.json
│   ├── scrape.py                 # legion.takras.net + PDF extraction
│   ├── images.py                 # CDN + Wikimedia image download
│   ├── overrides.py              # override resolution (card_art, manual files)
│   ├── units.py                  # inject 'units' field from unit_db.json
│   └── render.py                 # build_html(), get_version()
│
├── template/                     # Front-end source — edit here, not in dist/
│   ├── index.html                # HTML skeleton with {{VERSION}}, /*STYLE_CSS*/, /*APP_JS*/
│   ├── app.css                   # All CSS
│   └── app.js                    # All JavaScript (with /*CARD_JSON*/ etc. placeholders)
│
├── overrides/                    # USER OVERRIDES (committed, always survive rebuilds)
│   ├── <stem>.md                 # Full rules text override
│   ├── <stem>.summary.md         # One-liner summary override
│   ├── <stem>.png|webp|jpg       # Image override
│   └── <stem>.txt                # Image credit line
│
├── data/                         # Canonical input data (committed)
│   ├── unit_db.json              # Unit data extracted from LegionHQ2
│   ├── unit_keyword_mappings.json# Maps unit keyword strings → canonical card names
│   └── keyword_images.json       # Maps keyword name → CDN image filename
│
├── dist/                         # BUILD OUTPUT (committed for distribution)
│   ├── index.html                # Generated, self-contained app
│   └── images/                   # Final image set
│
├── cache/                        # GITIGNORED. Regenerated. Never edit.
│   ├── card_data.json
│   ├── images/
│   └── legionhq2_units.json
│
├── documents/                    # Architecture, PRD, design docs, rulebook PDF
├── build_swlegion_v4.py          # Legacy shim → delegates to src.build
├── rebuild_html_only.py          # Fast HTML-only rebuild
├── refresh_definitions.py        # Re-scrape definitions selectively
├── index.html                    # Redirect shim → dist/index.html
└── swlegion_flashcards.html      # Redirect shim → dist/index.html
```

---

## 3. Override system

One flat folder, keyed by keyword stem.

| Override file | Effect | Survives rebuild? |
|---|---|---|
| `overrides/<stem>.md` | Full rules text | ✅ Yes |
| `overrides/<stem>.summary.md` | One-liner summary | ✅ Yes |
| `overrides/<stem>.png\|webp\|jpg` | Card image | ✅ Yes |
| `overrides/<stem>.txt` | Image credit | ✅ Yes |
| In-browser edit (localStorage) | Personal notes/def edits | ✅ Yes (browser only) |

**Stem rules:**
- `Backup[]` → `backup`
- `Pierce X` → `pierce`
- `Coordinate: Type/Name[]` → `coordinate`
- `Sharpshooter 1` → `sharpshooter`

---

## 4. Versioning

`git describe --tags --always --dirty` — no version file. Tag a release:
```bash
git tag v5.x.y && git push origin v5.x.y
```

---

## 5. Data tables — sources of truth

| Data | File |
|---|---|
| Keyword → CDN image | `data/keyword_images.json` (edit here) |
| Unit keyword string → card name | `data/unit_keyword_mappings.json` |
| Unit → keywords (injected) | `data/unit_db.json` |
| Keyword pages (scrape order) | `src/data_tables.py` → `KEYWORD_PAGES` |
| Bundled offline definitions | `src/data_tables.py` → `BUNDLED_KEYWORDS` |

A keyword rename now requires **one JSON edit** in `keyword_images.json`, not scattered source edits.
