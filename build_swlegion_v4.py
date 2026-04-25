#!/usr/bin/env python3
"""
Star Wars Legion Flashcards Builder v4
========================================
Merged from v2 (PDF keyword extraction, .webp CDN images) and
v3 (Supabase auth, army lists, unit DB, full HTML template).

Keyword sources:
  1. legion.takras.net          (web scraping — names, types, definitions)
  2. SWQ_Rulebook_2.6.0-1.pdf  (PDF extraction — overrides definitions with official AMG text)
  3. BUNDLED_KEYWORDS           (offline fallback for any empty definitions)

Image source: legionhq2.com CDN (d2maxvwz12z6fm.cloudfront.net)
Fallback:     Wikimedia Commons

Usage:
    py -m pip install requests pdfplumber beautifulsoup4
    py build_swlegion_v4.py

Output:
    swlegion_flashcards.html
    images/   (one .webp/.jpg per keyword)
"""

import os, re, json, time, sys
import requests
from urllib.parse import urlencode

HERE          = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR     = os.path.join(HERE, 'cache')
IMGDIR        = os.path.join(CACHE_DIR, 'images')        # download cache (gitignored)
DIST_DIR      = os.path.join(HERE, 'dist')
DIST_IMGDIR   = os.path.join(DIST_DIR, 'images')         # final distributed images
OVERRIDES_DIR = os.path.join(HERE, 'overrides')          # was: card_art + manual
DATA_DIR      = os.path.join(HERE, 'data')
OUT           = os.path.join(DIST_DIR, 'index.html')
# Keep these for backward compat with code that uses them:
CARD_ART_DIR  = OVERRIDES_DIR
MANUAL_DIR    = OVERRIDES_DIR
BASE   = 'https://legion.takras.net'
CDN    = 'https://d2maxvwz12z6fm.cloudfront.net'
LEGIONHQ_CDN     = 'https://d2maxvwz12z6fm.cloudfront.net/unitCards/'
WIKI_COMMONS_API = 'https://commons.wikimedia.org/w/api.php'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ── Locate the PDF ────────────────────────────────────────────────────────────
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

KEYWORD_PAGES = [
    # Updated Rules in 11.11.2025
    ("anti_materiel_x",           "Anti-Materiel X"),
    ("anti_personnel_x",          "Anti-Personnel X"),
    ("upgrading_dice",            "Upgrading and Downgrading Dice"),
    ("cumbersome",                "Cumbersome"),
    ("command_vehicle_x",         "Command Vehicle X"),
    ("mobile",                    "Mobile"),
    # A
    ("abilities_provide_move",    "Abilities That Provide Moves"),
    ("activating_units",          "Activating a Unit"),
    ("activation_phase",          "Activation Phase"),
    ("advanced_targeting_x",      "Advanced Targeting: Unit Type X"),
    ("advantage_cards",           "Advantage Cards"),
    ("advantage_token",           "Advantage Token"),
    ("affiliations",              "Affiliations"),
    ("agile_x",                   "Agile X"),
    ("ai_action",                 "AI: Action[]"),
    ("aid",                       "Aid: Affiliation[]"),
    ("aim",                       "Aim"),
    ("allied_and_enemy",          "Allied and Enemy"),
    ("allies_of_convenience",     "Allies of Convenience"),
    ("apply_dodge_cover",         "Apply Dodge and Cover"),
    ("area_terrain",              "Area Terrain"),
    ("area_weapon",               "Area Weapon[]"),
    ("arm_x",                     "Arm X[]"),
    ("armor_x",                   "Armor X"),
    ("army_building",             "Army Building"),
    ("arsenal_x",                 "Arsenal X"),
    ("associate",                 "Associate: Unit Name"),
    ("ataru_mastery",             "Ataru Mastery"),
    ("attack",                    "Attack"),
    ("attack_run",                "Attack Run"),
    ("actions",                   "Make Actions"),
    # B
    ("backup",                    "Backup[]"),
    ("bane_tokens",               "Bane Tokens[]"),
    ("barrage",                   "Barrage"),
    ("barricades",                "Barricades"),
    ("base",                      "Bases and Base Contact"),
    ("battle_cards",              "Battle Cards"),
    ("battle_forces",             "Battle Forces"),
    ("battlefield",               "Battlefield"),
    ("beam_x",                    "Beam X[]"),
    ("blast",                     "Blast"),
    ("block",                     "Block"),
    ("bolster_x",                 "Bolster X[]"),
    ("bounty",                    "Bounty"),
    ("building_a_battle_deck",    "Building a Battle Deck"),
    ("building_a_command_hand",   "Building a Command Hand"),
    ("building_a_mission",        "Building a Mission"),
    ("objects",                   "Objects/Battlefield"),
    # C
    ("cache",                     "Cache"),
    ("calculate_odds",            "Calculate Odds[]"),
    ("cancel",                    "Canceling Results"),
    ("card_action",               "Card Action"),
    ("card_effects",              "Card Effects"),
    ("charge",                    "Charge"),
    ("charge_token",              "Charge Token"),
    ("claiming_objective_tokens", "Claiming Objective Tokens"),
    ("climb",                     "Climbing"),
    ("climb_vehicle",             "Climbing Vehicle"),
    ("clone_trooper",             "Clone Trooper"),
    ("cohesion",                  "Cohesion"),
    ("command_cards",             "Command Cards"),
    ("command_phase",             "Command Phase"),
    ("panic_commander",           "Commander and Panic Check"),
    ("compel",                    "Compel: Rank/Unit Type[]"),
    ("complete_the_mission",      "Complete the Mission[]"),
    ("compulsory_move",           "Compulsory Move"),
    ("contesting_objectives",     "Contesting Objective Tokens"),
    ("coordinate",                "Coordinate: Type/Name[]"),
    ("counterpart",               "Counterpart"),
    ("courage",                   "Courage"),
    ("cover",                     "Cover"),
    ("cover_x",                   "Cover X"),
    ("covert_ops",                "Covert Ops"),
    ("creature_trooper",          "Creature Trooper"),
    ("critical_x",                "Critical X"),
    ("cunning",                   "Cunning"),
    ("cycle",                     "Cycle"),
    # D
    ("danger_sense",              "Danger Sense"),
    ("dauntless",                 "Dauntless"),
    ("death_from_above",          "Death From Above"),
    ("declare_terrain",           "Declare and Place Terrain"),
    ("declare_defender",          "Declare Defender"),
    ("defeating_upgrade_cards",   "Defeating Upgrade Card and Discarding Upgrade Cards"),
    ("defend_x",                  "Defend X"),
    ("deflect",                   "Deflect"),
    ("demoralize_x",              "Demoralize X[]"),
    ("deploy",                    "Deploy"),
    ("detachment",                "Detachment: Name/Type"),
    ("determine_blue_player",     "Determine Blue Player"),
    ("determine_priority",        "Determine Priority"),
    ("detonate_x",                "Detonate X (Charge Type)"),
    ("dice",                      "Dice"),
    ("difficult_terrain",         "Difficult Terrain"),
    ("direct",                    "Direct Name/Type[]"),
    ("disciplined_x",             "Disciplined X"),
    ("disengage",                 "Disengage"),
    ("distract",                  "Distract[]"),
    ("divine_influence",          "Divine Influence[]"),
    ("divulge",                   "Divulge"),
    ("djem_so_mastery",           "Djem So Mastery"),
    ("dodge",                     "Dodge"),
    ("dodge_token",               "Dodge token"),
    ("droid_trooper",             "Droid Trooper"),
    ("dual_sided_upgrade_cards",  "Dual-Sided Upgrade Cards"),
    ("duelist",                   "Duelist"),
    # E
    ("emplacement_trooper",       "Emplacement Trooper"),
    ("empty_decks",               "Empty Decks"),
    ("end_phase",                 "End Phase"),
    ("engaged",                   "Engaged"),
    ("enrage_x",                  "Enrage X"),
    ("entourage",                 "Entourage: Unit Name[]"),
    ("equip",                     "Equip"),
    ("establish_battlefield",     "Establish the Battlefield and Prepare Components"),
    ("exemplar",                  "Exemplar[]"),
    ("exhaust",                   "Exhaust and Expend"),
    ("expert_climber",            "Expert Climber"),
    # F
    ("faction",                   "Factions"),
    ("field_commander",           "Field Commander"),
    ("fire_support",              "Fire Support"),
    ("fitting_on_terrain",        "Fitting on Terrain"),
    ("fixed",                     "Fixed: Front/Rear"),
    ("flexible_response_x",       "Flexible Response X"),
    ("form_attack_pools",         "Form Attack Pools"),
    ("free_card_action",          "Free Card Action"),
    ("full_pivot",                "Full Pivot"),
    # G
    ("game_effects",              "Game Effects"),
    ("game_overview",             "Game Overview"),
    ("generator_x",               "Generator X"),
    ("golden_rule_terrain",       "Golden Rule of Terrain"),
    ("graffiti_tokens",           "Graffiti Tokens[]"),
    ("ground_vehicles",           "Ground Vehicles"),
    ("guardian_x",                "Guardian X[]"),
    ("guidance",                  "Guidance[]"),
    ("gunslinger",                "Gunslinger"),
    # H
    ("heavy_weapon_team",         "Heavy Weapon Team"),
    ("high_velocity",             "High Velocity"),
    ("hold_the_line",             "Hold the Line"),
    ("hover_x",                   "Hover: Ground/Air X"),
    ("hunted",                    "Hunted"),
    # I
    ("im_part_of_the_squad_too",  "I'm Part of the Squad Too[]"),
    ("immobilize_x",              "Immobilize X"),
    ("immune",                    "Immune: Keyword"),
    ("impact_x",                  "Impact X"),
    ("impassable_terrain",        "Impassable Terrain"),
    ("impervious",                "Impervious"),
    ("incognito",                 "Incognito[]"),
    ("inconspicious",             "Inconspicious[]"),
    ("independent_x",             "Independent: Token X/Action"),
    ("indomitable",               "Indomitable"),
    ("infiltrate",                "Infiltrate"),
    ("inspire_x",                 "Inspire X[]"),
    ("interrogate",               "Interrogate[]"),
    ("ion_x",                     "Ion X"),
    ("issue_order",               "Nominate Commanders and Issue Orders"),
    # J
    ("jarkai_mastery",            "Jar'Kai Mastery"),
    ("jedi_hunter",               "Jedi Hunter"),
    ("jump_x",                    "Jump X"),
    ("juyo_mastery",              "Juyo Mastery"),
    # K
    ("keywords",                  "Keywords"),
    # L
    ("latent_power",              "Latent Power[]"),
    ("leader",                    "Leader"),
    ("leaving_battlefield",       "Leaving the Battlefield"),
    ("lethal_x",                  "Lethal X"),
    ("line_of_sight",             "Line of Sight"),
    ("long_shot",                 "Long Shot"),
    ("low_profile",               "Low Profile"),
    # M
    ("makashi_mastery",           "Makashi Mastery"),
    ("map_cards",                 "Map Cards"),
    ("marksman",                  "Marksman"),
    ("master_of_the_force",       "Master of the Force"),
    ("master_storyteller",        "Master Storyteller[]"),
    ("measurement",               "Measurement"),
    ("measuring_range",           "Measuring Range"),
    ("melee",                     "Melee"),
    ("melee_pierce",              "Melee Pierce"),
    ("mercenaries",               "Mercenaries"),
    ("mercenary",                 "Mercenary: Faction"),
    ("miniature",                 "Miniatures"),
    ("move",                      "Move"),
    ("move_into_melee",           "Moving Into Melee"),
    ("move_through_miniatures",   "Moving Through Miniatures"),
    ("move_through_terrain",      "Moving Through Terrain"),
    ("my_mood_is_based_on_profit","My Mood is Based on Profit"),
    # N
    ("nimble",                    "Nimble"),
    ("noncombatant",              "Noncombatant"),
    ("notch_based_movement",      "Notched Base Movement"),
    ("notched_bases",             "Notched Bases"),
    ("null_courage",              "Null Courage Value"),
    # O
    ("permanent",                 "Permanent"),
    ("objective_cards",           "Objective Cards"),
    ("objective",                 "Objective Tokens"),
    ("observe_x",                 "Observe X[]"),
    ("obstacle_terrain",          "Obstacle Terrain"),
    ("one_step_ahead",            "One Step Ahead"),
    ("open_terrain",              "Open Terrain"),
    ("outmaneuver",               "Outmaneuver"),
    ("overlapping_objects",       "Overlapping Objects"),
    ("override",                  "Override[]"),
    ("overrun_x",                 "Overrun X"),
    # P
    ("panic",                     "Panic"),
    ("pass",                      "Pass Pool"),
    ("pierce_x",                  "Pierce X"),
    ("pivot",                     "Pivot"),
    ("place_order_tokens",        "Place Order Token"),
    ("placing_objectives",        "Placing Objectives"),
    ("plodding",                  "Plodding"),
    ("poi",                       "POI (Point of Interest)"),
    ("poison_x",                  "Poison X"),
    ("precise_x",                 "Precise X"),
    ("prepared_positions",        "Prepared Positions"),
    ("primitive",                 "Primitive"),
    ("programmed",                "Programmed"),
    ("promote",                   "Promote"),
    ("pulling_the_strings",       "Pulling the Strings[]"),
    # Q
    ("quick_thinking",            "Quick Thinking"),
    # R
    ("rally",                     "Rally Step"),
    ("ram_x",                     "Ram"),
    ("range",                     "Range"),
    ("ranks",                     "Ranks and Rank Requirements"),
    ("ready_x",                   "Ready X"),
    ("recharge_x",                "Recharge X"),
    ("recover",                   "Recover"),
    ("regenerate",                "Regenerate X"),
    ("reinforcements",            "Reinforcements"),
    ("relentless",                "Relentless"),
    ("reliable_x",                "Reliable X"),
    ("repair_x",                  "Repair X: Capacity Y[]"),
    ("reposition",                "Reposition"),
    ("repulsor_vehicle",          "Repulsor Vehicles"),
    ("resiliency",                "Resiliency"),
    ("resolve_setup_effecs",      "Resolve Setup Effects"),
    ("restore",                   "Restore"),
    ("retinue_x",                 "Retinue: Unit/Unit Type[]"),
    ("reverse_moves",             "Reverse Moves"),
    ("roll_attack_dice",          "Roll Attack Dice"),
    ("ruthless",                  "Ruthless[]"),
    # S
    ("scale",                     "Scale"),
    ("scatter",                   "Scatter"),
    ("scatter_terrain",           "Scatter Terrain"),
    ("scout_x",                   "Scout X"),
    ("scouting_party_x",          "Scouting Party X"),
    ("secondary_objective_cards", "Secondary Objective Cards"),
    ("secret_information",        "Secret Information"),
    ("secret_mission",            "Secret Mission"),
    ("self_destruct_x",           "Self-Destruct X[]"),
    ("self_preservation",         "Self-Preservation"),
    ("sentinel",                  "Sentinel[]"),
    ("setup",                     "Setup"),
    ("sharpshooter_x",            "Sharpshooter"),
    ("shielded_x",                "Shielded X"),
    ("shien_mastery",             "Shien Mastery"),
    ("sidearm",                   "Sidearm"),
    ("silhouettes",               "Silhouettes"),
    ("small",                     "Small"),
    ("smoke_tokens",              "Smoke Tokens[]"),
    ("smoke_x",                   "Smoke X[]"),
    ("soresu_mastery",            "Soresu Mastery"),
    ("special_issue",             "Special Issue: Battle Force"),
    ("speeder_x",                 "Speeder X"),
    ("spotter_x",                 "Spotter X[]"),
    ("spray",                     "Spray"),
    ("spur",                      "Spur[]"),
    ("standby",                   "Standby[]"),
    ("stationary",                "Stationary"),
    ("steady",                    "Steady"),
    ("strafe",                    "Strafe Move"),
    ("strategize_x",              "Strategize X[]"),
    ("suffering_wounds",          "Suffering Wounds"),
    ("suppression",               "Suppression"),
    ("suppressive",               "Suppressive"),
    ("surge_token",               "Surge token"),
    # T
    ("tactical_x",                "Tactical X"),
    ("take_cover_x",              "Take Cover X[]"),
    ("target_x",                  "Target X"),
    ("teamwork",                  "Teamwork: Unit Name[]"),
    ("tempted",                   "Tempted[]"),
    ("terrain",                   "Terrain"),
    ("terrain_height",            "Terrain Height"),
    ("terrain_cover",             "Terrain Providing Cover"),
    ("terrain_movement",          "Terrain Restricting Movement"),
    ("timing",                    "Timing"),
    ("tokens",                    "Tokens"),
    ("tow_cable",                 "Tow Cable"),
    ("transport",                 "Transport"),
    ("treat_x",                   "Treat X[]"),
    ("trooper",                   "Trooper"),
    # U
    ("uncanny_luck_x",            "Uncanny Luck X"),
    ("unconcerned",               "Unconcerned"),
    ("undeployed_units",          "Undeployed Units"),
    ("unhindered",                "Unhindered"),
    ("unique",                    "Unique and Limited"),
    ("unit_cards",                "Unit Cards"),
    ("unit",                      "Unit Types"),
    ("units",                     "Units"),
    ("unstoppable",               "Unstoppable"),
    ("upgrade_card",              "Upgrade Cards"),
    # V
    ("vaapad_mastery",            "Vaapad Mastery"),
    ("vehicles",                  "Vehicles"),
    ("versatile",                 "Versatile"),
    # W
    ("we_are_not_regs",           "We're Not Regs"),
    ("weak_point_x",              "Weak Point X"),
    ("weapons",                   "Weapons"),
    ("weighed_down",              "Weighed Down"),
    ("wheel_mode",                "Wheel Mode"),
    ("winning",                   "Winning the Game"),
    ("withdraw",                  "Withdraw"),
    ("within_range",              "Within, Completely Within, and Not Within"),
    ("wookiee_trooper",           "Wookiee Trooper"),
    ("wounds",                    "Wound Tokens"),
    ("wound_x",                   "Wound X"),
]


# ── Keyword -> unit card mapping (for card_source display) ───────────────────
# (card_name, faction) tuples — used to build the "card_source" label
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


WIKI_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
LEGIONHQ_CDN     = "https://d2maxvwz12z6fm.cloudfront.net/unitCards/"

# Mapping of SW Legion keyword (base name, no trailing X/value) → unit card webp filename.
# Images are hosted at LEGIONHQ_CDN + filename (URL-encoded spaces as %20).
# Generated from legionhq2.com JS bundle unit data; iconic/recognisable units preferred
# for keywords that appear on many units.
KEYWORD_CARD_IMAGES = {
    "Advanced Targeting":            "Range%20Troopers.webp",
    "Advanced Targeting: Unit Type": "Range%20Troopers.webp",
    "Agile":                         "Jyn%20Erso.webp",
    "AI: Action":                    "B2%20Super%20Battle%20Droids.webp",
    "Aid":                           "Pyke%20Syndicate%20Capo.webp",
    "Aid: Affiliation":              "Pyke%20Syndicate%20Capo.webp",
    "Allies of Convenience":         "Lando%20Calrissian.webp",
    "Arm":                           "AT-RT%20Reb.webp",
    "Armor":                         "AT-ST.webp",
    "Arsenal":                       "Boba%20Fett%20Infamous%20Bounty%20Hunter.webp",
    "Associate":                     "Seventh%20Sister.webp",
    "Associate: Unit Name":          "Seventh%20Sister.webp",
    "Ataru Mastery":                 "Yoda.webp",
    "Attack":                        "Darth%20Vader%20Dark%20Lord%20of%20the%20Sith.webp",
    "Attack Run":                    "Raddaugh%20Gnasp%20Fluttercraft%20Attack%20Craft.webp",
    "Barrage":                       "AAT%20Battle%20Tank.webp",
    "Blast":                         "DSD1%20Dwarf%20Spider%20Droid.webp",
    "Block":                         "Luke%20Skywalker%20Hero%20of%20the%20Rebellion.webp",
    "Bolster":                       "T-Series%20Tactical%20Droid.webp",
    "Bounty":                        "Boba%20Fett%20Infamous%20Bounty%20Hunter.webp",
    "Calculate Odds":                "K-2SO.webp",
    "Charge":                        "Luke%20Skywalker%20Hero%20of%20the%20Rebellion.webp",
    "Climbing":                      "AT-RT%20Reb.webp",
    "Climbing Vehicle":              "AT-RT%20Reb.webp",
    "Clone Trooper":                 "Clone%20Captain%20Rex.webp",
    "Command Vehicle":               "Jedi%20Knight%20Mounted%20Jedi%20General.webp",
    "Compel":                        "Darth%20Vader%20Dark%20Lord%20of%20the%20Sith.webp",
    "Compel: Rank/Unit Type":        "Director%20Orson%20Krennic.webp",
    "Complete the Mission":          "Clone%20Commandos.webp",
    "Coordinate":                    "Rebel%20Veterans.webp",
    "Coordinate: Type/Name":         "Rebel%20Veterans.webp",
    "Cover":                         "74-Z%20Speeder%20Bikes.webp",
    "Creature Trooper":              "Tauntaun%20Riders.webp",
    "Critical":                      "DF-90%20Mortar%20Trooper.webp",
    "Cunning":                       "Director%20Orson%20Krennic.webp",
    "Danger Sense":                  "Cad%20Bane.webp",
    "Dauntless":                     "Black%20Sun%20Vigo.webp",
    "Death from Above":              "Sun%20Fac.webp",
    "Death From Above":              "Sun%20Fac.webp",
    "Defend":                        "Ahsoka%20Tano.webp",
    "Deflect":                       "Darth%20Vader%20Dark%20Lord%20of%20the%20Sith.webp",
    "Demoralize":                    "Savage%20Opress%20Maul%27s%20Enforcer.webp",
    "Detachment":                    "DF-90%20Mortar%20Trooper.webp",
    "Detachment: Name/Type":         "Rebel%20Commandos%20Strike%20Team.webp",
    "Direct":                        "Count%20Dooku.webp",
    "Disciplined":                   "Seventh%20Sister.webp",
    "Disengage":                     "Jyn%20Erso.webp",
    "Distract":                      "Plo%20Koon.webp",
    "Divine Influence":              "C-3PO%20Golden%20God.webp",
    "Djem So Mastery":               "Anakin%20Skywalker.webp",
    "Droid Trooper":                 "B2%20Super%20Battle%20Droids.webp",
    "Duelist":                       "Wookiee%20Chieftain.webp",
    "Emplacement Trooper":           "1.4%20FD%20Laser%20Cannon%20Team.webp",
    "Enrage":                        "Chewbacca%20Walking%20Carpet.webp",
    "Entourage":                     "General%20Grievous%20Sinister%20Cyborg.webp",
    "Entourage: Unit Name":          "Director%20Orson%20Krennic.webp",
    "Equip":                         "Clone%20Commandos.webp",
    "Exemplar":                      "Leia%20Organa.webp",
    "Expert Climber":                "AT-RT%20Reb.webp",
    "Field Commander":               "Cassian%20Andor.webp",
    "Fire Support":                  "DF-90%20Mortar%20Trooper.webp",
    "Fixed":                         "Persuader-Class%20Tank%20Droid.webp",
    "Fixed: Front/Rear":             "LAAT%20Patrol%20Transport%20R.webp",
    "Flexible Response":             "Guerilla%20Troopers.webp",
    "Full Pivot":                    "DF-90%20Mortar%20Trooper.webp",
    "Generator":                     "Droidekas.webp",
    "Guardian":                      "Chewbacca%20Walking%20Carpet.webp",
    "Guidance":                      "General%20Veers.webp",
    "Gunslinger":                    "Han%20Solo.webp",
    "Heavy Weapon Team":             "Mandalorian%20Warriors%20Fire%20Support.webp",
    "High Velocity":                 "AAT%20Battle%20Tank.webp",
    "Hold the Line":                 "Riot%20Control%20Squad.webp",
    "Hover":                         "Saber-Class%20Tank.webp",
    "Hover: Ground/Air":             "Saber-Class%20Tank.webp",
    "Hunted":                        "Grogu.webp",
    "Impact":                        "Luke%20Skywalker%20Hero%20of%20the%20Rebellion.webp",
    "Immune: Blast":                 "T-47%20Airspeeder.webp",
    "Immune: Keyword":               "Luke%20Skywalker%20Hero%20of%20the%20Rebellion.webp",
    "Immune: Melee":                 "T-47%20Airspeeder.webp",
    "Immune: Melee Pierce":          "Agent%20Kallus.webp",
    "Immune: Pierce":                "Darth%20Vader%20Dark%20Lord%20of%20the%20Sith.webp",
    "Immune: Range 1 Weapons":       "T-47%20Airspeeder.webp",
    "Impervious":                    "Boba%20Fett%20Infamous%20Bounty%20Hunter.webp",
    "Incognito":                     "K-2SO.webp",
    "Inconspicuous":                 "R2-D2%20Hero%20of%20a%20Thousand%20Devices.webp",
    "Inconspicious":                 "R2-D2%20Hero%20of%20a%20Thousand%20Devices.webp",
    "Independent":                   "Boba%20Fett%20Infamous%20Bounty%20Hunter.webp",
    "Independent: Token X/Action":   "Jyn%20Erso.webp",
    "Indomitable":                   "Wookiee%20Chieftain.webp",
    "Infiltrate":                    "Cassian%20Andor.webp",
    "Inspire":                       "Leia%20Organa.webp",
    "Interrogate":                   "Agent%20Kallus.webp",
    "Ion":                           "Persuader-Class%20Tank%20Droid.webp",
    "Jar'Kai Mastery":               "Asajj%20Ventress.webp",
    "Jedi Hunter":                   "General%20Grievous%20Sinister%20Cyborg.webp",
    "Jump":                          "Luke%20Skywalker%20Hero%20of%20the%20Rebellion.webp",
    "Juyo Mastery":                  "Maul%20Impatient%20Apprentice.webp",
    "Lethal":                        "Chewbacca%20Walking%20Carpet.webp",
    "Long Shot":                     "Luke%20Skywalker%20Hero%20of%20the%20Rebellion.webp",
    "Low Profile":                   "Han%20Solo.webp",
    "Makashi Mastery":               "Count%20Dooku.webp",
    "Marksman":                      "Iden%20Versio.webp",
    "Master Storyteller":            "C-3PO%20Golden%20God.webp",
    "Master of the Force":           "Darth%20Vader%20Dark%20Lord%20of%20the%20Sith.webp",
    "Mercenary":                     "Boba%20Fett%20Infamous%20Bounty%20Hunter.webp",
    "Mercenary: Faction":            "Boba%20Fett%20Infamous%20Bounty%20Hunter.webp",
    "Mobile":                        "TSMEU-6%20Wheel%20Bikes.webp",
    "My Mood is Based on Profit":    "Hondo%20Ohnaka.webp",
    "Nimble":                        "Leia%20Organa.webp",
    "Observe":                       "Clone%20Commander%20Cody.webp",
    "One Step Ahead":                "Grand%20Admiral%20Thrawn.webp",
    "Outmaneuver":                   "Saber-Class%20Tank.webp",
    "Overrun":                       "Swoop%20Bike%20Riders.webp",
    "Override":                      "Kraken.webp",
    "Pierce":                        "Han%20Solo.webp",
    "Plodding":                      "Imperial%20Dark%20Troopers.webp",
    "Poison":                        "Savage%20Opress%20Maul%27s%20Enforcer.webp",
    "Precise":                       "Stormtroopers.webp",
    "Prepared Position":             "DF-90%20Mortar%20Trooper.webp",
    "Primitive":                     "Wicket.webp",
    "Programmed":                    "IG-11.webp",
    "Pulling the Strings":           "Grand%20Moff%20Tarkin.webp",
    "Quick Thinking":                "Iden%20Versio.webp",
    "Ram":                           "Tauntaun%20Riders.webp",
    "Ready":                         "Imperial%20Death%20Troopers.webp",
    "Recharge":                      "Clone%20Commandos.webp",
    "Regenerate":                    "Bossk.webp",
    "Reinforcements":                "Kalani.webp",
    "Relentless":                    "Darth%20Vader%20Dark%20Lord%20of%20the%20Sith.webp",
    "Reliable":                      "Clone%20Trooper%20Infantry.webp",
    "Repair":                        "R2-D2%20Hero%20of%20a%20Thousand%20Devices.webp",
    "Reposition":                    "Tauntaun%20Riders.webp",
    "Retinue":                       "Mandalorian%20Leader.webp",
    "Retinue: Unit/Unit Type":       "Mandalorian%20Resistance%20Clan%20Wren.webp",
    "Ruthless":                      "Moff%20Gideon.webp",
    "Scale":                         "General%20Grievous%20Sinister%20Cyborg.webp",
    "Scout":                         "Scout%20Troopers.webp",
    "Scouting Party":                "Wicket.webp",
    "Secret Mission":                "R2-D2%20Hero%20of%20a%20Thousand%20Devices.webp",
    "Self-Destruct":                 "Imperial%20Probe%20Droid.webp",
    "Self-Preservation":             "Han%20%26%20Chewie.webp",
    "Sentinel":                      "Boba%20Fett%20Daimyo%20of%20Mos%20Espa.webp",
    "Sharpshooter":                  "Scout%20Troopers.webp",
    "Shielded":                      "Droidekas.webp",
    "Shien Mastery":                 "Plo%20Koon.webp",
    "Soresu Mastery":                "Obi-Wan%20Kenobi.webp",
    "Special Issue":                 "Major%20Marquand.webp",
    "Special Issue: Battle Force":   "Stormtroopers%20Heavy%20Response%20Unit.webp",
    "Speeder":                       "74-Z%20Speeder%20Bikes.webp",
    "Spotter":                       "General%20Veers.webp",
    "Spray":                         "Flametrooper.webp",
    "Spur":                          "Han%20Solo%20Reluctant%20Hero.webp",
    "Standby":                       "Rebel%20Troopers.webp",
    "Stationary":                    "1.4%20FD%20Laser%20Cannon%20Team.webp",
    "Steady":                        "Han%20Solo.webp",
    "Strategize":                    "Kraken.webp",
    "Suppressive":                   "Stormtroopers.webp",
    "Tactical":                      "Moff%20Gideon.webp",
    "Take Cover":                    "Leia%20Organa.webp",
    "Target":                        "Clone%20Commander%20Cody.webp",
    "Teamwork":                      "Chewbacca%20Walking%20Carpet.webp",
    "Teamwork: Unit Name":           "Chewbacca%20Walking%20Carpet.webp",
    "Tempted":                       "Anakin%20Skywalker.webp",
    "Transport":                     "A-A5%20Speeder%20Truck%20R.webp",
    "Treat":                         "R2-D2%20Hero%20of%20a%20Thousand%20Devices.webp",
    "Uncanny Luck":                  "Han%20Solo.webp",
    "Unconcerned":                   "Imperial%20Dark%20Troopers.webp",
    "Unhindered":                    "Wicket.webp",
    "Unstoppable":                   "Imperial%20Dark%20Troopers.webp",
    "Vaapad Mastery":                "Mace%20Windu.webp",
    "Versatile":                     "Boba%20Fett%20Infamous%20Bounty%20Hunter.webp",
    "Weak Point":                    "AT-ST.webp",
    "We're Not Regs":                "The%20Bad%20Batch%20Rep.webp",
    "Weighed Down":                  "Poggle%20the%20Lesser.webp",
    "Wheel Mode":                    "Droidekas.webp",
    "Wookiee Trooper":               "Chewbacca%20Walking%20Carpet.webp",
    "Wound":                         "Maul%20A%20Rival.webp",
}



def _kw_lookup_key(keyword_name):
    """Normalise a keyword display name to the lookup key used in KEYWORD_CARD_IMAGES."""
    # Strip trailing [] markers and trailing X (variable value)
    k = re.sub(r"\s*\[\]$", "", keyword_name).strip()
    k = re.sub(r"\s+X$", "", k).strip()
    # Also try without trailing value like "Keyword: Value"
    return k


def _keyword_stem(keyword_name):
    """Normalize a keyword name to a filename stem for card_art/ and manual/ lookups.
    Strips variable placeholders (X), bracket suffixes, and subtype qualifiers."""
    name = re.sub(r'\[.*?\]', '', keyword_name)       # strip [...]
    name = re.sub(r'\s+X\b.*$', '', name, flags=re.I) # strip trailing X (variable placeholder)
    name = re.sub(r'\s*[:/].*$', '', name)             # strip : or / subtypes
    return safe_filename(name.strip(), ext="").rstrip("_")

# Keep old name as alias so any external callers aren't broken
_card_art_stem = _keyword_stem


def find_card_art(keyword_name):
    """Return 'images/<file>' (dist-relative) using the actual on-disk filename from
    OVERRIDES_DIR (case-insensitive match). Checks .png, .webp, .jpg in that order.
    Also copies the file into DIST_IMGDIR so dist/index.html can reference it."""
    import shutil as _shutil
    if not os.path.isdir(CARD_ART_DIR):
        return None
    stem_lower = _keyword_stem(keyword_name).lower()
    try:
        entries = os.listdir(CARD_ART_DIR)
    except OSError:
        return None
    for ext in ('.png', '.webp', '.jpg'):
        for entry in entries:
            name, e = os.path.splitext(entry)
            if name.lower() == stem_lower and e.lower() == ext:
                src = os.path.join(CARD_ART_DIR, entry)
                os.makedirs(DIST_IMGDIR, exist_ok=True)
                dst = os.path.join(DIST_IMGDIR, entry)
                try:
                    _shutil.copy2(src, dst)
                except OSError:
                    pass
                return f"images/{entry}"
    return None


def find_card_art_credit(keyword_name):
    """Return text content of card_art/<stem>.txt if present (up to 1000 chars), else None."""
    if not os.path.isdir(CARD_ART_DIR):
        return None
    stem_lower = _keyword_stem(keyword_name).lower()
    try:
        entries = os.listdir(CARD_ART_DIR)
    except OSError:
        return None
    for entry in entries:
        name, e = os.path.splitext(entry)
        if name.lower() == stem_lower and e.lower() == '.txt':
            try:
                with open(os.path.join(CARD_ART_DIR, entry), encoding='utf-8') as f:
                    return f.read(1000).strip()
            except OSError:
                return None
    return None


def _manual_read(keyword_name, suffix):
    """Return text from manual/<stem><suffix> (case-insensitive), else None."""
    if not os.path.isdir(MANUAL_DIR):
        return None
    stem_lower = _keyword_stem(keyword_name).lower()
    try:
        entries = os.listdir(MANUAL_DIR)
    except OSError:
        return None
    for entry in entries:
        if entry.lower() == stem_lower + suffix:
            try:
                with open(os.path.join(MANUAL_DIR, entry), encoding='utf-8') as f:
                    return f.read().strip()
            except OSError:
                return None
    return None


def find_manual_definition(keyword_name):
    """Return content of manual/<stem>.md if present, else None."""
    return _manual_read(keyword_name, '.md')


def find_manual_summary(keyword_name):
    """Return content of manual/<stem>.summary.md if present, else None."""
    return _manual_read(keyword_name, '.summary.md')


def has_manual_override(keyword_name):
    """True if any manual file exists for this keyword."""
    return find_manual_definition(keyword_name) is not None \
        or find_manual_summary(keyword_name) is not None


def apply_manual_overlays(card_data):
    """Apply manual/ definition and summary files. Manual files always win.
    Returns count of cards that had a definition overridden."""
    applied = 0
    for c in card_data:
        defn = find_manual_definition(c["name"])
        summ = find_manual_summary(c["name"])
        if defn:
            c["definition"] = defn
            c["credit"] = "Manual"
            applied += 1
        if summ:
            c["summary"] = summ
    return applied


def safe_filename(name, ext=".jpg"):
    """Return a safe filename stem + extension."""
    stem = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")[:60]
    return stem + ext


def _get_ext(url):
    """Return '.webp', '.jpg', or '.png' based on the URL."""
    if re.search(r"\.webp", url, re.I):
        return ".webp"
    if re.search(r"\.png", url, re.I):
        return ".png"
    return ".jpg"


def search_images_wiki(keyword_name, max_imgs=2):
    """Fallback: search Wikimedia Commons for images."""
    clean = re.sub(r"\s*[\(\[].*?[\)\]]", "", keyword_name).strip()
    clean = re.sub(r"\s+X$", "", clean).strip()
    search_terms = [f"Star Wars Legion {clean}", f"Star Wars {clean}"]
    found_urls, seen_urls = [], set()
    for term in search_terms:
        if len(found_urls) >= max_imgs:
            break
        try:
            r = requests.get(WIKI_COMMONS_API, headers=HEADERS, timeout=10, params={
                "action": "query", "generator": "search",
                "gsrnamespace": "6", "gsrsearch": term, "gsrlimit": "8",
                "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": "1200",
                "format": "json",
            })
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
            for page in sorted(pages.values(), key=lambda p: p.get("index", 999)):
                info = (page.get("imageinfo") or [{}])[0]
                url  = info.get("thumburl") or info.get("url", "")
                mime = info.get("mime", "")
                if (url and "image" in mime
                        and re.search(r"\.(jpe?g|png)$", url, re.I)
                        and url not in seen_urls):
                    found_urls.append(url)
                    seen_urls.add(url)
                if len(found_urls) >= max_imgs:
                    break
        except Exception:
            pass
        time.sleep(0.3)
    return found_urls


def download_images(keyword_name, imgdir, max_imgs=2):
    """Download images for a keyword.

    Priority:
    1. Use unit card image from legionhq2.com CloudFront CDN if available.
    2. Fall back to Wikimedia Commons search.

    Returns (list_of_relative_paths, already_cached: bool).
    """
    # ── card_art/ folder takes priority over everything ───────────────────────
    art = find_card_art(keyword_name)
    if art:
        return [art], True

    lookup_key = _kw_lookup_key(keyword_name)
    card_filename = KEYWORD_CARD_IMAGES.get(lookup_key)

    # ── Try CloudFront unit card first ────────────────────────────────────────
    if card_filename:
        card_url = LEGIONHQ_CDN + card_filename
        ext      = _get_ext(card_url)
        fname    = safe_filename(keyword_name, ext=ext)
        # Use index 1 only (one authoritative card image per keyword)
        filepath = os.path.join(imgdir, fname)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            return [f"images/{fname}"], True
        try:
            r = requests.get(card_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
            print(f"(card)", end=" ")
            return [f"images/{fname}"], False
        except Exception as exc:
            print(f"(card-fail:{exc})", end=" ")
            # Fall through to Wikimedia

    # ── Wikimedia Commons fallback ────────────────────────────────────────────
    base     = safe_filename(keyword_name, ext="").rstrip("_")
    existing, needed = [], []
    for i in range(1, max_imgs + 1):
        found = None
        for ext in (".png", ".webp", ".jpg"):
            candidate = f"{base}_{i}{ext}"
            fp = os.path.join(imgdir, candidate)
            if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                found = candidate
                break
        if found:
            existing.append(f"images/{found}")
        else:
            fname = f"{base}_{i}.jpg"
            needed.append((i, fname, os.path.join(imgdir, fname)))
    if not needed:
        return existing, True
    urls = search_images_wiki(keyword_name, max_imgs=len(needed))
    saved = list(existing)
    for (i, fname, filepath), url in zip(needed, urls):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(r.content)
            saved.append(f"images/{fname}")
        except Exception:
            pass
    return saved, False



# ── Scrape keywords from legion.takras.net ────────────────────────────────────
def scrape_keyword_page(slug, display_name, session):
    """Fetch a single keyword page and extract type + definition."""
    # Strip trailing [] placeholders that appear in some KEYWORD_PAGES names
    display_name = display_name.replace("[]", "").strip()
    url = f"{BASE}/{slug}/"
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  FETCH ERROR {slug}: {e}")
        return None

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(r.text, "html.parser")

        # ── Replace inline icon <img> elements with readable text ─────────────
        # Icons live at paths like /images/black/<name>.png or /images/tokens/<name>.png
        # The 'title' attribute (when present) is the most reliable label.
        # Fallback: derive label from the filename stem.
        _ICON_TITLE_MAP = {
            # Die-face icons
            "hit":          "[HIT]",
            "hit surge":    "[SURGE: HIT]",
            "hit critical": "[CRIT]",
            "block":        "[BLOCK]",
            "block surge":  "[SURGE: BLOCK]",
            # Range icons
            "range melee":    "[MELEE]",
            "range half":     "[RANGE 1/2]",
            "range 1":        "[RANGE 1]",
            "range 2":        "[RANGE 2]",
            "range 3":        "[RANGE 3]",
            "range 4":        "[RANGE 4]",
            "range 5":        "[RANGE 5]",
            "range infinite": "[RANGE ∞]",
            # Rank icons
            "rank commander": "[COMMANDER]",
            "rank operative": "[OPERATIVE]",
            "rank corps":     "[CORPS]",
            "rank specialist":"[SPECIALIST]",
            "rank support":   "[SUPPORT]",
            "rank heavy":     "[HEAVY]",
            # Courage / misc
            "courage": "[COURAGE]",
        }
        _TOKEN_NAME_MAP = {
            "aim":        "[AIM TOKEN]",
            "dodge":      "[DODGE TOKEN]",
            "surge":      "[SURGE TOKEN]",
            "standby":    "[STANDBY TOKEN]",
            "observation":"[OBSERVATION TOKEN]",
            "smoke":      "[SMOKE TOKEN]",
            "damage":     "[DAMAGE TOKEN]",
            "order":      "[ORDER TOKEN]",
            "commander":  "[COMMANDER TOKEN]",
            "ion":        "[ION TOKEN]",
            "poison":     "[POISON TOKEN]",
            "immobilize": "[IMMOBILIZE TOKEN]",
            "shield":     "[SHIELD TOKEN]",
            "charge":     "[CHARGE TOKEN]",
            "wheel-mode": "[WHEEL MODE TOKEN]",
            "incognito":  "[INCOGNITO TOKEN]",
            "graffiti":   "[GRAFFITI TOKEN]",
            "poi":        "[POI TOKEN]",
            "asset":      "[ASSET TOKEN]",
            "advantage":  "[ADVANTAGE TOKEN]",
        }

        # Remove <head> entirely so the page <title> doesn't pollute the definition
        if soup.head:
            soup.head.decompose()

        for img_tag in soup.find_all("img"):
            src   = img_tag.get("src", "")
            title = (img_tag.get("title") or "").strip().lower()
            alt   = (img_tag.get("alt")   or "").strip().lower()

            replacement = None

            # Check title attribute first (most reliable)
            if title and title in _ICON_TITLE_MAP:
                replacement = _ICON_TITLE_MAP[title]

            # Check token images by src path
            if replacement is None and "/images/tokens/" in src:
                stem = re.sub(r"\.[^.]+$", "", src.rsplit("/", 1)[-1]).lower()
                replacement = _TOKEN_NAME_MAP.get(stem, f"[{stem.upper()} TOKEN]")

            # Check black/ die / range / rank icons by src path
            if replacement is None and "/images/black/" in src:
                stem = re.sub(r"\.[^.]+$", "", src.rsplit("/", 1)[-1]).lower()
                if stem in _ICON_TITLE_MAP:
                    replacement = _ICON_TITLE_MAP[stem]
                elif stem.startswith("range-"):
                    rng = stem[len("range-"):]
                    replacement = f"[RANGE {rng.upper()}]"
                elif stem.startswith("rank-"):
                    rank = stem[len("rank-"):].upper()
                    replacement = f"[{rank}]"
                else:
                    # Generic fallback: use alt or title if available
                    label = (alt or title or stem).upper()
                    replacement = f"[{label}]"

            if replacement:
                img_tag.replace_with(replacement)

        text = soup.get_text(separator="\n", strip=True)
    except Exception as e:
        print(f"  PARSE ERROR {slug}: {e}")
        return None

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # ── Determine keyword type ────────────────────────────────────────────────
    ktype = "concept"
    type_line_idx = -1
    for i, line in enumerate(lines):
        if re.search(r'\bUnit\s+Keyword\b', line, re.I):
            ktype = "unit";    type_line_idx = i; break
        if re.search(r'\bWeapon\s+Keyword\b', line, re.I):
            ktype = "weapon";  type_line_idx = i; break
        if re.search(r'\bUpgrade\s+Keyword\b', line, re.I):
            ktype = "upgrade"; type_line_idx = i; break
        if re.search(r'\bCommand\s+Card\s+Keyword\b', line, re.I):
            ktype = "upgrade"; type_line_idx = i; break

    # ── Extract definition ────────────────────────────────────────────────────
    # Skip header noise, find definition text after the keyword type label
    STOP = {"Related keywords", "Related Keywords", "Get sharable image",
            "Share keyword", "This website uses cookies"}

    def is_stop(line):
        return any(line.startswith(s) for s in STOP)

    def is_noise(line):
        return line in ("Back to Legion Helper", "I am One with the Force",
                        "I'm a Star Wars Muggle", display_name, "×")

    # icon token pattern – short lines produced by our img replacements are valid
    def is_icon_token(line):
        return bool(re.match(r"^\[.+\]$", line))

    # Start collecting after the type line (or after the name if no type line)
    start_idx = type_line_idx + 1 if type_line_idx >= 0 else 0
    definition_parts = []
    for line in lines[start_idx:]:
        if is_stop(line):
            break
        if is_noise(line):
            continue   # skip UI labels / display name, but keep collecting
        # Accept icon tokens regardless of length; otherwise require > 3 chars
        if not line.startswith("http") and (is_icon_token(line) or len(line) > 3):
            definition_parts.append(line)

    # If nothing found yet, fall back: take lines after the display name
    if not definition_parts:
        found_name = False
        for line in lines:
            if is_stop(line):
                break
            if is_noise(line):
                found_name = True
                continue
            if found_name and not line.startswith("http") and (is_icon_token(line) or len(line) > 3):
                definition_parts.append(line)
                if len(definition_parts) >= 12:
                    break

    # Join all parts (icon tokens inline), then truncate to 500 chars
    definition = " ".join(definition_parts).strip()
    # Clean up excess whitespace
    definition = re.sub(r"\s+", " ", definition)
    if len(definition) > 2000:
        definition = definition[:1997] + "..."

    if len(definition) < 15:
        print(f"  WARN: short definition for {display_name!r}")

    return {"name": display_name, "definition": definition, "type": ktype}


def scrape_keywords():
    print("  Fetching keyword definitions from legion.takras.net...")
    try:
        from bs4 import BeautifulSoup  # noqa: confirm available
    except ImportError:
        print("  ERROR: beautifulsoup4 not installed.")
        print("  Run: py -m pip install beautifulsoup4")
        raise

    session  = requests.Session()
    keywords = []
    total    = len(KEYWORD_PAGES)

    for i, (slug, name) in enumerate(KEYWORD_PAGES, 1):
        print(f"  [{i:3d}/{total}] {name[:50]}", end=" ... ", flush=True)
        kw = scrape_keyword_page(slug, name, session)
        if kw and kw["definition"]:
            print(f"OK ({kw['type']})")
            keywords.append(kw)
        else:
            print("SKIP (no definition)")
        time.sleep(0.25)   # be polite to the server

    print(f"\n  Scraped {len(keywords)} / {total} keywords")
    return keywords


def build_unit_db_js():
    """Return a compact JavaScript const UNIT_DB = {...}; string from the LegionHQ2 bundle.

    Downloads and parses the LegionHQ2 JS bundle (cached to legionhq2_units.json next to
    this script). Returns an empty object string if download fails.
    """
    cache_path = os.path.join(CACHE_DIR, "legionhq2_units.json")
    unit_db = None

    # Try loading from cache first
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                unit_db = json.load(f)
            print(f"  (unit DB loaded from cache: {len(unit_db)} units)")
        except Exception:
            unit_db = None

    if unit_db is None:
        print("  Fetching LegionHQ2 unit database...")
        try:
            # Get main bundle URL
            r = requests.get("https://legionhq2.com/list/empire", headers=HEADERS, timeout=15)
            m = re.search(r'src="(/static/js/main\.[^"]+\.js)"', r.text)
            if not m:
                print("  WARN: could not find JS bundle URL")
                return "const UNIT_DB = {};"
            bundle_url = "https://legionhq2.com" + m.group(1)
            print(f"  Fetching bundle: {bundle_url}")
            rb = requests.get(bundle_url, headers=HEADERS, timeout=60)
            rb.raise_for_status()
            content = rb.text

            # Extract JSON
            start_marker = "JSON.parse('"
            start = content.find(start_marker)
            if start < 0:
                print("  WARN: could not find unit JSON in bundle")
                return "const UNIT_DB = {};"
            start += len(start_marker)

            # Find end of JS single-quoted string
            i = start
            json_end = -1
            while i < len(content):
                c = content[i]
                if c == '\\':
                    i += 2
                    continue
                if c == "'":
                    json_end = i
                    break
                i += 1

            if json_end < 0:
                print("  WARN: could not find end of unit JSON")
                return "const UNIT_DB = {};"

            json_str = content[start:json_end]

            # Unescape JS single-quoted string
            def js_unescape(s):
                result = []
                i = 0
                while i < len(s):
                    if s[i] == '\\' and i + 1 < len(s):
                        nc = s[i+1]
                        if nc == '\\': result.append('\\')
                        elif nc == "'": result.append("'")
                        elif nc == '"': result.append('"')
                        elif nc == 'n': result.append('\n')
                        elif nc == 'r': result.append('\r')
                        elif nc == 't': result.append('\t')
                        elif nc == '/': result.append('/')
                        else: result.append('\\'); result.append(nc)
                        i += 2
                    else:
                        result.append(s[i]); i += 1
                return ''.join(result)

            json_decoded = js_unescape(json_str)
            data = json.loads(json_decoded)

            def extract_kw_names(kw_list):
                names = []
                for kw in (kw_list or []):
                    if isinstance(kw, str):
                        names.append(kw)
                    elif isinstance(kw, dict):
                        n = kw.get('name', '')
                        v = kw.get('value')
                        names.append(f"{n} {v}" if v is not None else n)
                return names

            unit_db = {}
            for uid, card in data.items():
                if card.get('cardType') != 'unit':
                    continue
                unit_db[uid] = {
                    'n': card.get('cardName', ''),
                    't': card.get('title', ''),
                    'f': card.get('faction', ''),
                    'r': card.get('rank', ''),
                    'k': extract_kw_names(card.get('keywords', [])),
                    'i': card.get('imageName', ''),
                }

            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(unit_db, f, ensure_ascii=False)
            print(f"  Unit DB: {len(unit_db)} units cached to legionhq2_units.json")

        except Exception as e:
            print(f"  WARN: could not build unit DB: {e}")
            return "const UNIT_DB = {};"

    # Generate compact JS
    lines = ['const UNIT_DB = {']
    for uid, u in sorted(unit_db.items()):
        entry = json.dumps({k: v for k, v in u.items() if v}, ensure_ascii=False)
        # Wrap in uid key
        lines.append(f'  {json.dumps(uid)}:{entry},')
    lines.append('};')
    return '\n'.join(lines)


def next_version():
    vfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.txt")
    try:
        parts = open(vfile).read().strip().split(".")
        major, minor, build = parts[0], parts[1], int(parts[2]) + 1
    except Exception:
        major, minor, build = "4", "3", 1
    ver = f"{major}.{minor}.{build:04d}"
    with open(vfile, "w") as f:
        f.write(ver + "\n")
    return ver

def build_html(card_data):
    template_dir = os.path.join(HERE, 'template')

    # Read template files
    with open(os.path.join(template_dir, 'index.html'), encoding='utf-8') as f:
        html = f.read()
    with open(os.path.join(template_dir, 'app.css'), encoding='utf-8') as f:
        css = f.read()
    with open(os.path.join(template_dir, 'app.js'), encoding='utf-8') as f:
        js = f.read()

    # Stamp data into JS
    fish_js    = json.dumps(card_data, ensure_ascii=False)
    base_names = json.dumps([c["name"] for c in card_data], ensure_ascii=False)
    unit_db_js = build_unit_db_js()
    js = js.replace("/*CARD_JSON*/", fish_js)
    js = js.replace("/*BASE_NAMES*/", base_names)
    js = js.replace("/*UNIT_DB_JSON*/", unit_db_js)

    # Inline into HTML
    html = html.replace("/*STYLE_CSS*/", css)
    html = html.replace("/*APP_JS*/", js)

    # Version
    ver = next_version()
    html = html.replace("v4.3.0001", "v" + ver)
    print(f"  Version: v{ver}")
    return html




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




def main():
    os.makedirs(IMGDIR, exist_ok=True)
    os.makedirs(DIST_IMGDIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    print("=" * 62)
    print("  SW Legion Flashcards Builder v4")
    print("  Keywords: Web Scrape (names+types) + PDF (definitions)")
    print("  Images:   legionhq2.com CDN + Wikimedia Commons")
    print("=" * 62)

    # ── Step 1a: Web scrape for full keyword list (names, types, definitions) ──
    print("\n[1/3] Scraping keywords from legion.takras.net...")
    keywords = []
    try:
        keywords = scrape_keywords()
        print(f"      {len(keywords)} keywords from web scraper")
    except Exception as e:
        print(f"      Scrape failed: {e}")

    # If scrape failed entirely, fall back to bundled
    if not keywords:
        print("      Falling back to bundled keyword definitions...")
        keywords = [{"name": k, "definition": v["definition"], "type": v["type"]}
                    for k, v in BUNDLED_KEYWORDS.items()]
        print(f"      {len(keywords)} bundled keywords")

    # ── Step 1b: Extract official definitions from PDF and overlay ────────────
    pdf_path = find_pdf()
    if pdf_path:
        print(f"\n      Overlaying PDF definitions from {os.path.basename(pdf_path)}...")
        try:
            pdf_dict = extract_keywords_from_pdf(pdf_path)
            if pdf_dict:
                # Normalize lookup: lowercase, strip punctuation
                def _norm(s):
                    return re.sub(r'[^a-z0-9]', '', s.lower())
                pdf_lookup = {_norm(k): v for k, v in pdf_dict.items()}
                overlaid = 0
                for kw in keywords:
                    key = _norm(kw["name"])
                    # Try exact match first, then prefix match
                    match = pdf_lookup.get(key)
                    if not match:
                        for pk, pv in pdf_lookup.items():
                            if pk.startswith(key) or key.startswith(pk):
                                match = pv
                                break
                    if match and match.get("definition"):
                        kw["definition"] = match["definition"]
                        kw["credit"] = "AMG Rulebook v2.6"
                        overlaid += 1
                print(f"      {overlaid}/{len(keywords)} definitions replaced with PDF versions")
            else:
                print("      PDF extraction returned nothing — keeping web definitions")
        except Exception as e:
            print(f"      PDF overlay failed: {e} — keeping web definitions")
    else:
        print("\n      No PDF found — using web definitions only")
        print("      (Place SWQ_Rulebook_2.6.0-1.pdf in documents/ to use official AMG text)")

    # Fill any empty definitions from bundled fallback
    bundled_lookup = {re.sub(r'[^a-z0-9]', '', k.lower()): v
                      for k, v in BUNDLED_KEYWORDS.items()}
    filled = 0
    for kw in keywords:
        if not kw.get("definition") or len(kw["definition"]) < 15:
            key = re.sub(r'[^a-z0-9]', '', kw["name"].lower())
            if key in bundled_lookup:
                kw["definition"] = bundled_lookup[key]["definition"]
                filled += 1
    if filled:
        print(f"      {filled} empty definitions filled from bundled fallback")

    # Apply manual overrides last — they always win
    manual_count = apply_manual_overlays(keywords)
    if manual_count:
        print(f"      {manual_count} definitions overridden from manual/ folder")

    print(f"\n      {len(keywords)} keywords ready")

    # Step 2: Download images
    print(f"\n[2/3] Downloading images from legionhq2.com CDN...")
    print("      (cached files are skipped automatically)\n")

    card_data = []
    failed = []

    for i, kw in enumerate(keywords, 1):
        name = kw["name"]
        print(f"  [{i:3d}/{len(keywords)}] {name[:42]:<42} ", end="", flush=True)
        img_paths, existed = download_images(name, IMGDIR, max_imgs=2)
        if img_paths:
            if existed:
                print(f"skip ({len(img_paths)} cached)")
            else:
                def _imgsize(p):
                    # p is like "images/foo.webp" (dist-relative); file lives in IMGDIR
                    fname = os.path.basename(p)
                    fpath = os.path.join(IMGDIR, fname)
                    return os.path.getsize(fpath) // 1024 if os.path.exists(fpath) else 0
                total_kb = sum(_imgsize(p) for p in img_paths)
                print(f"OK  ({len(img_paths)} imgs, ~{total_kb} KB)")
            time.sleep(0.3)
        else:
            print("no image")
            failed.append(name)
            time.sleep(0.1)

        # Build card_source from KEYWORD_CARDS (v2) if available
        cards_mapping = KEYWORD_CARDS.get(name, [])
        card_source = f"See: {cards_mapping[0][0]}" if cards_mapping else ""

        card_data.append({
            "name":        name,
            "definition":  kw["definition"],
            "summary":     kw.get("summary", ""),
            "type":        kw["type"],
            "imgs":        img_paths,
            "credit":      kw.get("credit", "legion.takras.net"),
            "card_source": card_source,
            "art_credit":  find_card_art_credit(name) or "",
        })

    ok = len(keywords) - len(failed)
    print()
    if failed:
        short = ', '.join(failed[:5]) + ('...' if len(failed) > 5 else '')
        print(f"  No image: {short}")
    print(f"  {ok}/{len(keywords)} keywords have images")

    # --- Inject units field: which units have each keyword ---
    unit_db_path = os.path.join(DATA_DIR, 'unit_db.json')
    if os.path.exists(unit_db_path):
        import re as _re
        from collections import defaultdict as _dd
        with open(unit_db_path, encoding="utf-8") as _f:
            _units = json.load(_f)

        def _norm_cache(name):
            n = _re.sub(r'\s*\[\]$', '', name)
            n = _re.sub(r'\s*:\s*.+$', '', n)
            n = _re.sub(r'\s+X$', '', n)
            n = _re.sub(r'\s+\d+$', '', n)
            return n.strip().lower()

        def _norm_unit(kw):
            n = _re.sub(r'\s+\d+(\s*:\s*.+)?$', '', kw)
            n = _re.sub(r'\s*:\s*.+$', '', n)
            return n.strip().lower()

        _manual = {
            'prepared position': 'Prepared Positions',
            'ai attack': 'AI: Action[]', 'ai dodge': 'AI: Action[]', 'ai move': 'AI: Action[]',
            'hover air': 'Hover: Ground/Air X', 'hover ground': 'Hover: Ground/Air X',
            'immune': 'Immune: Keyword',
            'sharpshooter': 'Sharpshooter',
            'strafe': 'Strafe Move',
            'death from above': 'Death From Above',
            'pull the strings empire trooper': 'Pulling the Strings[]',
            'special issue blizzard force': 'Special Issue: Battle Force',
            'special issue experimental droids': 'Special Issue: Battle Force',
            'special issue tempest force': 'Special Issue: Battle Force',
            'special issue wookiee defenders': 'Special Issue: Battle Force',
            'mercenary': 'Mercenaries',
            'equip': 'Equip', 'associate': 'Associate: Unit Name',
            'aid': 'Backup[]', 'allies of convenience': 'Allies of Convenience',
            'compel': 'Compel: Rank/Unit Type[]',
            'complete the mission': 'Complete the Mission[]',
            'coordinate': 'Coordinate: Type/Name[]',
            'detachment': 'Detachment: Name/Type',
            'direct': 'Direct Name/Type[]',
            'entourage': 'Entourage: Unit Name[]',
            'guidance': 'Guidance[]', 'guardian': 'Guardian X[]',
            'retinue': 'Retinue: Unit/Unit Type[]',
            'teamwork': 'Teamwork: Unit Name[]',
            'bolster': 'Bolster X[]', 'demoralize': 'Demoralize X[]',
            'exemplar': 'Exemplar[]', 'inspire': 'Inspire X[]',
            'observe': 'Observe X[]', 'repair': 'Repair X: Capacity Y[]',
            'self-destruct': 'Self-Destruct X[]', 'sentinel': 'Sentinel[]',
            'smoke': 'Smoke X[]', 'spotter': 'Spotter X[]',
            'spur': 'Spur[]', 'standby': 'Standby[]',
            'strategize': 'Strategize X[]', 'take cover': 'Take Cover X[]',
            'treat': 'Treat X[]', 'tempted': 'Tempted[]',
            'distract': 'Distract[]', 'divine influence': 'Divine Influence[]',
            'interrogate': 'Interrogate[]', 'incognito': 'Incognito[]',
            'inconspicuous': 'Inconspicious', 'override': 'Override[]',
            'ruthless': 'Ruthless[]', 'independent': 'Independent: Token X/Action',
        }

        _cache_lookup = {}
        for _e in card_data:
            _b = _norm_cache(_e['name'])
            if _b not in _cache_lookup:
                _cache_lookup[_b] = _e['name']

        def _find_cache_name(kw):
            base = _norm_unit(kw)
            if base in _manual:
                return _manual[base]
            for pfx, cn in _manual.items():
                if base.startswith(pfx + ' ') or base == pfx:
                    return cn
            return _cache_lookup.get(base)

        _kw_units = _dd(list)
        for _u in _units.values():
            _dname = _u['name']
            for _kw in _u.get('keywords', []):
                _cn = _find_cache_name(_kw)
                if _cn and _dname not in _kw_units[_cn]:
                    _kw_units[_cn].append(_dname)
        for _k in _kw_units:
            _kw_units[_k].sort()
        for _e in card_data:
            _ul = _kw_units.get(_e['name'], [])
            _e['units'] = ', '.join(_ul)
        print(f"      Injected 'units' field ({sum(1 for e in card_data if e.get('units'))} keywords have units)")

    # Save cache so rebuild_html_only.py picks up fresh data
    cache_path = os.path.join(CACHE_DIR, 'card_data.json')
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(card_data, f, ensure_ascii=False, indent=2)
    print(f"\n      Cached {len(card_data)} cards to cache/card_data.json")

    # Copy cached images → dist/images/ (so dist/index.html can reference them)
    import shutil as _shutil2
    img_copied = 0
    for fname in os.listdir(IMGDIR):
        src = os.path.join(IMGDIR, fname)
        dst = os.path.join(DIST_IMGDIR, fname)
        if os.path.isfile(src):
            _shutil2.copy2(src, dst)
            img_copied += 1
    print(f"      Copied {img_copied} images from cache/images/ -> dist/images/")

    # Step 3: Build HTML
    print(f"\n[3/3] Building dist/index.html...")
    html = build_html(card_data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUT) // 1024
    print(f"      dist/index.html  ({kb} KB)")
    print(f"      dist/images/     ({img_copied} images)")
    print()
    print("  Open dist/index.html in your browser.")
    print("  Images are in the dist/images/ folder.")
    print("=" * 62)


if __name__ == "__main__":
    main()
