# SWLegion FlashCards

A web-based flashcard app for learning all Star Wars: Legion keywords. Browse the catalog, study with flip-cards, and track which keywords you've added to your lists.

---

## Quick Start

```bash
# Full rebuild (scrapes web + PDF, downloads images, writes cache)
py build_swlegion_v4.py

# Fast rebuild from cache (no network, no scraping)
py rebuild_html_only.py

# Re-scrape only garbage/missing definitions
py refresh_definitions.py

# Open the result
start swlegion_flashcards.html
```

---

## Folder Structure

```
SWLegion-FlashCards/
├── build_swlegion_v4.py      # Full build script
├── rebuild_html_only.py      # Fast HTML-only rebuild (reads cache)
├── refresh_definitions.py    # Re-scrape definitions selectively
├── swlegion_flashcards.html  # Generated output — open this in a browser
├── cards_cache.json          # Cached card data (written by build scripts)
│
├── card_art/                 # YOUR manually curated images (highest priority)
│   ├── backup.png
│   ├── backup.txt            # optional: image credit line
│   └── ...
│
├── manual/                   # YOUR hand-authored text overrides (highest priority)
│   ├── backup.md             # override definition
│   ├── backup.summary.md     # override summary (one-liner shown in catalog)
│   └── ...
│
├── images/                   # Auto-downloaded images (managed by build scripts)
│   └── ...                   # do not manually place files here
│
└── SWQ_Rulebook_2.6.0-1.pdf  # optional: placed here or in documents/
```

---

## Image Priority Chain

When choosing an image for a card, the build uses this priority order:

1. **`card_art/<stem>.(png|webp|jpg)`** — your manual override wins
2. **CDN unit card** — official card image from the Legion CDN
3. **Wikimedia Commons** — fallback image scraped from the wiki

Files in `images/` are managed automatically. Do not place your own images there — use `card_art/` instead.

### Naming Convention for `card_art/`

The filename stem is derived from the keyword name:
- Strip `[]` (parameterized marker)
- Strip trailing ` X` or ` X ` (variable-value marker)
- Strip subtype qualifiers after `:` or `/`
- Apply safe filename normalization (lowercase, spaces → underscores)

| Keyword name | Expected filename |
|---|---|
| `Backup[]` | `backup.png` |
| `Pierce X` | `pierce.png` |
| `Anti-Material X` | `anti-material.png` |
| `Sharpshooter: 1` | `sharpshooter.png` |

Supported extensions: `.png`, `.webp`, `.jpg` (checked in that order).

### Optional Image Credit

Place a plain-text file `card_art/<stem>.txt` next to the image. Its contents are shown as the image credit in the catalog modal.

---

## Definition Priority Chain

When choosing a definition for a card:

1. **`manual/<stem>.md`** — your hand-authored text wins over everything
2. **PDF rulebook** — extracted from `SWQ_Rulebook_2.6.0-1.pdf` if present
3. **Bundled fallback** — hardcoded definitions for a small set of keywords
4. **Web scrape** — pulled from legion.takras.net

`apply_manual_overlays()` always runs **last** in every pipeline, so manual files can never be overwritten by a rebuild.

### Naming Convention for `manual/`

Same stem rules as `card_art/`:

| Keyword name | Definition file | Summary file |
|---|---|---|
| `Backup[]` | `manual/backup.md` | `manual/backup.summary.md` |
| `Pierce X` | `manual/pierce.md` | `manual/pierce.summary.md` |

### Summary vs Definition

- **`<stem>.md`** — the full rules text shown on the card back and in the modal
- **`<stem>.summary.md`** — a one-liner shown in the catalog tile modal, below the keyword type and above the rules text. If absent, the first sentence of the definition is used as a fallback.

---

## Refreshing Definitions

`refresh_definitions.py` re-scrapes definitions from legion.takras.net without doing a full rebuild.

```bash
# Default: only re-scrape cards with garbage/missing definitions
py refresh_definitions.py

# Re-scrape every keyword
py refresh_definitions.py --all

# Re-scrape specific keywords
py refresh_definitions.py --keywords "Backup,Pierce X,Armor X"

# Also overwrite cards that have a manual/ override (dangerous — use carefully)
py refresh_definitions.py --force-manual
```

After running, rebuild the HTML:
```bash
py rebuild_html_only.py
```

Cards with a `manual/<stem>.md` or `manual/<stem>.summary.md` file are **always skipped** by the scraper unless `--force-manual` is explicitly passed.

---

## Will My Edits Survive a Rebuild?

| Where the edit lives | Survives `rebuild_html_only.py`? | Survives `refresh_definitions.py`? | Survives `build_swlegion_v4.py`? |
|---|---|---|---|
| `manual/<stem>.md` | Yes | Yes (skipped) | Yes |
| `manual/<stem>.summary.md` | Yes | Yes (skipped) | Yes |
| `card_art/<image>` | Yes | Yes | Yes |
| In-browser custom definition (localStorage) | Yes — browser only | Yes | Yes |
| `cards_cache.json` (hand-edited) | Overwritten | Overwritten | Overwritten |

**Bottom line:** put your edits in `manual/` or `card_art/`. Never hand-edit `cards_cache.json` — it is always regenerated.

### In-Browser Edits

The flashcard app lets you edit a card's definition directly in the browser. These edits are saved to `localStorage` and survive any rebuild — they are stored in the browser, not in any file. They are per-browser and per-device. If you want an edit to be permanent and portable, copy it into a `manual/<stem>.md` file.

---

## Full Build vs Fast Rebuild

| Script | Network? | Scraping? | PDF? | Use when |
|---|---|---|---|---|
| `build_swlegion_v4.py` | Yes | Yes | Yes | First run or adding new keywords |
| `rebuild_html_only.py` | Only if image missing | No | Yes | Tweaking layout, CSS, JS, or manual overrides |
| `refresh_definitions.py` | Yes | Definitions only | No | Fixing bad definitions without full rebuild |
