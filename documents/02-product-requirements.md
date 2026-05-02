# SW Legion Flashcards — Product Requirements

*Owner: msleeman · Status: Active*

## 1. What this is

A **single-page web app** for studying every Star Wars: Legion keyword. Users browse, search, filter, mark as learned, take notes, edit definitions in-browser, and view the official rules text alongside a representative card image.

The app is a **static `.html` file**. No server, no login, no API at runtime. Drop it in any browser.

## 2. Who it's for

| Persona | Need |
|---|---|
| **The owner (msleeman)** | Study Legion keywords; build & maintain the app across multiple PCs |
| **Friends / fellow players** | Clone the GitHub repo, open the HTML, study |
| **Future Claude sessions** | Read this doc + architecture doc + skill, then make safe changes |

## 3. Distribution model

- **GitHub is the source of truth.** All commits land on `main`.
- The owner builds locally on **multiple PCs**, pulls before working, pushes after.
- Friends clone the repo and open `swlegion_flashcards.html` directly. They do not need to run the build script — the generated HTML is committed.
- Future option: serve via GitHub Pages so friends just visit a URL.

## 4. Core user-facing features (already exist — do not regress in v5)

- **Catalog view** — every keyword as a tile with image, type chip, and one-line summary
- **Search & filter** — text search, faction filter, type filter (unit/weapon/concept), learned/unlearned filter
- **Card flip view** — front shows image + name; back shows full rules text
- **Mark as learned** — per-keyword, persisted in `localStorage`
- **Lists** — pin keywords into named study lists; persisted in `localStorage`
- **Notes** — free-text per-card notes; persisted in `localStorage`
- **In-browser definition edit** — overrides shown text; persisted in `localStorage` (per-browser only)
- **Modal detail view** — opens on click; shows summary, rules, source, image credit, units that have this keyword
- **Source attribution** — every card shows where its text/image came from (legion.takras.net, PDF, manual override, etc.)
- **Bad photo / feedback** — flag a card for follow-up
- **Units field** — under source line, list units that have this keyword (added today)

## 5. Owner-side features (build pipeline)

- **One command rebuild** — `py build_swlegion_v4.py` (or v5 equivalent) does everything
- **Fast HTML-only rebuild** — for tweaking layout without re-scraping
- **Override system** — file-based, easy to maintain by hand:
  - text overrides for **summary** and **rules text**
  - image overrides
  - image credit overrides
- **Survival guarantee** — overrides never lost in any rebuild
- **PDF rulebook integration** — extract official definitions from the SWQ rulebook
- **Unit-keyword mapping** — every keyword card lists which units have it, derived from `unit_db.json`

## 6. Hard requirements

| # | Requirement | Why |
|---|---|---|
| R1 | The generated HTML must work offline (file://) | Friends use it without a server |
| R2 | All overrides must be plain files in version control | Easy to maintain, easy to diff, portable |
| R3 | One command builds the full app | Friction kills the workflow |
| R4 | Hand-edits to generated artifacts (`*.html`, `cards_cache.*`) are never required | Clear "edit here, not here" rule |
| R5 | Build is idempotent — running twice in a row produces the same output (modulo version bump) | Cache must not drift |
| R6 | Every change must be commit + pushable to GitHub without conflicts on common files | Multi-PC workflow |
| R7 | Version number is unambiguous and visible in the running app | "What version am I looking at?" |
| R8 | A new dev (or new Claude session) can read one architecture doc and understand the layout in 10 minutes | Onboarding |

## 7. Non-goals

- ❌ Real-time multiplayer / shared lists across users
- ❌ Mobile-app shell (it's a web app; phones load the HTML in the browser)
- ❌ Replacing LegionHQ2 as a full deck-builder (this is a study tool)
- ❌ Authoring tool / WYSIWYG override editor (overrides are files; that's the point)

## 8. Quality bar

- **Page load** — under 2 seconds on cold cache for the file:// HTML
- **Image fidelity** — every keyword has *some* image; "no image" cards are flagged in build output
- **Definition accuracy** — official PDF wins over scrape, manual override wins over PDF
- **Build time** — full rebuild under 5 minutes on a warm cache; under 60 seconds for HTML-only

## 9. The maintenance scenarios we actually face

These are the workflows the architecture must make **easy**:

1. **"The website spelled a keyword wrong, fix it locally"**
   → Drop `manual/<stem>.summary.md` and `manual/<stem>.md`, rebuild.

2. **"I want Cunning to show Orson Krennic instead of Count Dooku — even if the replacement is just a placeholder photo of a banana"**
   → The image override system doesn't care what's in the file, only what it's named.
   Drop ANY image as `card_art/cunning.png` (or `.webp`/`.jpg`). Rebuild. Done.
   The build's priority chain puts `card_art/` above CDN images, so your file always wins.
   In v5 this moves to `overrides/cunning.png` — same idea, one folder.

   ```
   # v4 today:
   copy my-krennic-photo.jpg  card_art\cunning.jpg
   py rebuild_html_only.py

   # v5:
   copy my-krennic-photo.jpg  overrides\cunning.jpg
   python -m src.build --no-scrape
   ```

   The stem for "Cunning" is just `cunning` (no brackets, no X, no colon). If unsure of
   the stem for any keyword, run `py -c "import build_swlegion_v4 as b; print(b._keyword_stem('Cunning'))"`.

3. **"This card's image is bad, swap it (from the CDN)"**
   → Same as above — drop `card_art/<stem>.<ext>`, rebuild.

4. **"Add a new field to every card (e.g., 'units')"**
   → Edit ONE file, rebuild. Never touch the generated HTML.

5. **"Tweak the catalog tile CSS"**
   → Edit ONE file (the CSS), rebuild. Today this requires editing inside a Python raw string.

6. **"Bump the version"**
   → Build does it. ONE version source.

7. **"I built on laptop, friend cloned and tried to push a tweak, conflict on version.txt"**
   → Should not happen by design.

8. **"My friend bookmarked the app URL — will it break when I reorganize the project?"**
   → No, by design. See §10 below.

---

## 10. URL stability — how friend bookmarks stay valid

The current GitHub Pages setup uses a **redirect shim** at the repo root:

```html
<!-- index.html (root) -->
<meta http-equiv="refresh" content="0;url=swlegion_flashcards.html">
```

So friends either visit:
- `https://msleeman.github.io/SWLegion-FlashCards/` (the nicer URL, hits `index.html`, then redirects)
- `https://msleeman.github.io/SWLegion-FlashCards/swlegion_flashcards.html` (direct)

**For v5 migration:** When the output moves to `dist/index.html` and GitHub Pages is
reconfigured to serve from `dist/`, the root URL becomes:

```
https://msleeman.github.io/SWLegion-FlashCards/
```

...which maps directly to `dist/index.html`. **Shorter, cleaner, no redirect needed.**

Friends who bookmarked the old `/swlegion_flashcards.html` path need one migration step.
Two options:

**Option A (clean break):** Update the root `index.html` redirect to point at the new location.
Friends visit their bookmark, get redirected, update their bookmark. One-time pain.

**Option B (zero pain):** Keep `swlegion_flashcards.html` in the root as a permanent redirect shim:
```html
<!-- swlegion_flashcards.html (root, permanent shim) -->
<meta http-equiv="refresh" content="0;url=dist/index.html">
```
Friends' old bookmarks keep working forever. No action required.

**Recommendation:** Option B. It costs nothing, protects all existing bookmarks, and the shim
file is 3 lines. Commit it once, never touch it again.
