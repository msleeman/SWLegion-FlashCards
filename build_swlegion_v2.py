#!/usr/bin/env python3
"""
Star Wars Legion Flashcards Builder v2
========================================
Sources:
  - Keyword definitions: SWQ_Rulebook_2.6.0-1.pdf  (official AMG rules)
  - Card images:         legionhq2.com CDN  (d2maxvwz12z6fm.cloudfront.net)

Usage:
    py -m pip install requests pdfplumber
    py build_swlegion_v2.py

Place SWQ_Rulebook_2.6.0-1.pdf in the same folder or documents/ sub-folder.

Output:
    swlegion_flashcards.html
    images/   (one .webp per keyword - from LegionHQ card art)
"""

import os, re, json, time, sys
import requests

HERE    = os.path.dirname(os.path.abspath(__file__))
IMGDIR  = os.path.join(HERE, "images")
OUT     = os.path.join(HERE, "swlegion_flashcards.html")

CDN     = "https://d2maxvwz12z6fm.cloudfront.net"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ── Locate the PDF ─────────────────────────────────────────────────────────────
def find_pdf():
    candidates = [
        os.path.join(HERE, "SWQ_Rulebook_2.6.0-1.pdf"),
        os.path.join(HERE, "SWQ_Rulebook_2_6_0-1.pdf"),
        os.path.join(HERE, "documents", "SWQ_Rulebook_2.6.0-1.pdf"),
        os.path.join(HERE, "documents", "SWQ_Rulebook_2_6_0-1.pdf"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

# ── PDF keyword extraction ─────────────────────────────────────────────────────
def extract_keywords_from_pdf(pdf_path):
    try:
        import pdfplumber
    except ImportError:
        print("  ERROR: pdfplumber not installed. Run: py -m pip install pdfplumber")
        return {}

    print(f"  Reading: {os.path.basename(pdf_path)}")
    keywords = {}

    NOISE = re.compile(r'^(\d{1,3}|RULEBOOK|LEGION|LEGIONRULEBOOK|[•*—©])$', re.IGNORECASE)

    def clean(s):
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s or '')
        return re.sub(r'\s+', ' ', s).strip()

    def fix_spaced(name):
        tokens = name.split()
        singles = sum(1 for t in tokens if len(t) == 1 and t.isalpha())
        if singles > len(tokens) * 0.5:
            name = ''.join(tokens)
        return name

    def title_kw(n):
        return ' '.join(
            w if w in ('X', 'LOS') or w.isdigit() else w.capitalize()
            for w in n.split()
        )

    def get_type(s):
        su = s.upper()
        if 'WEAPON' in su: return 'weapon'
        if 'COMMAND' in su or 'UPGRADE' in su: return 'upgrade'
        return 'unit'

    KW_INLINE = re.compile(
        r'^(.{3,60}?)\s*\(([^)]*(?:KEYWORD|KEYWO\s*RD)[^)]*)\)\s*$',
        re.IGNORECASE)
    KW_TYPE = re.compile(
        r'^\(([^)]*(?:KEYWORD|KEYWO\s*RD)[^)]*)\)$',
        re.IGNORECASE)
    KW_NAME = re.compile(r'^[A-Z][A-Z0-9\s\-\':\/\.]{2,59}$')
    SKIP = {'WEAPON KEYWORDS', 'UNIT KEYWORDS', 'UPGRADE AND', 'COMMAND CARD',
            'KEYWORDS', 'KEYWORD GLOSSARY', 'LINE OF SIGHT', 'SILHOUETTE TEMPLATES',
            'RULEBOOK', 'LEGION', 'LEGIONRULEBOOK'}

    current_name = current_type = None
    current_def = []

    def flush():
        nonlocal current_name, current_type, current_def
        if not current_name: return
        defn = clean(' '.join(current_def))
        if len(defn) > 20:
            name = title_kw(fix_spaced(current_name))
            keywords[name] = {'name': name, 'type': current_type or 'unit', 'definition': defn}
        current_name = current_type = None
        current_def = []

    with pdfplumber.open(pdf_path) as pdf:
        for pg_idx in range(44, min(61, len(pdf.pages))):
            page = pdf.pages[pg_idx]
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            if not words: continue
            mid = page.width * 0.50

            def col_lines(wlist):
                if not wlist: return []
                rows = {}
                for w in wlist:
                    y = round(w['top'] / 4) * 4
                    rows.setdefault(y, []).append(w)
                return [' '.join(w['text'] for w in sorted(rows[y], key=lambda w: w['x0']))
                        for y in sorted(rows)]

            for col_words in ([w for w in words if w['x0'] < mid],
                               [w for w in words if w['x0'] >= mid]):
                pending = None
                for line in col_lines(col_words):
                    line = clean(line)
                    if not line or NOISE.match(line): continue
                    m = KW_INLINE.match(line)
                    if m:
                        flush()
                        current_name = m.group(1).strip()
                        current_type = get_type(m.group(2))
                        current_def = []
                        pending = None
                        continue
                    if KW_TYPE.match(line):
                        if pending:
                            flush()
                            current_name = pending
                            current_type = get_type(line)
                            current_def = []
                        pending = None
                        continue
                    if KW_NAME.match(line) and len(line) < 65 and line.upper() not in SKIP:
                        pending = line
                        continue
                    if current_name:
                        current_def.append(line)
                    pending = None
    flush()

    print(f"  Extracted {len(keywords)} keywords from PDF")
    return keywords

# ── Keyword -> card image mapping ──────────────────────────────────────────────
# (cdn_card_name, faction)  — Empire first, then rebels, republic, separatist, mercenary
KEYWORD_CARDS = {
    "Deflect":              [("Darth Vader Dark Lord of the Sith","empire")],
    "Relentless":           [("Darth Vader Dark Lord of the Sith","empire")],
    "Master Of The Force":  [("Darth Vader Dark Lord of the Sith","empire")],
    "Immune: Pierce":       [("Darth Vader Dark Lord of the Sith","empire")],
    "Compel":               [("Darth Vader Dark Lord of the Sith","empire"),("Director Orson Krennic","empire")],
    "Entourage: Unit Name": [("Director Orson Krennic","empire")],
    "Cunning":              [("Director Orson Krennic","empire")],
    "Sharpshooter X":       [("Director Orson Krennic","empire"),("Scout Troopers","empire")],
    "Disciplined X":        [("Imperial Death Troopers","empire")],
    "Precise X":            [("Imperial Death Troopers","empire")],
    "Ready X":              [("Imperial Death Troopers","empire")],
    "Steady":               [("Snowtroopers","empire")],
    "Armor X":              [("AT-ST","empire")],
    "Tenacity":             [("Dewback Rider","empire"),("Bossk","mercenary")],
    "Weak Point X: Front/Rear/Sides": [("AT-ST","empire")],
    "Immune: Blast":        [("AT-ST","empire")],
    "Cumbersome":           [("AT-ST","empire"),("Dewback Rider","empire")],
    "Full Pivot":           [("E-Web Heavy Blaster Team","empire")],
    "Stationary":           [("E-Web Heavy Blaster Team","empire")],
    "Speeder X":            [("74-Z Speeder Bikes","empire")],
    "Charge":               [("Imperial Royal Guards","empire"),("Wookiee Warriors","rebels")],
    "Dauntless":            [("Imperial Royal Guards","empire"),("Wookiee Warriors","rebels")],
    "Guardian X":           [("Imperial Royal Guards","empire"),("Phase II Clone Troopers","republic")],
    "Barrage":              [("Imperial Death Troopers","empire"),("Clone Captain Rex","republic")],
    "Arsenal X":            [("Wookiee Warriors","rebels"),("B2 Super Battle Droids","separatist")],
    "Fire Support":         [("DF-90 Mortar Trooper","empire")],
    "Target X":             [("General Veers","empire")],
    "Defend X":             [("Emperor Palpatine","empire")],
    "Exemplar":             [("Stormtroopers","empire"),("Phase II Clone Troopers","republic")],
    "Retinue: Unit/Unit Type": [("Imperial Death Troopers","empire")],
    "Coordinate: Unit Name/Unit Type": [("Imperial Shoretroopers","empire")],
    "Direct: Unit Name/Unit Type": [("Grand Moff Tarkin","empire"),("Mon Mothma","rebels")],
    "Bolster X":            [("Grand Moff Tarkin","empire"),("Admiral Ackbar","rebels")],
    "Demoralize X":         [("Grand Moff Tarkin","empire")],
    "Marksman":             [("Scout Troopers Strike Team","empire"),("Jyn Erso","rebels")],
    "Sentinel":             [("E-Web Heavy Blaster Team","empire")],
    "Smoke X":              [("Imperial Shoretroopers","empire"),("Rebel Pathfinders","rebels")],
    "Scout X":              [("Scout Troopers","empire"),("Rebel Commandos","rebels")],
    "Infiltrate":           [("Scout Troopers","empire"),("Rebel Commandos","rebels")],
    "Low Profile":          [("Stormtroopers","empire"),("Rebel Troopers","rebels")],
    "Unhindered":           [("AT-ST","empire"),("AT-RT","rebels")],
    "Agile X":              [("74-Z Speeder Bikes","empire")],
    "Nimble":               [("74-Z Speeder Bikes","empire")],
    "Outmaneuver":          [("74-Z Speeder Bikes","empire"),("Scout Troopers","empire")],
    "Reposition":           [("74-Z Speeder Bikes","empire"),("Jyn Erso","rebels")],
    "Hover: Ground/Air X":  [("LAAT/le Patrol Transport","empire"),("T-47 Airspeeder","rebels")],
    "Transport":            [("LAAT/le Patrol Transport","empire")],
    "Attack Run":           [("T-47 Airspeeder","rebels")],
    "Plodding":             [("TX-225 GAVw Occupier Combat Assault Tank","empire")],
    "Generator X":          [("TX-225 GAVw Occupier Combat Assault Tank","empire")],
    "Climbing Vehicle":     [("AT-RT","rebels")],
    "Scale":                [("AT-RT","rebels"),("Wookiee Warriors","rebels")],
    "Expert Climber":       [("Wookiee Warriors","rebels")],
    "Enrage X":             [("Wookiee Warriors","rebels"),("Bossk","mercenary")],
    "Block":                [("Chewbacca","rebels"),("Wookiee Warriors","rebels")],
    "Bounty":               [("Bossk","mercenary"),("Boba Fett","mercenary")],
    "Mercenary":            [("Bossk","mercenary"),("Boba Fett","mercenary")],
    "Gunslinger":           [("Boba Fett","mercenary"),("Han Solo","rebels")],
    "Jump X":               [("Imperial Royal Guards","empire"),("Rebel Commandos","rebels")],
    "Flawed":               [("Darth Vader Operative","empire")],
    "Unstoppable":          [("Wookiee Warriors","rebels")],
    "Uncanny Luck X":       [("Han Solo","rebels")],
    "Unconcerned":          [("Probe Droid","empire")],
    "Heavy Weapon Team":    [("E-Web Heavy Blaster Team","empire")],
    "Detachment: Unit Name/Type": [("DF-90 Mortar Trooper","empire")],
    "Field Commander":      [("Imperial Officer","empire"),("Rebel Officer","rebels")],
    "Covert Ops":           [("Scout Troopers Strike Team","empire"),("Rebel Commandos Strike Team","rebels")],
    "Secret Mission":       [("Rebel Commandos","rebels"),("Scout Troopers","empire")],
    "Scouting Party X":     [("Scout Troopers","empire"),("Rebel Commandos","rebels")],
    "Danger Sense X":       [("Luke Skywalker Commander","rebels")],
    "Complete The Mission": [("Rebel Commandos","rebels")],
    "Death From Above":     [("Imperial Jumptroopers","empire"),("Rebel Pathfinders","rebels")],
    "Distract":             [("Han Solo","rebels"),("Sabine Wren","rebels")],
    "Observe X":            [("Scout Troopers","empire"),("Rebel Pathfinders","rebels")],
    "Override":             [("R2-D2 and C-3PO","rebels")],
    "Calculate Odds":       [("R2-D2 and C-3PO","rebels")],
    "Divine Influence":     [("R2-D2 and C-3PO","rebels")],
    "Teamwork: Unit Name":  [("Han Solo","rebels"),("Chewbacca","rebels")],
    "Guidance":             [("Admiral Ackbar","rebels")],
    "Ruthless":             [("Director Orson Krennic","empire")],
    "Interrogate":          [("Emperor Palpatine","empire")],
    "Duelist":              [("General Grievous","separatist"),("Count Dooku","separatist")],
    "Jedi Hunter":          [("General Grievous","separatist")],
    "AI: Action":           [("B1 Battle Droids","separatist")],
    "Shielded X":           [("Droidekas","separatist")],
    "Wheel Mode":           [("Droidekas","separatist")],
    "Immune: Melee Pierce": [("B2 Super Battle Droids","separatist")],
    "Self-Preservation":    [("B1 Battle Droids","separatist"),("Rebel Troopers","rebels")],
    "Self-Destruct X":      [("B1 Battle Droids","separatist")],
    "Independent: Token X": [("B1 Battle Droids","separatist")],
    "Counterpart":          [("Darth Vader Dark Lord of the Sith","empire")],
    "Aid: Affiliation":     [("Rebel Commandos","rebels")],
    "Allies of Convenience":[("Boba Fett","mercenary")],
    "Advanced Targeting: Unit Type X": [("General Grievous","separatist")],
    "Soresu Mastery":       [("Obi-Wan Kenobi","republic")],
    "Ataru Mastery":        [("Ahsoka Tano","rebels")],
    "Makashi Mastery":      [("Count Dooku","separatist")],
    "Djem So Mastery":      [("Darth Vader Dark Lord of the Sith","empire")],
    "Jar'kai Mastery":      [("Ahsoka Tano Fulcrum","rebels")],
    "Juyo Mastery":         [("Darth Maul","mercenary")],
    "Impervious":           [("Darth Vader Dark Lord of the Sith","empire")],
    "Latent Power":         [("Darth Vader Dark Lord of the Sith","empire")],
    "Loadout":              [("Stormtroopers","empire"),("Rebel Troopers","rebels")],
    "Equip":                [("Imperial Specialists","empire")],
    "Flexible Response X":  [("Rebel Troopers","rebels")],
    "Associate: Unit Name": [("DF-90 Mortar Trooper","empire")],
    "Immune: Enemy Effects":[("Darth Vader Dark Lord of the Sith","empire")],
    "Immune: Melee":        [("E-Web Heavy Blaster Team","empire")],
    "Immune: Range 1 Weapons": [("T-47 Airspeeder","rebels")],
    "Immune: Deflect":      [("Director Orson Krennic","empire")],
    "We're Not Regs":       [("ARC Troopers","republic")],
    "Wound X":              [("B2 Super Battle Droids","separatist")],
    "Tempted":              [("Luke Skywalker Son of Skywalker","rebels")],
    "Weighed Down":         [("Rebel Troopers","rebels")],
    "Indomitable":          [("AT-ST","empire")],
    "Incognito":            [("Rebel Commandos","rebels")],
    "Inconspicuous":        [("Scout Troopers","empire"),("Rebel Commandos","rebels")],
    "Hunted":               [("Rebel Commandos","rebels")],
    "Disengage":            [("Scout Troopers","empire"),("Rebel Commandos","rebels")],
    "Take Cover X":         [("Han Solo","rebels"),("Rebel Troopers","rebels")],
    "Cache":                [("Rebel Specialists","rebels")],
    "Master Storyteller":   [("Saw Gerrera","rebels")],
    "Cover X":              [("Stormtroopers","empire"),("Rebel Troopers","rebels")],
    "Special Issue":        [("Imperial Specialists","empire")],
    "Poison":               [("Wookiee Warriors","rebels")],
    "Blast":                [("TX-225 GAVw Occupier Combat Assault Tank","empire")],
    "Critical X":           [("Imperial Death Troopers","empire")],
    "High Velocity":        [("Imperial Death Troopers","empire")],
    "Impact X":             [("AT-RT","rebels"),("Phase II Clone Troopers","republic")],
    "Ion X":                [("Snowtroopers","empire")],
    "Suppressive":          [("E-Web Heavy Blaster Team","empire")],
    "Pierce X":             [("Darth Vader Dark Lord of the Sith","empire"),("Luke Skywalker Son of Skywalker","rebels")],
    "Scatter":              [("T-47 Airspeeder","rebels")],
    "Spray":                [("AT-RT","rebels")],
    "Poison X":             [("Wookiee Warriors","rebels")],
    "Primitive":            [("Ewoks","rebels"),("Wookiee Warriors","rebels")],
    "Ram X":                [("TX-225 GAVw Occupier Combat Assault Tank","empire")],
    "Overrun X":            [("TX-225 GAVw Occupier Combat Assault Tank","empire")],
    "Beam X":               [("Director Orson Krennic","empire")],
    "Arm X: Charge Token":  [("Rebel Pathfinders","rebels"),("Sabine Wren","rebels")],
    "Fixed: Front/Rear":    [("AT-ST","empire")],
    "Immobilize X":         [("Snowtroopers","empire")],
    "Lethal X":             [("Imperial Death Troopers","empire")],
    "Long Shot":            [("Scout Troopers Strike Team","empire")],
    "Tow Cable":            [("T-47 Airspeeder","rebels")],
    "Versatile":            [("BX-series Droid Commandos","separatist"),("Clone Captain Rex","republic")],
    "Detonate X: (Charge Type)": [("Rebel Pathfinders","rebels"),("Sabine Wren","rebels")],
    "Divulge":              [("Darth Vader Dark Lord of the Sith","empire")],
    "Cycle":                [("Imperial Specialists","empire"),("Rebel Specialists","rebels")],
    "Self-preservation":    [("B1 Battle Droids","separatist")],
    "Self-destruct X":      [("B1 Battle Droids","separatist")],
}

def safe_fn(name):
    return re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:55] + ".webp"

def cdn_url(card_name):
    from urllib.parse import quote
    return f"{CDN}/unitCards/{quote(card_name)}.webp"

def download_image(kw_name, imgdir):
    fname = safe_fn(kw_name)
    fpath = os.path.join(imgdir, fname)
    if os.path.exists(fpath) and os.path.getsize(fpath) > 5000:
        return f"images/{fname}", "cached"
    cards = KEYWORD_CARDS.get(kw_name, [])
    if not cards:
        return None, "no mapping"
    for card_name, _ in cards:
        url = cdn_url(card_name)
        try:
            r = requests.get(url, headers=HEADERS, timeout=14, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 5000:
                with open(fpath, "wb") as f:
                    f.write(r.content)
                return f"images/{fname}", f"{len(r.content)//1024}KB ({card_name})"
        except Exception:
            pass
        time.sleep(0.2)
    return None, "all CDN attempts failed"

# ── HTML template ──────────────────────────────────────────────────────────────
HTML_TMPL = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SW Legion Keywords</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --gold:#f5c518;--golddim:rgba(245,197,24,.2);--goldglow:rgba(245,197,24,.4);
  --G:#1D9E75;--Gbg:rgba(29,158,117,.2);--Gt:#6effc4;
  --R:#ff4444;--Rbg:rgba(255,68,68,.2);--Rt:#ffaaaa;
  --A:#f5a623;--Abg:rgba(245,166,35,.2);--At:#ffe0a0;
  --glass:rgba(0,0,0,.65);--white:rgba(255,255,255,.95);
  --white2:rgba(255,255,255,.6);--white3:rgba(255,255,255,.3);
  --rs:10px;--rb:16px;
}
html,body{width:100%;height:100%;overflow:hidden;background:#000;
  font-family:"Segoe UI",-apple-system,BlinkMacSystemFont,sans-serif}
.screen{position:fixed;inset:0;display:none}.screen.on{display:block}

/* Flashcard */
#fs-bg{position:absolute;inset:0;overflow:hidden;background:#060810}
#fs-img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;
  opacity:.35;transition:opacity .5s;filter:saturate(.7)}
#fs-img.revealed{opacity:.55;filter:saturate(1)}
#fs-scan{position:absolute;inset:0;pointer-events:none;z-index:1;
  background:repeating-linear-gradient(0deg,transparent,transparent 3px,rgba(0,0,0,.06) 3px,rgba(0,0,0,.06) 6px)}
#fs-top-grad{position:absolute;top:0;left:0;right:0;height:220px;z-index:2;
  background:linear-gradient(rgba(0,0,0,.9),transparent);pointer-events:none}
#fs-bot-grad{position:absolute;bottom:0;left:0;right:0;height:65%;z-index:2;
  background:linear-gradient(transparent,rgba(0,0,0,.97));pointer-events:none}
#fs-flip-zone{position:absolute;inset:0;cursor:pointer;z-index:3}
#fs-topbar{position:absolute;top:0;left:0;right:0;padding:14px 16px;
  display:flex;align-items:center;gap:8px;z-index:10;pointer-events:none}
#fs-topbar>*{pointer-events:all}
.pill{background:rgba(0,0,0,.7);backdrop-filter:blur(16px);
  border:1px solid rgba(245,197,24,.2);border-radius:20px;
  color:var(--white2);font-size:13px;padding:6px 14px;cursor:pointer;
  font-family:inherit;transition:all .2s}
.pill.active{background:var(--golddim);border-color:var(--gold);color:var(--gold)}
.pill:hover:not(.active){background:rgba(255,255,255,.08)}
#fs-prog{flex:1;height:2px;background:rgba(255,255,255,.12);border-radius:2px;margin:0 4px}
#fs-pfill{height:100%;background:var(--gold);border-radius:2px;transition:width .3s}
#fs-ctr{color:var(--white3);font-size:12px;white-space:nowrap}
#fs-qstats{display:none;gap:8px}
.qstat{font-size:13px;color:var(--white2)}.qstat span{font-weight:700}
.qok span{color:var(--Gt)}.qwr span{color:var(--Rt)}
#fs-prev,#fs-next{position:absolute;top:50%;transform:translateY(-50%);z-index:10;
  width:44px;height:44px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;cursor:pointer;font-size:18px;transition:all .2s;
  background:rgba(0,0,0,.5);backdrop-filter:blur(12px);
  border:1px solid var(--golddim);color:var(--gold)}
#fs-prev{left:12px}#fs-next{right:12px}
#fs-prev:hover,#fs-next:hover{background:var(--golddim)}
#fs-prev:disabled,#fs-next:disabled{opacity:.15;cursor:default}
#fs-topright{position:absolute;top:14px;right:16px;z-index:10;display:flex;gap:8px}
.tc{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.6px;
  padding:3px 10px;border-radius:12px;text-transform:uppercase;margin-bottom:10px}
.tc-unit   {background:rgba(52,152,219,.25);border:1px solid #3498db;color:#7ec8f5}
.tc-weapon {background:rgba(231,76,60,.25);border:1px solid #e74c3c;color:#f08080}
.tc-upgrade{background:rgba(155,89,182,.25);border:1px solid #9b59b6;color:#d7b4f5}
#fs-front{position:absolute;bottom:0;left:0;right:0;padding:0 24px 28px;z-index:10}
#fs-kw-name{font-size:clamp(30px,8vw,72px);font-weight:900;color:var(--gold);
  line-height:1.1;letter-spacing:-1px;
  text-shadow:0 0 40px var(--goldglow),0 2px 12px rgba(0,0,0,.9)}
#fs-tap-hint{font-size:13px;color:rgba(255,255,255,.3);margin-top:14px}
#fs-back{position:absolute;bottom:0;left:0;right:0;padding:0 24px 24px;z-index:10;display:none}
#fs-back-name{font-size:17px;font-weight:700;color:var(--gold);margin-bottom:6px}
.def-box{background:rgba(0,0,0,.7);backdrop-filter:blur(16px);
  border:1px solid rgba(245,197,24,.15);border-radius:var(--rs);padding:12px 16px;margin-bottom:8px}
.def-label{font-size:10px;font-weight:700;letter-spacing:.8px;
  color:rgba(255,255,255,.3);text-transform:uppercase;margin-bottom:6px}
.def-text{font-size:14px;color:var(--white);line-height:1.65}
.src-text{font-size:11px;color:var(--white3);margin-top:3px;font-style:italic}
#fs-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.act-btn{background:rgba(0,0,0,.6);backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,.15);border-radius:var(--rs);
  color:var(--white2);font-size:13px;padding:8px 16px;cursor:pointer;
  font-family:inherit;transition:all .2s}
.act-btn:hover{background:rgba(255,255,255,.1);color:var(--white)}
.act-btn.learned{background:var(--Gbg);border-color:var(--G);color:var(--Gt)}
#fs-status{max-height:0;overflow:hidden;text-align:center;font-size:13px;
  font-weight:500;border-radius:var(--rs);transition:all .3s;margin-bottom:0}
#fs-status.show{max-height:44px;padding:9px 14px;margin-bottom:8px}
#fs-status.ok{background:var(--Gbg);color:var(--Gt);border:1px solid rgba(29,158,117,.3)}
#fs-status.err{background:var(--Rbg);color:var(--Rt);border:1px solid rgba(255,68,68,.3)}
#fs-opts{display:none;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
#fs-opts.on{display:grid}
.qopt{background:rgba(0,0,0,.65);backdrop-filter:blur(12px);
  border:1px solid var(--golddim);border-radius:var(--rs);
  color:var(--white);font-size:13px;padding:12px 10px;cursor:pointer;
  font-family:inherit;transition:all .15s;text-align:center;line-height:1.3}
.qopt:hover:not(:disabled){background:var(--golddim)}
.qopt.correct{background:var(--Gbg);border-color:var(--G);color:var(--Gt);font-weight:700}
.qopt.wrong{background:var(--Rbg);border-color:var(--R);color:var(--Rt)}
#fs-qres{display:none;text-align:center;padding:10px 14px;font-size:14px;
  font-weight:600;border-radius:var(--rs);margin-bottom:8px;backdrop-filter:blur(12px)}
#fs-qres.on{display:block}
#fs-qres.ok{background:var(--Gbg);color:var(--Gt);border:1px solid rgba(29,158,117,.3)}
#fs-qres.no{background:var(--Rbg);color:var(--Rt);border:1px solid rgba(255,68,68,.3)}
#fs-alldone{position:absolute;inset:0;display:none;z-index:20;
  background:rgba(0,0,0,.9);backdrop-filter:blur(24px);
  align-items:center;justify-content:center;flex-direction:column;
  gap:20px;text-align:center;padding:2rem}
#fs-alldone.on{display:flex}
#fs-alldone h2{font-size:30px;font-weight:900;color:var(--gold);text-shadow:0 0 40px var(--goldglow)}
#fs-alldone p{color:var(--white2);font-size:15px;max-width:360px;line-height:1.6}
.big-btn{border:none;border-radius:var(--rb);font-size:15px;font-weight:700;
  padding:13px 32px;cursor:pointer;font-family:inherit;transition:all .2s}
.big-btn.gold{background:var(--gold);color:#000}
.big-btn.ghost{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.2);color:var(--white2)}

/* Catalog */
#catalog-screen{background:#060810;overflow-y:auto}
.cat-wrap{max-width:960px;margin:0 auto;padding:20px}
.cat-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:12px}
.cat-top h1{font-size:20px;font-weight:800;color:var(--gold);text-shadow:0 0 24px var(--goldglow)}
.dpill{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);
  border-radius:20px;color:var(--white2);font-size:13px;padding:6px 14px;
  cursor:pointer;font-family:inherit;transition:all .2s}
.dpill:hover{background:rgba(255,255,255,.1)}
.dpill.active{background:var(--golddim);border-color:var(--gold);color:var(--gold)}
.cat-filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.cat-count{font-size:12px;color:var(--white3);margin-bottom:12px}
.cat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
.cat-card{border-radius:var(--rs);overflow:hidden;
  background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);
  cursor:pointer;transition:transform .15s,box-shadow .15s,border-color .2s;position:relative}
.cat-card:hover{transform:translateY(-3px);box-shadow:0 8px 28px rgba(0,0,0,.6);border-color:var(--golddim)}
.cat-card.lrnd{border:2px solid rgba(29,158,117,.5)}
.cat-thumb{width:100%;height:100px;object-fit:cover;display:block;
  background:#0a1020;opacity:.65;filter:saturate(.7)}
.cat-thumb-ph{width:100%;height:100px;background:linear-gradient(135deg,#0a0d1a,#1a1a2e);
  display:flex;align-items:center;justify-content:center;font-size:22px;color:rgba(245,197,24,.2)}
.cat-lbl{padding:8px 10px}
.cat-name{font-size:12px;font-weight:600;color:var(--white);line-height:1.3}
.cat-type{font-size:10px;color:var(--white3);margin-top:2px}
.cat-badge{position:absolute;top:6px;right:6px;font-size:10px;font-weight:700;
  padding:2px 7px;border-radius:10px;background:var(--G);color:#fff}
.empty-cat{color:var(--white3);font-size:14px;grid-column:1/-1;padding:3rem 0;text-align:center}

/* Modal */
#modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);
  z-index:100;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(12px)}
#modal-bg.on{display:flex}
.modal-box{background:#0a0d1a;border:1px solid var(--golddim);border-radius:var(--rb);
  max-width:560px;width:100%;overflow:hidden;max-height:90vh;overflow-y:auto;
  box-shadow:0 0 60px rgba(245,197,24,.08)}
.modal-photo{width:100%;height:200px;object-fit:cover;display:block;background:#0a1020;opacity:.6}
.modal-photo-ph{width:100%;height:200px;background:linear-gradient(135deg,#0a0d1a,#1a1a2e);
  display:flex;align-items:center;justify-content:center;font-size:40px;color:rgba(245,197,24,.15)}
.modal-body{padding:1.25rem}
.modal-name{font-size:20px;font-weight:800;color:var(--gold)}
.modal-def{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);
  border-radius:var(--rs);padding:12px 14px;margin-top:10px;
  font-size:13px;color:rgba(255,255,255,.75);line-height:1.7}
.modal-src{font-size:11px;color:var(--white3);margin-top:6px;font-style:italic}
.modal-acts{display:flex;gap:8px;margin-top:1rem;flex-wrap:wrap}
.mbtn{padding:9px 18px;border-radius:var(--rs);background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.1);cursor:pointer;font-size:13px;
  font-family:inherit;color:var(--white2);transition:all .15s}
.mbtn:hover{background:rgba(255,255,255,.1)}
.mbtn.lrnd{background:var(--Gbg);border-color:var(--G);color:var(--Gt);font-weight:600}
.mbtn.cls{margin-left:auto;background:rgba(255,255,255,.03)}
@media(max-width:520px){#fs-kw-name{font-size:24px}#fs-opts{grid-template-columns:1fr}}
</style>
</head>
<body>

<div class="screen on" id="flashcard-screen">
  <div id="fs-bg">
    <img id="fs-img" alt="" style="display:none">
    <div id="fs-scan"></div>
    <div id="fs-top-grad"></div>
    <div id="fs-bot-grad"></div>
  </div>
  <div id="fs-flip-zone" onclick="handleTap()"></div>
  <div id="fs-topbar">
    <button class="pill active" id="pill-learn" onclick="setMode('learn')">Learn</button>
    <button class="pill" id="pill-quiz" onclick="setMode('quiz')">Quiz</button>
    <button class="pill active" id="pill-all" onclick="setTF('all')">All</button>
    <button class="pill" id="pill-unit" onclick="setTF('unit')">Unit</button>
    <button class="pill" id="pill-weapon" onclick="setTF('weapon')">Weapon</button>
    <div id="fs-prog"><div id="fs-pfill" style="width:0%"></div></div>
    <span id="fs-ctr"></span>
    <div id="fs-qstats">
      <div class="qstat qok">✓<span id="sc">0</span></div>
      <div class="qstat qwr">✗<span id="sw">0</span></div>
    </div>
  </div>
  <div id="fs-topright">
    <button class="pill" onclick="showScreen('catalog-screen')">Catalog</button>
  </div>
  <button id="fs-prev" onclick="go(-1)">&#8592;</button>
  <button id="fs-next" onclick="go(1)">&#8594;</button>
  <div id="fs-front">
    <div id="fs-status"></div>
    <div id="fs-qres"></div>
    <div id="fs-opts"></div>
    <div id="fs-type-chip"></div>
    <div id="fs-kw-name"></div>
    <div id="fs-tap-hint">Tap anywhere to reveal definition</div>
  </div>
  <div id="fs-back">
    <div id="fs-back-name"></div>
    <div class="def-box">
      <div class="def-label">Rules Text — Core Rulebook v2.6</div>
      <div class="def-text" id="fs-def"></div>
    </div>
    <div class="src-text" id="fs-card-src"></div>
    <div id="fs-actions"></div>
  </div>
  <div id="fs-alldone">
    <div style="font-size:56px">⚡</div>
    <h2>Deck Complete!</h2>
    <p>All keywords in this filter are learned. Reset or change filter to continue.</p>
    <button class="big-btn gold" onclick="resetLearned()">Start Over</button>
    <button class="big-btn ghost" onclick="showScreen('catalog-screen')">Catalog</button>
  </div>
</div>

<div class="screen" id="catalog-screen" style="background:#060810;overflow-y:auto">
  <div class="cat-wrap">
    <div class="cat-top">
      <h1>⚡ SW Legion Keywords v2</h1>
      <button class="dpill" onclick="showScreen('flashcard-screen')">← Study</button>
    </div>
    <div class="cat-filters" id="cat-filters">
      <button class="dpill active" onclick="setCF('all',this)">All</button>
      <button class="dpill" onclick="setCF('learned',this)">Learned</button>
      <button class="dpill" onclick="setCF('unlearned',this)">Unlearned</button>
      <button class="dpill" onclick="setCF('unit',this)">Unit Keywords</button>
      <button class="dpill" onclick="setCF('weapon',this)">Weapon Keywords</button>
      <button class="dpill" onclick="setCF('upgrade',this)">Upgrade/Command</button>
    </div>
    <div class="cat-count" id="cat-count"></div>
    <div class="cat-grid" id="cat-grid"></div>
  </div>
</div>

<div id="modal-bg" onclick="closeMod(event)">
  <div class="modal-box" onclick="event.stopPropagation()">
    <div id="mod-img"></div>
    <div class="modal-body">
      <div class="modal-name" id="mod-name"></div>
      <div class="modal-def"  id="mod-def"></div>
      <div class="modal-src"  id="mod-src"></div>
      <div class="modal-acts">
        <button class="mbtn" id="mod-lrnd" onclick="modToggleLearned()"></button>
        <button class="mbtn cls" onclick="closeMod()">Close</button>
      </div>
    </div>
  </div>
</div>

<script>
const CARDS = /*CARD_JSON*/;
const ST = {};
CARDS.forEach(c=>{ST[c.name]={learned:false};});

function loadState(){
  try{
    const d=JSON.parse(localStorage.getItem('swlegion_v2')||'{}');
    Object.keys(d).forEach(n=>{if(ST[n])Object.assign(ST[n],d[n]);});
  }catch(e){}
}
function saveState(){
  const o={};
  Object.keys(ST).forEach(n=>{o[n]={learned:ST[n].learned};});
  localStorage.setItem('swlegion_v2',JSON.stringify(o));
}
function ci(c){return(c.imgs&&c.imgs[0])||'';}
function s(n){return ST[n]||{learned:false};}
let _st=null;
function setStatus(msg,cls,ms){
  const el=document.getElementById('fs-status');
  el.textContent=msg;el.className='show '+(cls||'ok');
  clearTimeout(_st);if(ms)_st=setTimeout(()=>{el.textContent='';el.className='';},ms);
}
function showScreen(id){
  document.querySelectorAll('.screen').forEach(el=>el.classList.remove('on'));
  document.getElementById(id).classList.add('on');
  if(id==='catalog-screen')renderCatalog();
}
const TC={unit:'tc-unit',weapon:'tc-weapon',upgrade:'tc-upgrade'};
const TL={unit:'Unit Keyword',weapon:'Weapon Keyword',upgrade:'Upgrade/Command'};
function typeChip(t){return`<span class="tc ${TC[t]||'tc-unit'}">${TL[t]||t}</span>`;}

let deck=[],cur=0,mode='learn',revealed=false,answered=false,sc=0,sw=0,typeFilter='all';

function setTF(t){
  typeFilter=(typeFilter===t&&t!=='all')?'all':t;
  ['all','unit','weapon'].forEach(x=>
    document.getElementById('pill-'+x).classList.toggle('active',typeFilter===x));
  initDeck();render();
}
function filteredCards(){
  if(typeFilter==='all')return CARDS;
  return CARDS.filter(c=>c.type===typeFilter);
}
function activeDeck(){return filteredCards().filter(c=>!s(c.name).learned);}
function shuffle(a){for(let i=a.length-1;i>0;i--){const j=0|Math.random()*(i+1);[a[i],a[j]]=[a[j],a[i]];}}
function initDeck(){deck=[...activeDeck()];shuffle(deck);cur=0;}

function render(){
  const alive=activeDeck();
  document.getElementById('fs-alldone').classList.toggle('on',!alive.length);
  if(!alive.length)return;
  while(deck[cur]&&s(deck[cur].name).learned&&cur<deck.length)cur++;
  if(!deck[cur]||s(deck[cur].name).learned)initDeck();
  const c=deck[cur];
  revealed=false;answered=false;
  document.getElementById('fs-qres').className='';
  document.getElementById('fs-qres').textContent='';
  document.getElementById('fs-opts').className='';
  document.getElementById('fs-pfill').style.width=Math.round(((cur+1)/deck.length)*100)+'%';
  document.getElementById('fs-ctr').textContent=(cur+1)+'/'+deck.length;
  document.getElementById('fs-prev').disabled=cur===0;
  document.getElementById('fs-next').disabled=cur===deck.length-1;
  const img=document.getElementById('fs-img');
  const src=ci(c);
  if(src){img.src=src;img.style.display='block';img.classList.remove('revealed');
          img.onerror=()=>img.style.display='none';}
  else{img.style.display='none';}
  showFront(c);renderActions(c);
}

function showFront(c){
  document.getElementById('fs-front').style.display='block';
  document.getElementById('fs-back').style.display='none';
  document.getElementById('fs-img').classList.remove('revealed');
  document.getElementById('fs-type-chip').innerHTML=typeChip(c.type);
  document.getElementById('fs-kw-name').textContent=c.name;
  document.getElementById('fs-tap-hint').style.display=mode==='learn'?'block':'none';
  if(mode==='quiz')renderOpts(c);
}
function showBack(c){
  document.getElementById('fs-front').style.display='none';
  document.getElementById('fs-back').style.display='block';
  document.getElementById('fs-img').classList.add('revealed');
  document.getElementById('fs-back-name').innerHTML=c.name+' '+typeChip(c.type);
  document.getElementById('fs-def').textContent=c.definition;
  document.getElementById('fs-card-src').textContent=c.card_source||'';
}
function renderActions(c){
  const sn=c.name.replace(/'/g,"\\'");
  const st=s(c.name);
  document.getElementById('fs-actions').innerHTML=
    `<button class="act-btn${st.learned?' learned':''}" onclick="toggleLearned('${sn}')">${st.learned?'✓ Learned':'Mark as learned'}</button>`;
}
function handleTap(){
  if(mode==='quiz'&&!answered)return;
  if(!revealed){revealed=true;showBack(deck[cur]);}
  else{if(cur<deck.length-1){cur++;render();}}
}
function go(d){cur=Math.max(0,Math.min(deck.length-1,cur+d));render();}
function setMode(m){
  mode=m;
  document.getElementById('pill-learn').classList.toggle('active',m==='learn');
  document.getElementById('pill-quiz').classList.toggle('active',m==='quiz');
  document.getElementById('fs-qstats').style.display=m==='quiz'?'flex':'none';
  if(m==='quiz'){sc=0;sw=0;['sc','sw'].forEach(id=>document.getElementById(id).textContent=0);}
  initDeck();render();
}
function renderOpts(c){
  const pool=filteredCards().filter(x=>x.name!==c.name);shuffle(pool);
  const choices=[c,...pool.slice(0,3)];shuffle(choices);
  const el=document.getElementById('fs-opts');el.className='on';
  const sn=c.name.replace(/'/g,"\\'");
  document.getElementById('fs-kw-name').innerHTML=
    `<div style="font-size:13px;color:rgba(255,255,255,.8);line-height:1.65;font-weight:400;max-width:600px">${c.definition}</div>`;
  document.getElementById('fs-tap-hint').style.display='none';
  el.innerHTML=choices.map(o=>{
    const on=o.name.replace(/'/g,"\\'");
    return `<button class="qopt" onclick="pick(this,'${on}','${sn}')">${o.name}</button>`;
  }).join('');
}
function pick(btn,chosen,correct){
  if(answered)return;answered=true;
  const ok=chosen===correct;
  document.querySelectorAll('.qopt').forEach(b=>{
    b.disabled=true;
    if(b.textContent.trim()===correct)b.classList.add('correct');
    else if(b===btn&&!ok)b.classList.add('wrong');
  });
  if(ok)sc++;else sw++;
  document.getElementById('sc').textContent=sc;
  document.getElementById('sw').textContent=sw;
  const qr=document.getElementById('fs-qres');
  qr.textContent=ok?'Correct!':`That's "${correct}"`;
  qr.className='on '+(ok?'ok':'no');
  revealed=true;
  showBack(CARDS.find(c=>c.name===correct));
  setTimeout(()=>{if(cur<deck.length-1){cur++;render();}else{qr.textContent=`Done! ${sc}/${sc+sw}`;}},2200);
}
function toggleLearned(name){ST[name].learned=!ST[name].learned;saveState();initDeck();render();}
function resetLearned(){CARDS.forEach(c=>{ST[c.name].learned=false;});saveState();initDeck();
  document.getElementById('fs-alldone').classList.remove('on');render();}

let catFilter='all';
function setCF(v,btn){
  catFilter=v;
  document.querySelectorAll('#cat-filters .dpill').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');renderCatalog();
}
function renderCatalog(){
  let list=[...CARDS];
  if(catFilter==='learned')list=list.filter(c=>s(c.name).learned);
  if(catFilter==='unlearned')list=list.filter(c=>!s(c.name).learned);
  if(catFilter==='unit')list=list.filter(c=>c.type==='unit');
  if(catFilter==='weapon')list=list.filter(c=>c.type==='weapon');
  if(catFilter==='upgrade')list=list.filter(c=>c.type==='upgrade');
  document.getElementById('cat-count').textContent=`${list.length} keyword${list.length!==1?'s':''}`;
  const g=document.getElementById('cat-grid');
  if(!list.length){g.innerHTML='<p class="empty-cat">Nothing here.</p>';return;}
  g.innerHTML=list.map(c=>{
    const st=s(c.name),src=ci(c),sn=c.name.replace(/'/g,"\\'");
    const th=src
      ?`<img class="cat-thumb" src="${src}" alt="${c.name}" loading="lazy"
             onerror="this.outerHTML='<div class=cat-thumb-ph>⚡</div>'">`
      :`<div class="cat-thumb-ph">⚡</div>`;
    return `<div class="cat-card${st.learned?' lrnd':''}" onclick="openMod('${sn}')">
      ${th}${st.learned?'<span class="cat-badge">✓</span>':''}
      <div class="cat-lbl"><div class="cat-name">${c.name}</div><div class="cat-type">${c.type}</div></div>
    </div>`;
  }).join('');
}

let mcard=null;
function openMod(name){
  mcard=CARDS.find(c=>c.name===name);renderMod();
  document.getElementById('modal-bg').classList.add('on');
}
function renderMod(){
  const c=mcard,st=s(c.name),src=ci(c);
  document.getElementById('mod-img').innerHTML=src
    ?`<img class="modal-photo" src="${src}" alt="${c.name}" onerror="this.outerHTML='<div class=modal-photo-ph>⚡</div>'">`
    :`<div class="modal-photo-ph">⚡</div>`;
  document.getElementById('mod-name').innerHTML=c.name+' '+typeChip(c.type);
  document.getElementById('mod-def').textContent=c.definition;
  document.getElementById('mod-src').textContent=c.card_source||'';
  const ml=document.getElementById('mod-lrnd');
  ml.textContent=st.learned?'✓ Learned — reset':'Mark as learned';
  ml.className='mbtn'+(st.learned?' lrnd':'');
}
function modToggleLearned(){toggleLearned(mcard.name);renderMod();renderCatalog();}
function closeMod(e){
  if(e&&e.target.id!=='modal-bg')return;
  document.getElementById('modal-bg').classList.remove('on');mcard=null;
}

loadState();setMode('learn');
</script>
</body>
</html>"""


def main():
    os.makedirs(IMGDIR, exist_ok=True)
    print("=" * 62)
    print("  SW Legion Flashcards Builder v2")
    print("  Source: AMG Core Rulebook v2.6 + LegionHQ CDN")
    print("=" * 62)

    # 1. Extract from PDF
    pdf_path = find_pdf()
    if pdf_path:
        print(f"\n[1/3] Extracting keywords from PDF...")
        keywords = extract_keywords_from_pdf(pdf_path)
    else:
        print("\n[1/3] PDF not found — using bundled definitions (144 keywords)")
        print("      To use your PDF, place it in the same folder as this script")
        print("      or in a documents/ subfolder.")
        keywords = {}

    if not keywords:
        keywords = BUNDLED_KEYWORDS

    print(f"      {len(keywords)} keywords ready")

    # 2. Download images
    print(f"\n[2/3] Downloading images from legionhq2.com CDN...")
    print(f"      Cached files are skipped automatically\n")
    card_data = []
    ok = fail = 0

    for i, (name, data) in enumerate(sorted(keywords.items()), 1):
        print(f"  [{i:3d}/{len(keywords)}] {name[:52]:<52} ", end="", flush=True)
        img_path, status = download_image(name, IMGDIR)
        print(status)
        if img_path: ok += 1
        else: fail += 1
        time.sleep(0.25)

        cards = KEYWORD_CARDS.get(name, [])
        card_source = f"See: {cards[0][0]}" if cards else ""
        card_data.append({
            "name":        name,
            "definition":  data.get("definition", ""),
            "type":        data.get("type", "unit"),
            "card_source": card_source,
            "imgs":        [img_path] if img_path else [],
        })

    print(f"\n  {ok} images OK  |  {fail} failed")

    # 3. Build HTML
    print(f"\n[3/3] Building swlegion_flashcards.html...")
    cards_js = json.dumps(card_data, ensure_ascii=False)
    html = HTML_TMPL.replace("/*CARD_JSON*/", cards_js)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUT) // 1024
    print(f"      swlegion_flashcards.html  ({kb} KB)")
    print(f"      images/                    ({ok} card images)")
    print()
    print("  Open swlegion_flashcards.html in your browser.")
    print("  Keep the images/ folder alongside the HTML file.")
    print("=" * 62)


# ── Bundled definitions (fallback when PDF not available) ──────────────────────
BUNDLED_KEYWORDS = {
  "Advanced Targeting: Unit Type X":{"type":"unit","definition":"When a unit with the Advanced Targeting X keyword declares an attack against an enemy unit with the unit type listed, during the Form Attack Pool step, it may gain X aim tokens. A unit that uses Advanced Targeting X may only form one attack pool and skips the Declare Additional Defender step."},
  "Agile X":{"type":"unit","definition":"The Agile X keyword allows a unit to gain a number of dodge tokens equal to X each time it performs a standard move as part of an action or free action."},
  "AI: Action":{"type":"unit","definition":"At the start of a unit with the AI keyword's Perform Actions step, if it is on the battlefield, does not have a faceup order token, and is not at Range 3 of a friendly Commander unit, it must perform one of the specified actions as its first action that activation."},
  "Aid: Affiliation":{"type":"unit","definition":"When a unit with the Aid keyword would gain an aim, dodge, or surge token, another friendly unit of the affiliation or type listed at Range 2 and in LOS may gain that token instead. If it does, the unit with Aid gains one suppression token."},
  "Allies of Convenience":{"type":"unit","definition":"Units with the Allies of Convenience keyword may issue orders to friendly Mercenary units regardless of affiliation. Additionally, when building an army, players may include one extra Mercenary unit regardless of rank if there is at least one unit with this keyword."},
  "Armor X":{"type":"unit","definition":"During the Modify Attack Dice step, if the defending unit has the Armor X keyword, the defending player may cancel up to X hit results, removing those dice from the attack pool."},
  "Arm X: Charge Token":{"type":"weapon","definition":"A unit equipped with a card that has the Arm X: Charge Token keyword can perform the Arm X action, placing X charge tokens of the specified type within Range 1 and LOS of its unit leader."},
  "Arsenal X":{"type":"unit","definition":"When choosing weapons during the Form Attack Pool step, each miniature in the unit that has Arsenal X can contribute X weapons to attack pools. Each weapon may only be added to one attack pool."},
  "Associate: Unit Name":{"type":"unit","definition":"During Army Building, a unit with the Associate keyword does not count its rank towards the maximum rank requirements for that rank if a unit with the specified unit name is included in the same army."},
  "Ataru Mastery":{"type":"unit","definition":"A unit with Ataru Mastery can perform up to two attack actions during its activation. When it attacks, it gains one dodge token after the attack resolves. When it defends, it gains one aim token after the attack resolves."},
  "Attack Run":{"type":"unit","definition":"At the start of its activation, a unit with Attack Run may increase or decrease its maximum speed by 1 until the end of that activation."},
  "Barrage":{"type":"unit","definition":"If a unit has the Barrage keyword, it may make two attack actions instead of one if it does not use the Arsenal keyword during its activation."},
  "Beam X":{"type":"weapon","definition":"During the Declare Additional Defender step, if a weapon with Beam X is in the attack pool, the unit may declare up to X additional attacks using only the Beam X weapon, even though it has already been added to an attack pool."},
  "Blast":{"type":"weapon","definition":"During the Apply Cover step, a defending unit cannot use light or heavy cover to cancel hit results produced by an attack pool that contains a weapon with the Blast keyword."},
  "Block":{"type":"unit","definition":"When a unit with the Block keyword is defending, if it spends any dodge tokens during the Apply Dodge and Cover step, it gains Armor X where X equals the number of dodge tokens spent."},
  "Bolster X":{"type":"unit","definition":"As a card action, a unit with Bolster X can choose up to X friendly units at Range 1. Each chosen unit gains an aim token."},
  "Bounty":{"type":"unit","definition":"During Setup, a unit with Bounty chooses an enemy Commander or Operative unit. If that unit is defeated, the player who controls the Bounty unit scores 1 victory point."},
  "Cache":{"type":"unit","definition":"During Setup, a unit with an equipped Upgrade Card that has the Cache keyword places the specified token(s) on that Upgrade Card."},
  "Calculate Odds":{"type":"unit","definition":"As a card action, a unit with Calculate Odds can choose a friendly unit at Range 1-2 and in LOS. That unit gains an aim token, a dodge token, and a surge token."},
  "Charge":{"type":"unit","definition":"After a unit that has Charge performs a move action that brings it into base contact with an enemy miniature, it may perform a free melee attack action."},
  "Climbing Vehicle":{"type":"unit","definition":"A unit with the Climbing Vehicle keyword is treated as a trooper unit for the purposes of vertical movement."},
  "Compel":{"type":"unit","definition":"After another trooper unit at Range 1-2 of a friendly unit with Compel performs its Rally step and is suppressed but not panicked, at the beginning of its Perform Actions step, it may gain 1 suppression token to perform a free move action."},
  "Complete The Mission":{"type":"unit","definition":"During Setup, for each friendly unit with Complete the Mission, that unit's controlling player places 1 victory token on the battlefield beyond Range 3 of all enemy units. Once per game, at the beginning of the Command Phase, if that unit is within Range 1 of a friendly victory token, it may claim it."},
  "Coordinate: Unit Name/Unit Type":{"type":"unit","definition":"After a unit with the Coordinate keyword is issued an order, it may issue an order to a friendly unit at Range 1 that has the unit name or unit type specified."},
  "Counterpart":{"type":"unit","definition":"A unit with the Counterpart keyword has a Counterpart Card. That miniature is always added to another unit and forms a combined unit using the rank, type, defense die, courage value, surge conversion chart, and speed shown on the Unit Card."},
  "Covert Ops":{"type":"unit","definition":"During Setup, a unit with Covert Ops may change its rank to Operative for all rules purposes for the rest of the game. If it does, it gains the Infiltrate keyword that game."},
  "Cover X":{"type":"unit","definition":"If a unit has Cover X and is defending against an attack with at least one ranged weapon, during the Apply Dodge and Cover step, it improves the numerical value of its cover by X."},
  "Critical X":{"type":"weapon","definition":"When a unit converts attack surges for an attack pool with Critical X, during the Convert Surges step it may convert up to X attack surge results to critical results."},
  "Cumbersome":{"type":"weapon","definition":"A unit that has a weapon with Cumbersome cannot perform a move prior to attacking with that weapon during the same activation unless the move is a pivot. A unit may move with its second action after attacking with a Cumbersome weapon. Cumbersome weapons may be used on Standby and Pulling the Strings attacks even if the unit moved that activation."},
  "Cunning":{"type":"unit","definition":"During the Command Phase, if a player reveals a Commander or Operative specific Command Card belonging to a unit with Cunning and there would be a tie for priority, treat that card as having one fewer pip."},
  "Cycle":{"type":"upgrade","definition":"At the end of a unit's activation, ready each of its exhausted Upgrade Cards with the Cycle keyword that was not used during that activation."},
  "Danger Sense X":{"type":"unit","definition":"When a unit with Danger Sense X would remove any number of suppression tokens, it may choose to not remove up to X tokens. While defending, it rolls one extra defense die for every suppression token it has, up to X additional dice."},
  "Dauntless":{"type":"unit","definition":"After a unit with Dauntless performs its Rally step and is suppressed but not panicked, at the beginning of its Perform Action step, it may gain one suppression token to perform a free move action. A unit with Dauntless may not be affected by the Compel keyword."},
  "Death From Above":{"type":"unit","definition":"When a unit with Death From Above attacks, the defending unit cannot use cover to cancel hit results during the Apply Cover step if the attacking unit's unit leader is overlapping non-area terrain of greater height than any terrain the defending unit leader is overlapping."},
  "Defend X":{"type":"unit","definition":"After a unit with Defend X is issued an order, it gains X dodge tokens."},
  "Deflect":{"type":"unit","definition":"While a unit with Deflect is defending against a ranged attack or using Guardian X, its surge conversion chart gains Surge: Block. Additionally, during the Convert Defense Surges step, the attacker suffers one wound if there is at least one surge result in the defense roll. Deflect has no effect against attacks where High Velocity weapons are the only weapons in the pool."},
  "Demoralize X":{"type":"unit","definition":"After a unit with Demoralize X performs its Rally step, add up to X total suppression tokens to enemy units at Range 2."},
  "Detachment: Unit Name/Type":{"type":"unit","definition":"During Army Building, a unit with Detachment doesn't count against the maximum number of units of its rank. It can only be included if another unit with the specified unit name or type is also included."},
  "Detonate X: (Charge Type)":{"type":"weapon","definition":"After a unit attacks, moves, or performs an action, each unit with Detonate X may detonate up to X friendly charge tokens of the specified type. When a token detonates, perform a separate attack against each unit in LOS and in range of the area weapon."},
  "Direct: Unit Name/Unit Type":{"type":"unit","definition":"Each Command Phase, during the Issue Orders step, a unit with Direct may issue an order to a friendly unit at Range 2 that has the unit name or unit type specified."},
  "Disciplined X":{"type":"unit","definition":"After a unit with Disciplined X is issued an order, it may remove up to X suppression tokens."},
  "Disengage":{"type":"unit","definition":"While a trooper unit with Disengage is engaged with a single enemy unit, it can still perform moves as normal."},
  "Distract":{"type":"unit","definition":"As a free card action, a unit with Distract can choose an enemy trooper unit at Range 2 and in LOS. Until the end of the round, when that enemy unit performs an attack, it must attack the unit that used Distract, if able."},
  "Divine Influence":{"type":"unit","definition":"While at Range 1 of a friendly C-3PO, friendly trooper units gain Guardian 2: C-3PO. While using Guardian, they may cancel block results as if they were hit results."},
  "Djem So Mastery":{"type":"unit","definition":"When a unit with Djem So Mastery is defending against a melee attack, during the Compare Results step, the attacking unit suffers a wound if the attack roll contains one or more blank results."},
  "Duelist":{"type":"unit","definition":"When a unit with Duelist performs a melee attack and spends one or more aim tokens during the Reroll Attack Dice step, the attack pool gains Pierce 1. When defending against a melee attack and spending at least one dodge token during Apply Dodge and Cover, it gains Immune: Pierce."},
  "Enrage X":{"type":"unit","definition":"When a unit with Enrage X has wound tokens greater than or equal to X, it gains the Charge keyword, treats its courage value as '-', and loses any suppression tokens it may have."},
  "Entourage: Unit Name":{"type":"unit","definition":"During Army Building, if a player includes a unit with Entourage, one unit specified by the keyword does not count its rank towards the maximum rank requirements. In the Command Phase, the Entourage unit may issue an order to a friendly unit at Range 2 with the specified name."},
  "Equip":{"type":"unit","definition":"During Army Building, a unit with the Equip keyword must equip the upgrades listed after the keyword."},
  "Exemplar":{"type":"unit","definition":"While attacking or defending, if a friendly unit is at Range 2 and in LOS of one or more friendly units with Exemplar that share the same faction or affiliation, that unit may spend one aim, dodge, or surge token belonging to one of those Exemplar units as if it had the token."},
  "Expert Climber":{"type":"unit","definition":"When a unit with Expert Climber performs a climb, it may move a vertical distance up to height 2."},
  "Field Commander":{"type":"unit","definition":"During Army Building, an army that includes a unit with Field Commander may ignore the minimum Commander rank requirement. A unit with Field Commander is not a Commander and only counts as one for the purposes of issuing orders with a Command Card."},
  "Fire Support":{"type":"unit","definition":"After a unit with Fire Support is issued an order, it gains a standby token."},
  "Fixed: Front/Rear":{"type":"weapon","definition":"To add a weapon with Fixed: Front or Fixed: Rear to an attack pool, the defending unit must have at least one miniature's base partially inside the specified firing arc of the attacking miniature."},
  "Flawed":{"type":"unit","definition":"A unit with Flawed has a corresponding Flaw Card that must be added to an opponent's command hand during Setup. The opponent may play the Flaw Card when permitted by its rules."},
  "Flexible Response X":{"type":"unit","definition":"During Army Building, a unit with Flexible Response X must equip X heavy weapon upgrades."},
  "Full Pivot":{"type":"unit","definition":"When a unit with Full Pivot performs a pivot, it may pivot up to 360°."},
  "Generator X":{"type":"unit","definition":"During the End Phase, a unit with Generator X may flip up to X inactive shield tokens to their active side."},
  "Guardian X":{"type":"unit","definition":"While a friendly trooper unit at Range 1 and in LOS of a unit with Guardian X is defending against a ranged attack, it may cancel up to X hit results during Modify Attack Dice. For each hit canceled in this way, the Guardian unit rolls a defense die and suffers one wound for each blank result."},
  "Guidance":{"type":"unit","definition":"When a unit uses the Guidance card action, choose another friendly unit at Range 1-2 and in LOS. That unit may perform a free move action."},
  "Gunslinger":{"type":"unit","definition":"When a unit with Gunslinger reaches the Declare Additional Defender step, it may declare an additional defender and create an attack pool consisting solely of a ranged weapon that has already been contributed to another attack pool. Gunslinger can only be used once per attack sequence."},
  "Heavy Weapon Team":{"type":"unit","definition":"A unit with Heavy Weapon Team must equip a heavy weapon Upgrade Card. The miniature added to the unit with this Upgrade Card becomes the unit leader."},
  "High Velocity":{"type":"weapon","definition":"While defending against an attack in which weapons with High Velocity are the only weapons in an attack pool, the defending unit cannot spend dodge tokens during the Apply Dodge and Cover step."},
  "Hover: Ground/Air X":{"type":"unit","definition":"A unit with Hover: Ground or Hover: Air X can perform standby actions and gain and spend standby tokens. Hover: Ground is treated as a ground vehicle for LOS purposes. Hover: Air X ignores terrain of height X or lower while moving."},
  "Hunted":{"type":"unit","definition":"During Setup, if one or more enemy units have the Bounty keyword, each unit with Hunted gains a victory token."},
  "Immune: Blast":{"type":"unit","definition":"The Blast keyword cannot be used against a unit with Immune: Blast."},
  "Immune: Deflect":{"type":"weapon","definition":"During an attack, if the attack pool contains weapons with Immune: Deflect, the attacking unit cannot suffer wounds from the Deflect keyword."},
  "Immune: Enemy Effects":{"type":"unit","definition":"Enemy card effects cannot be used to affect a unit with Immune: Enemy Effects."},
  "Immune: Melee":{"type":"unit","definition":"Enemy units cannot be placed in base contact with a unit that has Immune: Melee, and enemy units cannot perform melee attacks against it."},
  "Immune: Melee Pierce":{"type":"unit","definition":"While a unit with Immune: Melee Pierce is defending against a melee attack, the Pierce X keyword cannot be used against this unit."},
  "Immune: Pierce":{"type":"unit","definition":"While a unit with Immune: Pierce is defending, the Pierce X keyword cannot be used against this unit."},
  "Immune: Range 1 Weapons":{"type":"unit","definition":"An attack pool assigned to a unit with Immune: Range 1 Weapons that contains only Range 1 weapons has no effect and is canceled."},
  "Impact X":{"type":"weapon","definition":"During the Modify Attack Dice step, if the defending unit has Armor or Armor X, a unit whose attack pool includes Impact X can modify up to X hit results to critical results for that attack."},
  "Immobilize X":{"type":"weapon","definition":"A unit that suffers wounds after defending against an attack with Immobilize X gains X immobilize tokens. A unit's maximum speed is reduced by 1 for each immobilize token it has."},
  "Impervious":{"type":"unit","definition":"While a unit with Impervious is defending, it rolls one additional defense die for each Pierce result that would affect it."},
  "Incognito":{"type":"unit","definition":"A unit with Incognito cannot be attacked by enemy units beyond Range 1 unless it is the closest enemy unit."},
  "Inconspicuous":{"type":"unit","definition":"While a unit with Inconspicuous has a facedown order token, enemy units cannot attack it unless it is the only enemy unit that can be attacked."},
  "Independent: Token X":{"type":"unit","definition":"At the start of the Activation Phase, if a unit with Independent: Token X does not have a faceup order token, it gains the listed token(s)."},
  "Indomitable":{"type":"unit","definition":"While a unit with Indomitable is rallying, it rolls one additional die for each suppression token it has beyond its courage value."},
  "Infiltrate":{"type":"unit","definition":"During Setup, a unit with Infiltrate can be deployed anywhere on the battlefield that is beyond Range 3 of all enemy units."},
  "Ion X":{"type":"weapon","definition":"A vehicle or droid trooper unit that suffers wounds after defending against an attack with Ion X gains X ion tokens. A unit's maximum speed is reduced by 1 for each ion token it has."},
  "Interrogate":{"type":"unit","definition":"During the Command Phase, if a player reveals a Command Card belonging to a unit with Interrogate, that player may look at their opponent's command hand."},
  "Jar'kai Mastery":{"type":"unit","definition":"While performing a melee attack, after converting attack surges during the Convert Attack Surges step, a unit with Jar'Kai Mastery may convert one attack surge result to a hit result."},
  "Jedi Hunter":{"type":"unit","definition":"When a unit with Jedi Hunter attacks a unit with a force upgrade slot, it adds 1 red attack die to its attack pool."},
  "Jump X":{"type":"unit","definition":"A unit with Jump X can perform the Jump X card action, performing a move that may ignore terrain of height X or lower during that move."},
  "Juyo Mastery":{"type":"unit","definition":"While a unit with Juyo Mastery has one or more wound tokens, when it performs a melee attack, it rolls one additional red attack die."},
  "Latent Power":{"type":"unit","definition":"At the end of a unit with Latent Power's activation, if it has no order token, it may gain a Force token. Force tokens may be spent as aim, dodge, or surge tokens."},
  "Lethal X":{"type":"weapon","definition":"When a unit performs an attack with Lethal X in the attack pool, it can spend up to X aim tokens during Modify Attack Dice. If it does, the attack pool gains Pierce 1 for each aim token spent."},
  "Loadout":{"type":"unit","definition":"During Army Building, when a player includes a unit with Loadout, that unit may swap any of its non-fixed upgrade cards for other upgrades of the same type up to the same point cost."},
  "Long Shot":{"type":"weapon","definition":"When a unit with Long Shot performs an attack, before choosing an enemy unit to attack, it may spend an aim token to increase the maximum range of that weapon by one until the end of that attack sequence."},
  "Low Profile":{"type":"unit","definition":"While defending against a ranged attack, if a unit with Low Profile is obscured, it rolls 1 extra die during the Roll Cover Pool step."},
  "Makashi Mastery":{"type":"unit","definition":"While a unit with Makashi Mastery performs a melee attack, after resolving the attack, the unit may remove all suppression tokens and recover all exhausted upgrade cards."},
  "Marksman":{"type":"unit","definition":"After converting attack surges during the Convert Attack Surges step, a unit with Marksman may convert one attack surge result to a hit result."},
  "Master Of The Force":{"type":"unit","definition":"During the End Phase, a unit with Master of the Force X may ready X of its exhausted Force upgrade cards."},
  "Master Storyteller":{"type":"unit","definition":"When a unit performs the Master Storyteller card action, it may choose up to 2 friendly units at Range 1-2. Each chosen unit removes all suppression tokens and gains a surge token."},
  "Mercenary":{"type":"unit","definition":"A unit with the Mercenary keyword is a Mercenary unit and can be included in armies of specified factions or affiliations as defined on the unit's card."},
  "Nimble":{"type":"unit","definition":"After a unit with Nimble defends against an attack, if it spent any dodge tokens during that attack, it gains one dodge token."},
  "Observe X":{"type":"unit","definition":"As a card action or free card action, a unit with Observe X can choose an enemy unit at Range 1-3 and in LOS. That unit gains X observation tokens, improving cover for attacks against it."},
  "Outmaneuver":{"type":"unit","definition":"During the Apply Dodge and Cover step, a unit with Outmaneuver can spend dodge tokens to cancel critical results as if they were hit results."},
  "Override":{"type":"unit","definition":"When a friendly unit begins its activation while at Range 1 of a unit with Override, the Override unit may spend an action to allow the friendly unit to perform a free card action."},
  "Overrun X":{"type":"weapon","definition":"A unit may make X overrun attacks during its activation after it performs a standard move in which the movement tool or one of its miniatures' bases overlapped an enemy miniature's base."},
  "Pierce X":{"type":"weapon","definition":"If an attacking unit attacks with Pierce X it may cancel up to X block results during the Modify Defense Dice step."},
  "Plodding":{"type":"unit","definition":"During its activation, a unit with Plodding can only move by performing a single standard move and cannot perform any other type of move action."},
  "Poison":{"type":"weapon","definition":"A non-droid trooper unit that suffers wounds from an attack with the Poison keyword gains 1 poison token. At the end of a unit's activation, it suffers one wound for each poison token, then removes all poison tokens."},
  "Poison X":{"type":"weapon","definition":"A non-droid trooper unit that suffers wounds from an attack with Poison X gains X poison tokens. At the end of a unit's activation, it suffers one wound for each poison token, then removes all poison tokens."},
  "Precise X":{"type":"unit","definition":"When an attacking unit with Precise X spends an aim token, it may reroll up to X additional dice."},
  "Primitive":{"type":"weapon","definition":"During Modify Attack Dice, after resolving Impact X, if the defending unit has Armor or Armor X, a unit whose attack pool includes Primitive must modify all critical results to hit results for that attack."},
  "Ram X":{"type":"weapon","definition":"While a unit performs an attack using Ram X, during Modify Attack Dice, it may change X results to critical results if the unit leader has a notched base and performed at least one full standard move at maximum speed during the same activation."},
  "Ready X":{"type":"unit","definition":"After a unit with Ready X performs a standby action, it gains X aim tokens."},
  "Relentless":{"type":"unit","definition":"After a unit with Relentless performs a move action, it may perform a free attack action."},
  "Reposition":{"type":"unit","definition":"When a unit with Reposition performs a standard move, it may perform a free pivot either before or after that move."},
  "Retinue: Unit/Unit Type":{"type":"unit","definition":"At the start of the Activation Phase, if a unit with Retinue is at Range 1-2 of the specified unit or type, it gains either 1 aim or 1 dodge token."},
  "Ruthless":{"type":"unit","definition":"When another friendly trooper unit at Range 2 and in LOS with a faceup order token activates, a unit with Ruthless may spend 1 action to allow that unit to remove 1 suppression token. That unit then gains 1 suppression token."},
  "Scale":{"type":"unit","definition":"When a unit with Scale performs a climb, it may move a vertical distance up to height 2."},
  "Scatter":{"type":"weapon","definition":"After a unit performs an attack against a trooper unit on small bases using Scatter, it may place any non-unit leader miniatures in the defending unit following cohesion rules as if the defending unit leader had just performed a standard move."},
  "Scout X":{"type":"unit","definition":"When an undeployed unit with Scout X activates, at the start of its activation it may perform a speed-X move before deploying."},
  "Scouting Party X":{"type":"unit","definition":"During Setup, the controlling player of a unit with Scouting Party X may choose up to X friendly units to gain the Scout 1 keyword for that game."},
  "Secret Mission":{"type":"unit","definition":"Once per game, at the beginning of the Command Phase, if a unit with Secret Mission is within the enemy deployment zone, that unit's controlling player scores 1 victory point."},
  "Self-Destruct X":{"type":"weapon","definition":"A unit can perform a Self-Destruct attack as a free action if it has at least X wound tokens, attacking each unit at Range 1 and in LOS. After performing all attacks, the unit performing the Self-Destruct attack is defeated."},
  "Self-Preservation":{"type":"unit","definition":"When checking to see if a unit with Self-Preservation panics, it uses its own courage value even if a friendly Commander is within Range 3."},
  "Sentinel":{"type":"unit","definition":"A unit with Sentinel can spend a standby token after an enemy unit performs an attack against a friendly unit at Range 1-3 and in LOS."},
  "Sharpshooter X":{"type":"unit","definition":"During the Determine Cover step, a unit with Sharpshooter X reduces the defender's cover by X."},
  "Shielded X":{"type":"unit","definition":"A unit with Shielded X has X shield tokens. Shield tokens can be spent to negate wounds. At the start of a unit's activation, flip all inactive shield tokens to their active side."},
  "Smoke X":{"type":"unit","definition":"As a card action, a unit with Smoke X can place X smoke tokens within Range 1 and in LOS of its unit leader. Units in or touching a smoke token improve their cover by 1."},
  "Soresu Mastery":{"type":"unit","definition":"When a unit with Soresu Mastery is defending against a ranged attack, it may reroll any number of its defense dice. When using Guardian X, it does not suffer wounds from blank results rolled while using Guardian."},
  "Special Issue":{"type":"unit","definition":"A unit with Special Issue can only be included in an army if another unit with a specified unit name is also included in that army."},
  "Speeder X":{"type":"unit","definition":"While a unit with Speeder X is not on impassable terrain, it must perform at least X moves during its activation. A unit with Speeder X also has the Unhindered keyword."},
  "Spray":{"type":"weapon","definition":"When a miniature adds a weapon with Spray to the attack pool, that weapon contributes its dice a number of times equal to the number of miniatures in the defending unit that are in LOS of the miniature using that weapon."},
  "Stationary":{"type":"unit","definition":"A unit with Stationary cannot perform moves of any kind, including pivots, but still has a speed value on its Unit Card."},
  "Steady":{"type":"unit","definition":"After a unit with Steady rallies, if it is suppressed but not panicked, it may gain 1 suppression token to perform a free move action."},
  "Suppressive":{"type":"weapon","definition":"After defending against an attack pool that includes a weapon with Suppressive, the defending unit gains one suppression token during the Assign Suppression Token to Defender step."},
  "Take Cover X":{"type":"unit","definition":"As a card action, a unit with Take Cover X can choose up to X friendly units at Range 1-2 and in LOS. Each chosen unit gains a dodge token."},
  "Target X":{"type":"unit","definition":"After a unit with Target X is issued an order, it gains X aim tokens."},
  "Teamwork: Unit Name":{"type":"unit","definition":"When a unit with Teamwork is at Range 1-2 of a friendly unit with the specified name, when either unit gains an aim or dodge token, the other unit also gains a token of the same type."},
  "Tempted":{"type":"unit","definition":"If a friendly unit is defeated by an enemy attack and the attacking unit is at Range 3 of a unit with Tempted, after the attack resolves, the Tempted unit may perform a free attack action or a speed-2 move ignoring difficult terrain."},
  "Tenacity":{"type":"unit","definition":"When a unit with Tenacity has 1 or more wound tokens, it may perform an additional action during its activation. Even with free actions, a unit cannot perform more than 3 move actions."},
  "Token X":{"type":"unit","definition":"At the start of the Activation Phase, if a unit with Token X does not have a faceup order token, it gains the listed token(s)."},
  "Tow Cable":{"type":"weapon","definition":"After a vehicle is wounded by an attack pool that included Tow Cable, the player who performed the attack performs a pivot with the vehicle that was wounded."},
  "Transport":{"type":"unit","definition":"During Setup, a unit with Transport may choose a friendly Corps or Special Forces unit to transport. During the round 1 Command Phase, it may issue an order to that unit. If the transported unit is undeployed when the Transport deploys, the transported unit deploys by performing a speed-1 move."},
  "Uncanny Luck X":{"type":"unit","definition":"While a unit with Uncanny Luck X is defending, it may reroll up to X of its defense dice during the Reroll Defense Dice step."},
  "Unconcerned":{"type":"unit","definition":"A unit with Unconcerned cannot benefit from cover, and miniatures in the unit cannot be repaired or restored."},
  "Unhindered":{"type":"unit","definition":"When a unit with Unhindered performs a move, it ignores the effects of difficult terrain."},
  "Unstoppable":{"type":"unit","definition":"A unit with Unstoppable is eligible to activate during the Activation Phase while it has one or fewer facedown order tokens."},
  "Versatile":{"type":"weapon","definition":"Units can perform ranged attacks using a weapon with Versatile even while engaged. A weapon with Versatile that is both ranged and melee can be used to perform either a ranged or melee attack."},
  "We're Not Regs":{"type":"unit","definition":"A unit with We're Not Regs may not spend green tokens on other Clone Trooper units, and other Clone Trooper units may not spend this unit's green tokens. This unit cannot benefit from backup."},
  "Weighed Down":{"type":"unit","definition":"While a unit with Weighed Down is holding 1 or more objective tokens, it cannot use the Jump keyword."},
  "Wheel Mode":{"type":"unit","definition":"At the start of its activation, a unit with Wheel Mode can increase its maximum speed to 3 until the end of that activation. If it does, it gains Cover 2 and cannot attack or flip active shield tokens."},
  "Wound X":{"type":"unit","definition":"The first time a unit with Wound X enters play, that unit suffers X wounds."},
  "Divulge":{"type":"upgrade","definition":"Some Command Cards have the Divulge keyword. These cards can be revealed at the start of the phase or step indicated to resolve the Divulge effect without playing the card. A divulged card is returned to the command hand at the end of that step."},
}

if __name__ == "__main__":
    main()
