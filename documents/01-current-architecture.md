# SW Legion Flashcards — Current Architecture (v4.3.x)

*Snapshot taken: 2026-04-23*

This document describes the system as it actually exists today — warts and all. See `03-proposed-v5-architecture.md` for the redesign.

---

## 1. High-level data flow

```
                    ┌────────────────────────────────────┐
                    │   EXTERNAL SOURCES (network)       │
                    │  • legion.takras.net (web scrape)  │
                    │  • LegionHQ2 CDN (unit images)     │
                    │  • Wikimedia Commons (fallback)    │
                    │  • SWQ_Rulebook_2.6.0-1.pdf        │
                    └─────────────────┬──────────────────┘
                                      │
                                      ▼
                ┌──────────────────────────────────────────┐
                │  build_swlegion_v4.py (one giant file)   │
                │   1. scrape keywords + definitions       │
                │   2. download images to images/          │
                │   3. apply manual overlays:              │
                │       ◦ manual/<stem>.md                 │
                │       ◦ manual/<stem>.summary.md         │
                │       ◦ card_art/<stem>.png|webp|jpg     │
                │       ◦ card_art/<stem>.txt (credit)     │
                │   4. inject 'units' field from unit_db   │
                │   5. write cards_cache.json              │
                │   6. stamp HTML_TEMPLATE w/ JSON & build │
                │   7. write swlegion_flashcards.html      │
                └─────────────┬────────────────┬───────────┘
                              │                │
                              ▼                ▼
                ┌──────────────────────┐  ┌─────────────────────────┐
                │   cards_cache.json   │  │ swlegion_flashcards.html│
                │ (regenerated, but    │  │  (regenerated; viewed   │
                │  committed to git)   │  │   directly in browser)  │
                └──────────────────────┘  └─────────────────────────┘
```

### Three entry-point scripts

| Script | What it does | Network? |
|---|---|---|
| `build_swlegion_v4.py` | Full rebuild: scrape, download, overlay, render | Yes |
| `rebuild_html_only.py` | Re-render HTML from `cards_cache.json` (skips scraping) | Only if image missing |
| `refresh_definitions.py` | Re-scrape only definitions for cards flagged as bad | Yes (definitions only) |

---

## 2. Files & folders today

```
C:/Users/marti/AI/SWLegion-FlashCards/
│
├── build_swlegion_v4.py        ← 4,153 lines / 228 KB — DOES EVERYTHING
├── rebuild_html_only.py        ← thin wrapper that re-imports the big script
├── refresh_definitions.py      ← targeted re-scrape
├── patch_template.py           ← legacy
├── rebuild_html_only.py
│
├── version.txt                 ← "4.3.0014"  (read+written by next_version())
├── build_number.txt            ← "23"         (incremented by a separate hook)
│   ⚠ TWO version trackers competing — source of the v4.2.0023 vs v4.3.0014 confusion
│
├── README.md                   ← user-facing docs (already good)
├── pytest.ini, requirements-dev.txt
│
├── manual/                     ← USER OVERRIDES: text (currently empty)
│   ├── <stem>.md               ← full definition override
│   └── <stem>.summary.md       ← one-liner override
│
├── card_art/                   ← USER OVERRIDES: images (166 files)
│   ├── <stem>.png|webp|jpg     ← image override
│   └── <stem>.txt              ← optional image credit
│
├── images/                     ← AUTO-DOWNLOADED images (407 files)
│   └── *.webp, *.jpg           ← from CDN + Wikimedia, managed by build
│
├── swlegion_flashcards.html    ← GENERATED (442 KB, 2,494 lines) — open in browser
├── cards_cache.json            ← GENERATED (312 KB, 3,997 lines)
│
├── legionhq2_units.json        ← cached extract of LegionHQ2 unit data
├── ../unit_db.json             ← simplified unit DB (lives in parent dir, oddly)
│
├── documents/                  ← THIS folder + the rulebook PDF
├── tests/                      ← pytest tests
├── supabase/                   ← experimental (unused?)
└── Transcripts/                ← work logs
```

---

## 3. Inside `build_swlegion_v4.py` — what's there

The single file packs at least 8 distinct concerns:

| Lines | Section | Concern |
|---|---|---|
| 1–43 | imports, paths | infra |
| 44–505 | PDF extraction | scraping |
| 506–840 | `KEYWORD_CARDS`, `UNIT_IMAGE_MAP`, manual aliases | data tables |
| 850–942 | filename helpers, override lookups | overrides |
| 943–960 | `apply_manual_overlays()` | overrides |
| 975–1080 | image download (Wikimedia + CDN) | images |
| 1081–1290 | keyword page scraper | scraping |
| 1291–1426 | unit DB JS builder + version handling | data + versioning |
| 1428–1440 | `build_html()` | rendering |
| **1442–3919** | **`HTML_TEMPLATE` (giant string)** | **HTML / CSS / JavaScript app** |
| 3920–4153 | `main()` orchestration + units injection | orchestration |

**The HTML_TEMPLATE alone is ~2,500 lines of HTML/CSS/JS embedded in a Python raw string.** Editing it is painful: no syntax highlighting, no linting, no formatter, no autocomplete. Every change requires running the build to see the result.

---

## 4. Override system (already exists — under-used)

The build supports **filename-based overrides** keyed by a normalized "stem" of the keyword name:

| Override file | Effect | Wins over |
|---|---|---|
| `manual/<stem>.md` | Full rules text | PDF / scrape |
| `manual/<stem>.summary.md` | One-line summary | First-sentence fallback |
| `card_art/<stem>.png\|.webp\|.jpg` | Card image | CDN / Wikimedia |
| `card_art/<stem>.txt` | Image credit | Default credit |

The stem normalization is in `_keyword_stem()` (line 859):
- `"Backup[]"` → `backup`
- `"Pierce X"` → `pierce`
- `"Coordinate: Type/Name[]"` → `coordinate`

`apply_manual_overlays()` runs **last** in every pipeline so overrides cannot be wiped by re-scraping. This part of the architecture is genuinely good.

The `manual/` directory is currently **empty**, meaning no text overrides have been authored yet — only image overrides exist (in `card_art/`).

---

## 5. Pain points

### 5.1 The build script is too big to edit safely
4,153 lines. Editing HTML/CSS/JS inside a Python raw string is the worst of all worlds. We've already lost edits multiple times because changes went to the *generated* HTML rather than the embedded template.

### 5.2 Two competing version files
- `version.txt` (e.g., `4.3.0014`) is incremented by `next_version()` inside the build script
- `build_number.txt` (e.g., `23`) is incremented by something else (likely a git hook)
- They drift apart. The build prints one number, GitHub shows another. Confusing.

### 5.3 Version is hardcoded into the script filename
`build_swlegion_v4.py` ties the script to a major version. To bump to v5 you either rename the file (breaking imports in `rebuild_html_only.py` etc.) or live with a stale name.

### 5.4 `images/` vs `card_art/` is fuzzy
- `images/` is auto-downloaded — but committed to git (407 files, large repo footprint)
- `card_art/` is manual — also committed to git (166 files)
- Neither is gitignored. Both are essentially "image storage." A new contributor can't tell at a glance which is canonical.

### 5.5 Scattered manual mappings
- `KEYWORD_CARDS` — keyword → list of (unit, faction) for image fallback
- `UNIT_IMAGE_MAP` — keyword → URL-encoded unit image filename
- Hardcoded array around line 2596 — keyword → image
- `_manual` dict in units injection (~line 4040) — unit-keyword spelling fixes
- Spelling alias hardcoded ("Inconspicious" misspelling) appears in 4+ places

A keyword name change can break in 4 different places. There's no single source of truth.

### 5.6 No clear separation between "cache" and "source of truth"
`cards_cache.json` is regenerated on every build, but is also committed to git. So it acts as both a cache *and* a checked-in artifact. Hand-edits get wiped — but the file is big and noisy in PRs.

### 5.7 Multi-PC sync risk
Building on PC A and PC B at different times means each PC increments `version.txt` locally. Push from both → merge conflict on `version.txt`. The current setup leaves this entirely to manual coordination.

---

## 6. What's working well

These should be **preserved** in any redesign:

- ✅ The override mental model: `manual/` for text, `card_art/` for images, both filename-based
- ✅ Three-tier rebuild scripts (full / fast / definitions-only)
- ✅ Override priority is documented and apply-overlays-last is correct
- ✅ Localstorage in-browser edits for ad-hoc personal customization
- ✅ Existing README.md has a clear table of "will my edit survive a rebuild?"
- ✅ Stem normalization handles `[]`, `X`, `:` suffixes consistently
