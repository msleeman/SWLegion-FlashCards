#!/usr/bin/env python3
"""
Star Wars Legion Flashcards — Builder v1
==========================================
1. Scrapes keywords from legionquickguide.com
2. Searches for a Star Wars image for each keyword
3. Builds swlegion_flashcards.html + images/

Usage:
    py -m pip install requests beautifulsoup4
    py build_swlegion.py

Output:
    swlegion_flashcards.html
    images/   (one jpg per keyword)
"""

import requests, json, os, re, time
from urllib.parse import urlencode

HERE   = os.path.dirname(os.path.abspath(__file__))
IMGDIR = os.path.join(HERE, "images")
OUT    = os.path.join(HERE, "swlegion_flashcards.html")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ── Keywords to SKIP (too general / not a flashcard-worthy concept) ────────────
SKIP_SECTIONS = {
    "Activating Units", "Activation Phase", "Actions", "Attack",
    "Command Phase", "End Phase", "Setup", "Deployment", "Terrain",
    "Area Terrain", "Bases", "Dice", "Weapons", "Movement",
    "Line of Sight", "Suppression", "Winning the Game",
    "Issuing Orders", "Order Pool", "Priority", "Rank", "Unit",
    "Miniature", "Cohesion", "Panic", "Wound", "Defeated",
    "Friendly", "Allied", "Enemy", "Battlefield", "Advantage Token",
    "Asset Token", "Objective Tokens", "Charge Tokens",
    "Upgrade Cards", "Command Cards", "Battle Cards",
}

# ── Image search: Wikimedia Commons first, then fallback query ──────────────────
WIKI_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKI_EN_API      = "https://en.wikipedia.org/w/api.php"


def safe_filename(name):
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:60] + ".jpg"


def search_image(keyword_name):
    """
    Try to find a relevant Star Wars image.
    Strategy: search Wikipedia for the SW concept, then Commons.
    """
    # Clean up keyword for searching — strip (X), (Unit Keyword), etc.
    clean = re.sub(r"\s*[\(\[].*?[\)\]]", "", keyword_name).strip()
    clean = re.sub(r"\s+X$", "", clean).strip()

    search_terms = [
        f"Star Wars Legion {clean}",
        f"Star Wars {clean}",
        clean,
    ]

    for term in search_terms:
        try:
            r = requests.get(WIKI_COMMONS_API, headers=HEADERS, timeout=10, params={
                "action": "query", "generator": "search",
                "gsrnamespace": "6", "gsrsearch": term, "gsrlimit": "5",
                "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": "1200",
                "format": "json",
            })
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                info = (page.get("imageinfo") or [{}])[0]
                url  = info.get("thumburl") or info.get("url", "")
                mime = info.get("mime", "")
                if url and "image" in mime and re.search(r"\.(jpe?g|png|webp)$", url, re.I):
                    return url
        except Exception:
            pass
        time.sleep(0.3)

    return None


def download_image(keyword_name, imgdir):
    fname    = safe_filename(keyword_name)
    filepath = os.path.join(imgdir, fname)

    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        return f"images/{fname}", True  # already exists

    url = search_image(keyword_name)
    if not url:
        return None, False

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(r.content)
        return f"images/{fname}", False
    except Exception:
        return None, False


def scrape_keywords():
    """Parse legionquickguide.com for keyword name + definition pairs."""
    print("  Fetching legionquickguide.com...")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  ERROR: beautifulsoup4 not installed.")
        print("  Run: py -m pip install beautifulsoup4")
        raise

    r = requests.get("https://legionquickguide.com/", headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    keywords = []
    seen     = set()

    # Each keyword is an <h4> tag, followed by <p> tags with the definition
    for h4 in soup.find_all("h4"):
        raw_name = h4.get_text(strip=True)

        # Determine keyword type from name
        ktype = "concept"
        if "(Unit Keyword)" in raw_name:
            ktype = "unit"
        elif "(Weapon Keyword)" in raw_name:
            ktype = "weapon"
        elif "(Upgrade Keyword)" in raw_name or "(Command Card Keyword)" in raw_name:
            ktype = "upgrade"

        # Clean display name
        display = re.sub(r"\s*\(Unit Keyword\)|\s*\(Weapon Keyword\)|\s*\(Upgrade.*?\)|\s*\(Command.*?\)", "", raw_name).strip()

        if display in seen or display in SKIP_SECTIONS:
            continue
        if len(display) < 3 or display.startswith("Example:") or display.startswith("EXAMPLE"):
            continue
        seen.add(display)

        # Gather definition paragraphs — collect text until next h4
        definition_parts = []
        for sib in h4.find_next_siblings():
            if sib.name in ("h4", "h3", "h2"):
                break
            if sib.name == "p":
                text = sib.get_text(" ", strip=True)
                # Skip "Related Topics:" lines
                if text.startswith("Related Topics"):
                    break
                if text and len(text) > 20:
                    definition_parts.append(text)
            if sib.name in ("ul", "ol"):
                # Include list items as bullet text
                items = [li.get_text(" ", strip=True) for li in sib.find_all("li")]
                definition_parts.extend(items[:4])  # cap at 4 bullets

        if not definition_parts:
            continue

        # Keep definition concise — first 2 paragraphs max, cap at 400 chars
        definition = " ".join(definition_parts[:2])
        # Remove image descriptions like "![aim token](url)"
        definition = re.sub(r"!\[.*?\]\(.*?\)", "", definition)
        # Clean up leftover markdown artifacts
        definition = re.sub(r"\s+", " ", definition).strip()
        if len(definition) > 450:
            definition = definition[:447] + "..."

        if len(definition) < 20:
            continue

        keywords.append({
            "name":       display,
            "definition": definition,
            "type":       ktype,
            "raw_name":   raw_name,
        })

    print(f"  Scraped {len(keywords)} keywords")
    return keywords


def build_html(card_data):
    fish_js    = json.dumps(card_data, ensure_ascii=False)
    base_names = json.dumps([c["name"] for c in card_data], ensure_ascii=False)
    html = HTML_TEMPLATE.replace("/*CARD_JSON*/", fish_js)
    html = html.replace("/*BASE_NAMES*/", base_names)
    return html


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SW Legion Keywords</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --gold:#f5c518;--golddim:#a8870d;
  --red:#c0392b;--redbg:rgba(192,57,43,.15);
  --blue:#3498db;--bluebg:rgba(52,152,219,.15);
  --G:#1D9E75;--Gbg:rgba(29,158,117,.15);--Gt:#a8ffd8;
  --R:#ff4444;--Rbg:rgba(255,68,68,.15);--Rt:#ffaaaa;
  --A:#f5a623;--Abg:rgba(245,166,35,.15);--At:#ffe0a0;
  --glass:rgba(0,0,0,.6);--glass2:rgba(0,0,0,.8);
  --white:rgba(255,255,255,.95);--white2:rgba(255,255,255,.65);
  --rs:10px;--rb:16px;
}
html,body{width:100%;height:100%;overflow:hidden;
  background:#0a0a0f;
  font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,sans-serif}

/* ── Screens ── */
.screen{position:fixed;inset:0;display:none}
.screen.on{display:block}

/* ══════════════════════════════
   FLASHCARD SCREEN
══════════════════════════════ */
#fs-bg{position:absolute;inset:0;background:#0a0a0f;overflow:hidden}
#fs-img{position:absolute;inset:0;width:100%;height:100%;
  object-fit:cover;opacity:.45;transition:opacity .4s}
#fs-img.dim{opacity:.25}

/* Imperial scanline texture overlay */
#fs-scan{position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,
    transparent,transparent 2px,
    rgba(0,0,0,.08) 2px,rgba(0,0,0,.08) 4px);
  z-index:1}

#fs-top-grad{position:absolute;top:0;left:0;right:0;height:200px;
  background:linear-gradient(rgba(0,0,0,.85),transparent);pointer-events:none;z-index:2}
#fs-bot-grad{position:absolute;bottom:0;left:0;right:0;height:60%;
  background:linear-gradient(transparent,rgba(0,0,0,.95));pointer-events:none;z-index:2}

#fs-flip-zone{position:absolute;inset:0;cursor:pointer;z-index:3}

/* Top bar */
#fs-topbar{position:absolute;top:0;left:0;right:0;
  padding:14px 16px 0;display:flex;align-items:center;gap:10px;
  z-index:10;pointer-events:none}
#fs-topbar>*{pointer-events:all}

.fs-pill{background:rgba(0,0,0,.6);backdrop-filter:blur(12px);
  border:1px solid rgba(245,197,24,.25);border-radius:20px;
  color:var(--white);font-size:13px;padding:6px 14px;cursor:pointer;
  transition:all .2s;font-family:inherit}
.fs-pill.active{background:rgba(245,197,24,.2);border-color:var(--gold);color:var(--gold)}
.fs-pill:hover:not(.active){background:rgba(255,255,255,.1)}

.type-badge{font-size:11px;font-weight:700;letter-spacing:.5px;
  padding:4px 10px;border-radius:20px;text-transform:uppercase}
.type-unit{background:rgba(52,152,219,.25);border:1px solid #3498db;color:#7ec8f5}
.type-weapon{background:rgba(192,57,43,.25);border:1px solid #c0392b;color:#f08080}
.type-upgrade{background:rgba(155,89,182,.25);border:1px solid #9b59b6;color:#d7b4f5}
.type-concept{background:rgba(245,197,24,.15);border:1px solid var(--golddim);color:var(--gold)}

#fs-progress{flex:1;height:2px;background:rgba(255,255,255,.15);
  border-radius:2px;margin:0 8px}
#fs-pfill{height:100%;background:var(--gold);transition:width .3s;border-radius:2px}
#fs-ctr{color:var(--white2);font-size:13px;white-space:nowrap}
#fs-quiz-stats{display:none;gap:12px;align-items:center}
.fs-stat{color:var(--white2);font-size:13px}
.fs-stat span{font-weight:700;color:var(--white)}
.fs-stat.ok span{color:#6effc4}.fs-stat.wr span{color:#ff8888}

/* Side nav */
#fs-prev,#fs-next{position:absolute;top:50%;transform:translateY(-50%);
  z-index:10;background:rgba(0,0,0,.55);backdrop-filter:blur(12px);
  border:1px solid rgba(245,197,24,.2);border-radius:50%;
  width:44px;height:44px;display:flex;align-items:center;justify-content:center;
  cursor:pointer;color:var(--gold);font-size:18px;transition:all .2s}
#fs-prev{left:12px}#fs-next{right:12px}
#fs-prev:hover,#fs-next:hover{background:rgba(245,197,24,.15)}
#fs-prev:disabled,#fs-next:disabled{opacity:.2;cursor:default}

/* Top-right */
#fs-nav-btns{position:absolute;top:14px;right:16px;display:flex;gap:8px;z-index:10}

/* Bottom panel */
#fs-bottom{position:absolute;bottom:0;left:0;right:0;
  padding:0 20px 24px;z-index:10}

/* FRONT: show keyword name only */
#fs-front-content{display:block}
#fs-keyword-name{
  font-size:clamp(32px,7vw,64px);font-weight:800;
  color:var(--gold);line-height:1.1;
  text-shadow:0 0 40px rgba(245,197,24,.4),0 2px 8px rgba(0,0,0,.8);
  letter-spacing:-0.5px}
#fs-keyword-subtext{font-size:15px;color:var(--white2);margin-top:6px;
  text-shadow:0 1px 4px rgba(0,0,0,.8)}
#fs-tap-hint{font-size:13px;color:rgba(255,255,255,.4);
  margin-top:12px;letter-spacing:.5px;font-style:italic}

/* BACK: definition reveal */
#fs-back-content{display:none}
#fs-back-name{font-size:22px;font-weight:700;color:var(--gold);margin-bottom:8px}
#fs-definition{font-size:15px;color:var(--white);line-height:1.7;
  max-width:660px;text-shadow:0 1px 4px rgba(0,0,0,.6)}
#fs-source{font-size:11px;color:rgba(255,255,255,.3);margin-top:8px}

/* Actions */
#fs-actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
.fs-btn{background:rgba(0,0,0,.55);backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,.15);border-radius:var(--rs);
  color:var(--white2);font-size:13px;padding:8px 16px;cursor:pointer;
  font-family:inherit;transition:all .2s}
.fs-btn:hover{background:rgba(255,255,255,.12);color:var(--white)}
.fs-btn.learned{background:rgba(29,158,117,.3);border-color:var(--G);color:var(--Gt)}
.fs-btn.flagged{background:rgba(245,166,35,.2);border-color:var(--A);color:var(--At)}

/* Status bar */
#fs-status{max-height:0;overflow:hidden;text-align:center;font-size:13px;
  font-weight:500;border-radius:var(--rs);transition:all .25s;margin-bottom:0}
#fs-status.show{max-height:40px;padding:8px 14px;margin-bottom:8px}
#fs-status.ok{background:var(--Gbg);color:var(--Gt);border:1px solid rgba(29,158,117,.3)}
#fs-status.err{background:var(--Rbg);color:var(--Rt);border:1px solid rgba(255,68,68,.3)}
#fs-status.work{background:var(--Abg);color:var(--At);border:1px solid rgba(245,166,35,.3)}

/* Quiz */
#fs-opts{display:none;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
#fs-opts.on{display:grid}
.fs-opt{background:rgba(0,0,0,.6);backdrop-filter:blur(12px);
  border:1px solid rgba(245,197,24,.2);border-radius:var(--rs);
  color:var(--white);font-size:14px;padding:12px 10px;cursor:pointer;
  font-family:inherit;transition:all .15s;text-align:center;line-height:1.3}
.fs-opt:hover:not(:disabled){background:rgba(245,197,24,.1);border-color:var(--gold)}
.fs-opt.correct{background:rgba(29,158,117,.35);border-color:var(--G);color:var(--Gt);font-weight:700}
.fs-opt.wrong{background:rgba(255,68,68,.25);border-color:var(--R);color:var(--Rt)}
#fs-qres{display:none;text-align:center;padding:10px 14px;font-size:14px;
  font-weight:600;border-radius:var(--rs);margin-bottom:10px}
#fs-qres.on{display:block}
#fs-qres.ok{background:var(--Gbg);color:var(--Gt);border:1px solid rgba(29,158,117,.3)}
#fs-qres.no{background:var(--Rbg);color:var(--Rt);border:1px solid rgba(255,68,68,.3)}

/* All-learned */
#fs-alldone{position:absolute;inset:0;display:none;z-index:20;
  background:rgba(0,0,0,.85);backdrop-filter:blur(20px);
  align-items:center;justify-content:center;flex-direction:column;
  gap:20px;text-align:center;padding:2rem}
#fs-alldone.on{display:flex}
#fs-alldone h2{font-size:32px;color:var(--gold);font-weight:800;
  text-shadow:0 0 30px rgba(245,197,24,.5)}
#fs-alldone p{color:var(--white2);font-size:15px;max-width:400px;line-height:1.6}
.big-btn{border:none;border-radius:var(--rb);font-size:15px;font-weight:700;
  padding:13px 30px;cursor:pointer;font-family:inherit;transition:all .2s}
.big-btn.gold{background:var(--gold);color:#000}
.big-btn.gold:hover{background:#ffd700;transform:translateY(-1px)}
.big-btn.ghost{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);
  color:var(--white2)}
.big-btn.ghost:hover{background:rgba(255,255,255,.15)}

/* ══════════════════════════════
   CATALOG SCREEN
══════════════════════════════ */
#catalog-screen{background:#0a0a0f;overflow-y:auto}
.cat-wrap{max-width:960px;margin:0 auto;padding:20px}
.cat-top{display:flex;align-items:center;justify-content:space-between;
  margin-bottom:20px;gap:12px;flex-wrap:wrap}
.cat-top h1{font-size:20px;font-weight:700;
  color:var(--gold);text-shadow:0 0 20px rgba(245,197,24,.3)}
.cat-top-btns{display:flex;gap:8px}
.dark-pill{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);
  border-radius:20px;color:var(--white2);font-size:13px;padding:6px 14px;
  cursor:pointer;font-family:inherit;transition:all .2s}
.dark-pill:hover{background:rgba(255,255,255,.12)}
.dark-pill.active{background:rgba(245,197,24,.15);border-color:var(--gold);color:var(--gold)}
.cat-filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.cat-count{font-size:13px;color:rgba(255,255,255,.3);margin-bottom:12px}
.cat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.cat-card{border-radius:var(--rs);overflow:hidden;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);
  cursor:pointer;transition:transform .15s,box-shadow .15s,border-color .15s;
  position:relative}
.cat-card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.5);
  border-color:rgba(245,197,24,.2)}
.cat-card.lrnd{border-color:rgba(29,158,117,.4);border-width:2px}
.cat-thumb{width:100%;height:100px;object-fit:cover;display:block;
  background:#0a1020;opacity:.7}
.cat-thumb-ph{width:100%;height:100px;background:linear-gradient(135deg,#0a1020,#1a1a30);
  display:flex;align-items:center;justify-content:center;
  color:rgba(255,255,255,.15);font-size:11px;text-align:center;padding:.5rem}
.cat-lbl{padding:8px 10px}
.cat-name{font-size:12px;font-weight:600;color:var(--white);line-height:1.3}
.cat-type{font-size:10px;color:rgba(255,255,255,.35);margin-top:2px;text-transform:uppercase;letter-spacing:.3px}
.cat-badge{position:absolute;top:6px;right:6px;font-size:10px;font-weight:700;
  padding:2px 8px;border-radius:10px}
.badge-learned{background:var(--G);color:#fff}
.empty-msg{color:rgba(255,255,255,.2);font-size:14px;
  grid-column:1/-1;padding:3rem 0;text-align:center}

/* ══════════════════════════════
   MODAL
══════════════════════════════ */
#modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);
  z-index:100;align-items:center;justify-content:center;
  padding:1rem;backdrop-filter:blur(10px)}
#modal-bg.on{display:flex}
.modal-box{background:#0d1020;border:1px solid rgba(245,197,24,.2);
  border-radius:var(--rb);max-width:540px;width:100%;
  overflow:hidden;max-height:90vh;overflow-y:auto;
  box-shadow:0 0 40px rgba(245,197,24,.1)}
.modal-photo{width:100%;height:220px;object-fit:cover;display:block;
  background:#0a1020;opacity:.7}
.modal-photo-ph{width:100%;height:220px;
  background:linear-gradient(135deg,#0a1020,#1a1a30);display:flex;
  align-items:center;justify-content:center;color:rgba(255,255,255,.2);
  font-size:13px;text-align:center;padding:1rem;line-height:1.6}
.modal-body{padding:1.25rem}
.modal-name{font-size:22px;font-weight:800;color:var(--gold)}
.modal-type{font-size:12px;margin-top:4px}
.modal-def{font-size:13px;color:rgba(255,255,255,.75);line-height:1.7;margin-top:.75rem}
.modal-src{font-size:11px;color:rgba(255,255,255,.25);margin-top:.5rem}
.modal-status{font-size:12px;font-weight:500;margin-top:.4rem;min-height:18px}
.modal-status.ok{color:var(--Gt)}.modal-status.err{color:var(--Rt)}.modal-status.work{color:var(--At)}
.modal-acts{display:flex;gap:8px;margin-top:1rem;flex-wrap:wrap}
.modal-btn{padding:9px 18px;border-radius:var(--rs);
  background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);
  cursor:pointer;font-size:13px;font-family:inherit;color:var(--white2);transition:all .15s}
.modal-btn:hover{background:rgba(255,255,255,.12)}
.modal-btn.lrnd{background:rgba(29,158,117,.25);border-color:var(--G);color:var(--Gt);font-weight:600}
.modal-btn.flagd{background:var(--Abg);border-color:var(--A);color:var(--At)}
.modal-btn.cls{margin-left:auto;background:rgba(255,255,255,.04)}

@media(max-width:500px){
  #fs-keyword-name{font-size:28px}
  #fs-opts{grid-template-columns:1fr}
  .cat-grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}
}
</style>
</head>
<body>

<!-- ══ FLASHCARD SCREEN ══ -->
<div class="screen on" id="flashcard-screen">
  <div id="fs-bg">
    <img id="fs-img" src="" alt="">
    <div id="fs-scan"></div>
    <div id="fs-top-grad"></div>
    <div id="fs-bot-grad"></div>
  </div>

  <div id="fs-flip-zone" onclick="handleTap()"></div>

  <div id="fs-topbar">
    <button class="fs-pill active" id="pill-learn" onclick="setMode('learn')">Learn</button>
    <button class="fs-pill" id="pill-quiz" onclick="setMode('quiz')">Quiz</button>
    <div id="fs-type-filter">
      <button class="fs-pill active" id="pill-all" onclick="setTypeFilter('all')">All</button>
      <button class="fs-pill" id="pill-unit" onclick="setTypeFilter('unit')">Unit</button>
      <button class="fs-pill" id="pill-weapon" onclick="setTypeFilter('weapon')">Weapon</button>
    </div>
    <div id="fs-progress"><div id="fs-pfill" style="width:0%"></div></div>
    <span id="fs-ctr"></span>
    <div id="fs-quiz-stats">
      <div class="fs-stat ok">✓<span id="sc">0</span></div>
      <div class="fs-stat wr">✗<span id="sw">0</span></div>
    </div>
  </div>

  <div id="fs-nav-btns">
    <button class="fs-pill" onclick="showScreen('catalog-screen')">Catalog</button>
  </div>

  <button id="fs-prev" onclick="go(-1)">&#8592;</button>
  <button id="fs-next" onclick="go(1)">&#8594;</button>

  <div id="fs-bottom">
    <div id="fs-status"></div>
    <div id="fs-qres"></div>
    <div id="fs-opts"></div>

    <div id="fs-front-content">
      <div id="fs-keyword-name"></div>
      <div id="fs-keyword-subtext"></div>
      <div id="fs-tap-hint">Tap anywhere to reveal definition</div>
    </div>

    <div id="fs-back-content">
      <div id="fs-back-name"></div>
      <div id="fs-definition"></div>
      <div id="fs-source">Source: legionquickguide.com</div>
      <div id="fs-actions"></div>
    </div>
  </div>

  <div id="fs-alldone">
    <div style="font-size:56px">⚡</div>
    <h2>All keywords learned!</h2>
    <p>You've mastered all active keywords.<br>Reset or change your filter to continue.</p>
    <button class="big-btn gold" onclick="resetLearned()">Start Over</button>
    <button class="big-btn ghost" onclick="showScreen('catalog-screen')">View Catalog</button>
  </div>
</div>

<!-- ══ CATALOG SCREEN ══ -->
<div class="screen" id="catalog-screen" style="background:#0a0a0f;overflow-y:auto">
  <div class="cat-wrap">
    <div class="cat-top">
      <h1>⚡ SW Legion Keywords</h1>
      <div class="cat-top-btns">
        <button class="dark-pill" onclick="showScreen('flashcard-screen')">← Back</button>
      </div>
    </div>
    <div class="cat-filters" id="cat-filters">
      <button class="dark-pill active" onclick="setCF('all',this)">All</button>
      <button class="dark-pill" onclick="setCF('learned',this)">Learned</button>
      <button class="dark-pill" onclick="setCF('unlearned',this)">Unlearned</button>
      <button class="dark-pill" onclick="setCF('unit',this)">Unit Keywords</button>
      <button class="dark-pill" onclick="setCF('weapon',this)">Weapon Keywords</button>
      <button class="dark-pill" onclick="setCF('concept',this)">Concepts</button>
    </div>
    <div class="cat-count" id="cat-count"></div>
    <div class="cat-grid" id="cat-grid"></div>
  </div>
</div>

<!-- ══ MODAL ══ -->
<div id="modal-bg" onclick="closeMod(event)">
  <div class="modal-box" onclick="event.stopPropagation()">
    <div id="mod-img"></div>
    <div class="modal-body">
      <div class="modal-name" id="mod-name"></div>
      <div class="modal-type" id="mod-type"></div>
      <div class="modal-def"  id="mod-def"></div>
      <div class="modal-src">Source: legionquickguide.com</div>
      <div class="modal-status" id="mod-st"></div>
      <div class="modal-acts">
        <button class="modal-btn" id="mod-lrnd"  onclick="modToggleLearned()"></button>
        <button class="modal-btn" id="mod-photo" onclick="modBadPhoto()">📷 Bad photo</button>
        <button class="modal-btn cls"             onclick="closeMod()">Close</button>
      </div>
    </div>
  </div>
</div>

<script>
const CARDS = /*CARD_JSON*/;

// ── State ──────────────────────────────────────────────────────────────────────
const ST = {};
CARDS.forEach(c => { ST[c.name]={idx:0,learned:false,flagged:false,busy:false}; });

function loadState(){
  try{
    const saved=JSON.parse(localStorage.getItem('swlegion_v1')||'{}');
    Object.keys(saved).forEach(n=>{ if(ST[n]) Object.assign(ST[n],saved[n]); });
  }catch(e){}
}
function saveState(){
  const out={};
  Object.keys(ST).forEach(n=>{ const{idx,learned,flagged}=ST[n]; out[n]={idx,learned,flagged}; });
  localStorage.setItem('swlegion_v1',JSON.stringify(out));
}

function s(n){ return ST[n]||{idx:0,learned:false,flagged:false,busy:false}; }
function ci(c){ const st=s(c.name); return (c.imgs&&c.imgs[st.idx])||(c.imgs&&c.imgs[0])||''; }
function ic(c){ return (c.imgs&&c.imgs.length)||0; }

// ── Status ─────────────────────────────────────────────────────────────────────
let _st=null;
function setStatus(msg,cls,ms){
  const el=document.getElementById('fs-status');
  el.textContent=msg; el.className='show '+(cls||'ok');
  clearTimeout(_st); if(ms) _st=setTimeout(()=>{el.textContent='';el.className='';},ms);
}
function clrStatus(){ clearTimeout(_st); const el=document.getElementById('fs-status'); el.textContent='';el.className=''; }

// ── Screens ────────────────────────────────────────────────────────────────────
function showScreen(id){
  document.querySelectorAll('.screen').forEach(el=>el.classList.remove('on'));
  document.getElementById(id).classList.add('on');
  if(id==='catalog-screen') renderCatalog();
}

// ── Type filter ────────────────────────────────────────────────────────────────
let typeFilter='all';
function setTypeFilter(t){
  typeFilter=t;
  ['all','unit','weapon'].forEach(x=>{
    document.getElementById('pill-'+x).classList.toggle('active',x===t);
  });
  clrStatus(); initDeck(); render();
}

function filteredCards(){
  if(typeFilter==='all') return CARDS;
  if(typeFilter==='weapon') return CARDS.filter(c=>c.type==='weapon');
  if(typeFilter==='unit') return CARDS.filter(c=>c.type==='unit');
  return CARDS;
}

// ── Flashcard ──────────────────────────────────────────────────────────────────
let deck=[],cur=0,mode='learn',revealed=false,answered=false;
let sc=0,sw=0;

function activeDeck(){ return filteredCards().filter(c=>!s(c.name).learned); }
function shuffle(a){ for(let i=a.length-1;i>0;i--){const j=0|Math.random()*(i+1);[a[i],a[j]]=[a[j],a[i]];} }
function initDeck(){ deck=[...activeDeck()]; shuffle(deck); cur=0; }

function render(){
  const alive=activeDeck();
  const alldone=document.getElementById('fs-alldone');
  if(!alive.length){ alldone.classList.add('on'); return; }
  alldone.classList.remove('on');

  while(deck[cur]&&s(deck[cur].name).learned&&cur<deck.length) cur++;
  if(!deck[cur]||s(deck[cur].name).learned) initDeck();

  const c=deck[cur];
  revealed=false; answered=false;

  const qr=document.getElementById('fs-qres'); qr.className=''; qr.textContent='';
  document.getElementById('fs-opts').className='';

  document.getElementById('fs-pfill').style.width=Math.round(((cur+1)/deck.length)*100)+'%';
  document.getElementById('fs-ctr').textContent=(cur+1)+'/'+deck.length;
  document.getElementById('fs-prev').disabled=cur===0;
  document.getElementById('fs-next').disabled=cur===deck.length-1;

  // Image
  const img=document.getElementById('fs-img');
  const src=ci(c);
  if(src){ img.src=src; img.style.display='block'; }
  else   { img.style.display='none'; }

  showFront(c);
  renderActions(c);
}

function typeBadgeHTML(type){
  const labels={unit:'Unit Keyword',weapon:'Weapon Keyword',upgrade:'Upgrade',concept:'Concept'};
  return `<span class="type-badge type-${type}">${labels[type]||type}</span>`;
}

function showFront(c){
  document.getElementById('fs-front-content').style.display='block';
  document.getElementById('fs-back-content').style.display='none';
  document.getElementById('fs-keyword-name').textContent=c.name;
  document.getElementById('fs-keyword-subtext').innerHTML=typeBadgeHTML(c.type);
  document.getElementById('fs-tap-hint').style.display=mode==='learn'?'block':'none';
  document.getElementById('fs-img').classList.remove('dim');
  if(mode==='quiz') renderOpts(c);
}

function showBack(c){
  document.getElementById('fs-front-content').style.display='none';
  document.getElementById('fs-back-content').style.display='block';
  document.getElementById('fs-back-name').innerHTML=c.name+' '+typeBadgeHTML(c.type);
  document.getElementById('fs-definition').textContent=c.definition;
  document.getElementById('fs-img').classList.add('dim');
}

function renderActions(c){
  const st=s(c.name), n=ic(c);
  const sn=c.name.replace(/'/g,"\\'");
  const pl=st.busy?'⏳...':n>1?`📷 (${st.idx+1}/${n})`:'📷 Bad photo';
  document.getElementById('fs-actions').innerHTML=
    `<button class="fs-btn${st.learned?' learned':''}" onclick="toggleLearned('${sn}')">${st.learned?'✓ Learned':'Mark as learned'}</button>`+
    `<button class="fs-btn${st.flagged?' flagged':''}" onclick="badPhoto('${sn}')">${pl}</button>`;
}

function handleTap(){
  if(mode==='quiz'&&!answered) return;
  if(!revealed){
    revealed=true; showBack(deck[cur]);
  } else {
    if(cur<deck.length-1){ cur++; render(); }
  }
}

function go(d){ cur=Math.max(0,Math.min(deck.length-1,cur+d)); render(); }

function setMode(m){
  mode=m;
  document.getElementById('pill-learn').classList.toggle('active',m==='learn');
  document.getElementById('pill-quiz').classList.toggle('active',m==='quiz');
  document.getElementById('fs-quiz-stats').style.display=m==='quiz'?'flex':'none';
  if(m==='quiz'){sc=0;sw=0;['sc','sw'].forEach(id=>document.getElementById(id).textContent=0);}
  clrStatus(); initDeck(); render();
}

function renderOpts(c){
  // Quiz: show definition excerpt, pick the keyword name
  const pool=filteredCards().filter(x=>x.name!==c.name); shuffle(pool);
  const choices=[c,...pool.slice(0,3)]; shuffle(choices);
  const el=document.getElementById('fs-opts'); el.className='on';
  const sn=c.name.replace(/'/g,"\\'");
  el.innerHTML=choices.map(o=>{
    const on=o.name.replace(/'/g,"\\'");
    return `<button class="fs-opt" onclick="pick(this,'${on}','${sn}')">${o.name}</button>`;
  }).join('');
  // Show definition on front in quiz mode
  document.getElementById('fs-tap-hint').style.display='none';
  document.getElementById('fs-keyword-subtext').innerHTML=
    typeBadgeHTML(c.type)+
    `<div style="font-size:13px;color:rgba(255,255,255,.7);margin-top:8px;line-height:1.6;max-width:600px">${c.definition}</div>`;
}

function pick(btn,chosen,correct){
  if(answered)return; answered=true;
  const ok=chosen===correct;
  document.querySelectorAll('.fs-opt').forEach(b=>{
    b.disabled=true;
    if(b.textContent.trim()===correct) b.classList.add('correct');
    else if(b===btn&&!ok) b.classList.add('wrong');
  });
  if(ok){sc++;}else{sw++;}
  document.getElementById('sc').textContent=sc;
  document.getElementById('sw').textContent=sw;
  const qr=document.getElementById('fs-qres');
  qr.textContent=ok?`Correct!`:`Nope — it's "${correct}"`;
  qr.className='on '+(ok?'ok':'no');
  revealed=true;
  showBack(CARDS.find(c=>c.name===correct));
  setTimeout(()=>{ if(cur<deck.length-1){cur++;render();}else{qr.textContent=`Done! ${sc} correct of ${sc+sw}`;} },2200);
}

function toggleLearned(name){
  ST[name].learned=!ST[name].learned;
  saveState(); initDeck(); render();
}
function resetLearned(){
  CARDS.forEach(c=>{ ST[c.name].learned=false; });
  saveState(); initDeck();
  document.getElementById('fs-alldone').classList.remove('on');
  render();
}

// ── Bad photo ──────────────────────────────────────────────────────────────────
function badPhoto(name){
  const c=CARDS.find(x=>x.name===name), st=s(name);
  if(st.busy) return;
  const n=ic(c);
  if(n>1&&st.idx<n-1){
    st.idx++; st.flagged=true; saveState();
    setStatus(`Photo ${st.idx+1} of ${n}`,'ok',3000); render(); return;
  }
  st.busy=true; st.flagged=true;
  setStatus(`⏳ Fetching photo for "${name}"...`,'work');
  renderActions(c);
  fetchImage(c).then(r=>{
    st.busy=false;
    if(r==='ok')        setStatus(`✓ Photo loaded!`,'ok',5000);
    else if(r==='none') setStatus(`No image found for "${name}"`, 'err',5000);
    else                setStatus(`Network error`,'err',5000);
    saveState(); render();
  });
}

async function fetchImage(c){
  const capi='https://commons.wikimedia.org/w/api.php';
  const clean=c.name.replace(/\s*X$/,'').replace(/\s*\(.*?\)/g,'').trim();
  const terms=[`Star Wars Legion ${clean}`,`Star Wars ${clean}`,clean];
  const cands=[];
  for(const term of terms){
    try{
      const q=new URLSearchParams({action:'query',generator:'search',
        gsrnamespace:'6',gsrsearch:term,gsrlimit:'5',
        prop:'imageinfo',iiprop:'url|mime',iiurlwidth:'1200',format:'json',origin:'*'});
      const data=await (await fetch(`${capi}?${q}`)).json();
      if(data.query) Object.values(data.query.pages||{}).forEach(p=>{
        const inf=(p.imageinfo||[])[0];
        if(inf&&/\.(jpe?g|png)$/i.test(inf.url)) cands.push(inf.thumburl||inf.url);
      });
    }catch(e){}
    if(cands.length>=3) break;
  }
  const have=new Set(c.imgs||[]);
  const fresh=[...new Set(cands)].filter(u=>u&&!have.has(u));
  if(!fresh.length) return 'none';
  for(const url of fresh){
    try{
      const r=await fetch(url); if(!r.ok) continue;
      const blobUrl=URL.createObjectURL(await r.blob());
      if(!c.imgs) c.imgs=[];
      c.imgs.push(blobUrl); s(c.name).idx=c.imgs.length-1;
      return 'ok';
    }catch(e){}
  }
  return 'none';
}

// ── Catalog ────────────────────────────────────────────────────────────────────
let catFilter='all';
function setCF(v,btn){
  catFilter=v;
  document.querySelectorAll('#cat-filters .dark-pill').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active'); renderCatalog();
}
function renderCatalog(){
  let list=[...CARDS];
  if(catFilter==='learned')   list=list.filter(c=>s(c.name).learned);
  if(catFilter==='unlearned') list=list.filter(c=>!s(c.name).learned);
  if(catFilter==='unit')      list=list.filter(c=>c.type==='unit');
  if(catFilter==='weapon')    list=list.filter(c=>c.type==='weapon');
  if(catFilter==='concept')   list=list.filter(c=>c.type==='concept');
  document.getElementById('cat-count').textContent=`${list.length} keyword${list.length!==1?'s':''}`;
  const g=document.getElementById('cat-grid');
  if(!list.length){ g.innerHTML='<p class="empty-msg">Nothing here.</p>'; return; }
  g.innerHTML=list.map(c=>{
    const st=s(c.name), src=ci(c);
    const sn=c.name.replace(/'/g,"\\'");
    const th=src
      ?`<img class="cat-thumb" src="${src}" alt="${c.name}" loading="lazy"
             onerror="this.outerHTML='<div class=cat-thumb-ph>${c.name[0]}</div>'">`
      :`<div class="cat-thumb-ph">${c.name[0]}</div>`;
    return `<div class="cat-card${st.learned?' lrnd':''}" onclick="openMod('${sn}')">
      ${th}
      ${st.learned?'<span class="cat-badge badge-learned">✓</span>':''}
      <div class="cat-lbl">
        <div class="cat-name">${c.name}</div>
        <div class="cat-type">${c.type}</div>
      </div>
    </div>`;
  }).join('');
}

// ── Modal ──────────────────────────────────────────────────────────────────────
let mcard=null;
function openMod(name){
  mcard=CARDS.find(c=>c.name===name);
  renderMod(); document.getElementById('modal-bg').classList.add('on');
}
function renderMod(){
  const c=mcard, st=s(c.name), src=ci(c);
  document.getElementById('mod-img').innerHTML=src
    ?`<img class="modal-photo" src="${src}" alt="${c.name}"
           onerror="this.outerHTML='<div class=modal-photo-ph>No image — use Bad Photo to fetch one</div>'">`
    :`<div class="modal-photo-ph">No image — use the Bad Photo button to fetch one</div>`;
  document.getElementById('mod-name').textContent=c.name;
  document.getElementById('mod-type').innerHTML=typeBadgeHTML(c.type);
  document.getElementById('mod-def').textContent=c.definition;
  const ml=document.getElementById('mod-lrnd');
  ml.textContent=st.learned?'✓ Learned — reset':'Mark as learned';
  ml.className='modal-btn'+(st.learned?' lrnd':'');
  const mb=document.getElementById('mod-photo');
  mb.textContent=st.busy?'⌛':'📷 Bad photo — fetch one';
  mb.className='modal-btn'+(st.flagged?' flagd':'');
}
function modToggleLearned(){ toggleLearned(mcard.name); renderMod(); renderCatalog(); }
async function modBadPhoto(){
  const c=mcard, st=s(c.name);
  if(st.busy) return;
  st.busy=true; st.flagged=true;
  document.getElementById('mod-st').textContent='⌛ Fetching...';
  document.getElementById('mod-st').className='modal-status work';
  renderMod();
  const r=await fetchImage(c);
  st.busy=false;
  const el=document.getElementById('mod-st');
  if(r==='ok'){el.textContent='✓ Loaded!';el.className='modal-status ok';}
  else if(r==='none'){el.textContent='No image found';el.className='modal-status err';}
  else{el.textContent='Network error';el.className='modal-status err';}
  saveState(); renderMod(); renderCatalog();
}
function closeMod(e){
  if(e&&!e.target.classList.contains('modal-bg')&&e.target.id!=='modal-bg') return;
  document.getElementById('modal-bg').classList.remove('on'); mcard=null;
}

// ── Boot ───────────────────────────────────────────────────────────────────────
loadState();
setMode('learn');
</script>
</body>
</html>"""


def main():
    os.makedirs(IMGDIR, exist_ok=True)
    print("=" * 60)
    print("  SW Legion Flashcards Builder v1")
    print("=" * 60)

    # Step 1: Scrape keywords
    keywords = scrape_keywords()

    # Step 2: Download images
    print(f"\n  Downloading images for {len(keywords)} keywords...")
    print("  (skips any already in images/)\n")

    card_data = []
    failed    = []

    for i, kw in enumerate(keywords, 1):
        name = kw["name"]
        print(f"[{i:3d}/{len(keywords)}] {name[:40]:<40} ", end="", flush=True)
        img_path, existed = download_image(name, IMGDIR)
        if img_path:
            if existed:
                print("skip")
            else:
                kb = os.path.getsize(os.path.join(HERE, img_path)) // 1024
                print(f"OK  ({kb} KB)")
            time.sleep(0.4)
        else:
            print("no image")
            failed.append(name)

        card_data.append({
            "name":       name,
            "definition": kw["definition"],
            "type":       kw["type"],
            "imgs":       [img_path] if img_path else [],
            "credit":     "legionquickguide.com / Wikimedia Commons",
        })

    print()
    ok = len(keywords) - len(failed)
    if failed:
        print(f"  No image found for {len(failed)}: {', '.join(failed[:5])}{'...' if len(failed)>5 else ''}")
    print(f"  {ok}/{len(keywords)} keywords have images\n")

    # Step 3: Write HTML
    html = build_html(card_data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    kb = os.path.getsize(OUT) // 1024
    print(f"  swlegion_flashcards.html  ({kb} KB)")
    print(f"  images/                   ({ok} images)")
    print()
    print("  Open swlegion_flashcards.html in your browser.")
    print("  Keep the images/ folder in the same directory.")
    print("=" * 60)


if __name__ == "__main__":
    main()
