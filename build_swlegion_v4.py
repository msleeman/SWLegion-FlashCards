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

HERE   = os.path.dirname(os.path.abspath(__file__))
IMGDIR = os.path.join(HERE, 'images')
OUT    = os.path.join(HERE, 'swlegion_flashcards.html')
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
        fname    = f"{base}_{i}.jpg"
        filepath = os.path.join(imgdir, fname)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
            existing.append(f"images/{fname}")
        else:
            needed.append((i, fname, filepath))
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
    cache_path = os.path.join(HERE, "legionhq2_units.json")
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


def build_html(card_data):
    fish_js    = json.dumps(card_data, ensure_ascii=False)
    base_names = json.dumps([c["name"] for c in card_data], ensure_ascii=False)
    unit_db_js = build_unit_db_js()
    html = HTML_TEMPLATE.replace("/*CARD_JSON*/", fish_js)
    html = html.replace("/*BASE_NAMES*/", base_names)
    html = html.replace("/*UNIT_DB_JSON*/", unit_db_js)
    return html



HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SW Legion Keywords</title>
<link rel="icon" type="image/png" href="EmpireCrest.png">
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
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
.screen{position:fixed;inset:0;display:none}
.screen.on{display:block}
#fs-bg{position:absolute;inset:0;background:#0a0a0f;overflow:hidden}
#fs-img{position:absolute;top:68px;left:50%;transform:translateX(-50%);width:auto;height:calc(100% - 68px);max-width:100%;object-fit:contain;object-position:top center;opacity:1;transition:opacity .4s}
#fs-scan{display:none}
#fs-top-grad{display:none}
#fs-bot-grad{display:none}
#fs-flip-zone{position:absolute;inset:0;cursor:pointer;z-index:3}
#fs-topbar{position:absolute;top:0;left:0;right:0;
  padding:14px 205px 0 16px;display:flex;align-items:center;gap:10px;z-index:10;pointer-events:none}
#fs-topbar>*{pointer-events:all}
.fs-pill{background:rgba(0,0,0,.6);backdrop-filter:blur(12px);
  border:1px solid rgba(245,197,24,.25);border-radius:20px;
  color:var(--white);font-size:13px;padding:6px 14px;cursor:pointer;
  transition:all .2s;font-family:inherit}
.fs-pill.active{background:rgba(245,197,24,.2);border-color:var(--gold);color:var(--gold)}
.fs-pill:hover:not(.active){background:rgba(255,255,255,.1)}
.type-badge{font-size:11px;font-weight:700;letter-spacing:.5px;padding:4px 10px;border-radius:20px;text-transform:uppercase}
.type-unit{background:rgba(52,152,219,.25);border:1px solid #3498db;color:#7ec8f5}
.type-weapon{background:rgba(192,57,43,.25);border:1px solid #c0392b;color:#f08080}
.type-upgrade{background:rgba(155,89,182,.25);border:1px solid #9b59b6;color:#d7b4f5}
.type-concept{background:rgba(245,197,24,.15);border:1px solid var(--golddim);color:var(--gold)}
#fs-progress{flex:1;position:relative;height:14px;background:rgba(255,255,255,.06);border-radius:3px;margin:0 8px}
#fs-pfill{position:absolute;bottom:0;left:0;height:2px;width:0%;background:var(--gold);transition:width .3s;border-radius:2px}
#fs-ctr{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);font-size:9px;color:rgba(255,255,255,.45);white-space:nowrap;line-height:1;pointer-events:none;letter-spacing:.5px}
#fs-quiz-stats{display:none;gap:12px;align-items:center}
.fs-stat{color:var(--white2);font-size:13px}
.fs-stat span{font-weight:700;color:var(--white)}
.fs-stat.ok span{color:#6effc4}.fs-stat.wr span{color:#ff8888}
#fs-prev,#fs-next{position:absolute;top:50%;transform:translateY(-50%);
  z-index:10;background:rgba(0,0,0,.55);backdrop-filter:blur(12px);
  border:1px solid rgba(245,197,24,.2);border-radius:50%;
  width:44px;height:44px;display:flex;align-items:center;justify-content:center;
  cursor:pointer;color:var(--gold);font-size:18px;transition:all .2s}
#fs-prev{left:12px}#fs-next{right:12px}
#fs-prev:hover,#fs-next:hover{background:rgba(245,197,24,.15)}
#fs-prev:disabled,#fs-next:disabled{opacity:.2;cursor:default}
#fs-nav-btns{position:absolute;top:14px;right:16px;display:flex;gap:8px;z-index:10}
#fs-bottom{position:absolute;bottom:0;left:0;right:0;max-height:calc(100% - 90px);overflow-y:auto;-webkit-overflow-scrolling:touch;padding:60px 16px 16px;z-index:10;background:linear-gradient(transparent,rgba(0,0,0,.92) 30%)}
#fs-bottom::-webkit-scrollbar{width:4px}
#fs-bottom::-webkit-scrollbar-track{background:transparent}
#fs-bottom::-webkit-scrollbar-thumb{background:rgba(245,197,24,.45);border-radius:2px}
#fs-front-content{display:block}
#fs-keyword-name{font-size:clamp(32px,7vw,64px);font-weight:800;color:var(--gold);line-height:1.1;
  text-shadow:0 0 40px rgba(245,197,24,.4),0 2px 8px rgba(0,0,0,.8);letter-spacing:-0.5px}
#fs-keyword-subtext{font-size:15px;color:var(--white2);margin-top:6px;text-shadow:0 1px 4px rgba(0,0,0,.8)}
#fs-tap-hint{font-size:13px;color:rgba(255,255,255,.4);margin-top:12px;letter-spacing:.5px;font-style:italic}
#fs-back-content{display:none}
#fs-back-name{font-size:22px;font-weight:700;color:var(--gold);margin-bottom:6px}
#fs-notes-col{display:flex;flex-direction:column;gap:4px;margin-bottom:8px}
.fs-notes-label{font-size:10px;font-weight:700;color:rgba(255,255,255,.35);text-transform:uppercase;letter-spacing:.6px}
#fs-notes{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:8px;color:var(--white);font-size:13px;padding:8px 10px;font-family:inherit;resize:none;width:100%;min-height:80px;line-height:1.6;outline:none;box-sizing:border-box}
#fs-notes:focus{border-color:rgba(245,197,24,.6)}
#fs-rules-section{margin-top:2px}
#fs-rules-header{display:flex;align-items:center;gap:8px;cursor:pointer;padding:5px 0;user-select:none;border-top:1px solid rgba(255,255,255,.08)}
#fs-rules-preview{font-size:13px;color:rgba(255,255,255,.45);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#fs-rules-caret{color:var(--gold);font-size:11px;flex-shrink:0;transition:transform .2s}
#fs-definition{display:none;font-size:14px;color:var(--white);line-height:1.7;text-shadow:0 1px 4px rgba(0,0,0,.6);padding-top:6px}
#fs-source{font-size:11px;color:rgba(255,255,255,.3);margin-top:4px}
#fs-actions{display:flex;gap:8px;margin-top:7px;flex-wrap:wrap}
.fs-btn{background:rgba(0,0,0,.55);backdrop-filter:blur(12px);
  border:1px solid rgba(255,255,255,.15);border-radius:var(--rs);
  color:var(--white2);font-size:13px;padding:8px 16px;cursor:pointer;
  font-family:inherit;transition:all .2s}
.fs-btn:hover{background:rgba(255,255,255,.12);color:var(--white)}
.fs-btn.learned{background:rgba(29,158,117,.3);border-color:var(--G);color:var(--Gt)}
.fs-btn.flagged{background:rgba(245,166,35,.2);border-color:var(--A);color:var(--At)}
#fs-status{max-height:0;overflow:hidden;text-align:center;font-size:13px;
  font-weight:500;border-radius:var(--rs);transition:all .25s;margin-bottom:0}
#fs-status.show{max-height:40px;padding:8px 14px;margin-bottom:8px}
#fs-status.ok{background:var(--Gbg);color:var(--Gt);border:1px solid rgba(29,158,117,.3)}
#fs-status.err{background:var(--Rbg);color:var(--Rt);border:1px solid rgba(255,68,68,.3)}
#fs-status.work{background:var(--Abg);color:var(--At);border:1px solid rgba(245,166,35,.3)}
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
#fs-alldone{position:absolute;inset:0;display:none;z-index:20;
  background:rgba(0,0,0,.85);backdrop-filter:blur(20px);
  align-items:center;justify-content:center;flex-direction:column;
  gap:20px;text-align:center;padding:2rem}
#fs-alldone.on{display:flex}
#fs-alldone h2{font-size:32px;color:var(--gold);font-weight:800;text-shadow:0 0 30px rgba(245,197,24,.5)}
#fs-alldone p{color:var(--white2);font-size:15px;max-width:400px;line-height:1.6}
.big-btn{border:none;border-radius:var(--rb);font-size:15px;font-weight:700;
  padding:13px 30px;cursor:pointer;font-family:inherit;transition:all .2s}
.big-btn.gold{background:var(--gold);color:#000}
.big-btn.gold:hover{background:#ffd700;transform:translateY(-1px)}
.big-btn.ghost{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.2);color:var(--white2)}
.big-btn.ghost:hover{background:rgba(255,255,255,.15)}
#catalog-screen{background:#0a0a0f;overflow-y:auto}
.cat-wrap{max-width:960px;margin:0 auto;padding:20px}
.cat-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:12px;flex-wrap:wrap}
.cat-top h1{font-size:20px;font-weight:700;color:var(--gold);text-shadow:0 0 20px rgba(245,197,24,.3)}
.cat-top-btns{display:flex;gap:8px}
.dark-pill{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);
  border-radius:20px;color:var(--white2);font-size:13px;padding:6px 14px;
  cursor:pointer;font-family:inherit;transition:all .2s}
.dark-pill:hover{background:rgba(255,255,255,.12)}
.dark-pill.active{background:rgba(245,197,24,.15);border-color:var(--gold);color:var(--gold)}
.cat-filters{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}
.cat-count{font-size:13px;color:rgba(255,255,255,.3);margin-bottom:12px}
#cat-search{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);border-radius:var(--rs);color:var(--white);font-size:13px;padding:8px 14px;font-family:inherit;outline:none;width:100%;margin-bottom:12px;box-sizing:border-box}
#cat-search:focus{border-color:rgba(245,197,24,.4)}
#cat-search::placeholder{color:rgba(255,255,255,.2)}
#cat-add-row{display:none;flex-wrap:wrap;gap:6px;align-items:center;margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,.07)}
#cat-add-row .add-label{font-size:11px;color:rgba(255,255,255,.35);white-space:nowrap}
.dark-pill.extra-on{background:rgba(245,197,24,.2);border-color:var(--gold);color:var(--gold)}
#mod-def-edit{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:var(--rs);color:var(--white);font-size:13px;padding:10px 12px;font-family:inherit;resize:vertical;width:100%;min-height:120px;line-height:1.6;outline:none;box-sizing:border-box;margin-top:8px;display:none}
#mod-def-edit:focus{border-color:rgba(245,197,24,.5)}
.modal-btn.pin-on{background:rgba(245,197,24,.2);border-color:var(--gold);color:var(--gold)}
.cat-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}
.cat-card{border-radius:var(--rs);overflow:hidden;background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);cursor:pointer;
  transition:transform .15s,box-shadow .15s,border-color .15s;position:relative}
.cat-card:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.5);border-color:rgba(245,197,24,.2)}
.cat-card.lrnd{border-color:rgba(29,158,117,.4);border-width:2px}
.cat-thumb{width:100%;height:100px;object-fit:cover;display:block;background:#0a1020;opacity:.7}
.cat-thumb-ph{width:100%;height:100px;background:linear-gradient(135deg,#0a1020,#1a1a30);
  display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.15);font-size:11px;text-align:center;padding:.5rem}
.cat-lbl{padding:8px 10px}
.cat-name{font-size:12px;font-weight:600;color:var(--white);line-height:1.3}
.cat-type{font-size:10px;color:rgba(255,255,255,.35);margin-top:2px;text-transform:uppercase;letter-spacing:.3px}
.cat-badge{position:absolute;top:6px;right:6px;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px}
.badge-learned{background:var(--G);color:#fff}
.empty-msg{color:rgba(255,255,255,.2);font-size:14px;grid-column:1/-1;padding:3rem 0;text-align:center}
#modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.75);
  z-index:100;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(10px)}
#modal-bg.on{display:flex}
.modal-box{background:#0d1020;border:1px solid rgba(245,197,24,.2);border-radius:var(--rb);
  max-width:540px;width:100%;overflow:hidden;max-height:90vh;overflow-y:auto;
  box-shadow:0 0 40px rgba(245,197,24,.1)}
.modal-photo{width:100%;height:340px;object-fit:contain;display:block;background:#0a1020;opacity:.85}
.modal-photo-ph{width:100%;height:340px;background:linear-gradient(135deg,#0a1020,#1a1a30);
  display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.2);
  font-size:13px;text-align:center;padding:1rem;line-height:1.6}
.modal-body{padding:1.25rem}
.modal-name{font-size:22px;font-weight:800;color:var(--gold)}
.modal-type{font-size:12px;margin-top:4px}
.modal-def{font-size:13px;color:rgba(255,255,255,.75);line-height:1.7;margin-top:.75rem}
.modal-src{font-size:11px;color:rgba(255,255,255,.25);margin-top:.5rem}
.modal-status{font-size:12px;font-weight:500;margin-top:.4rem;min-height:18px}
.modal-status.ok{color:var(--Gt)}.modal-status.err{color:var(--Rt)}.modal-status.work{color:var(--At)}
.modal-acts{display:flex;gap:8px;margin-top:1rem;flex-wrap:wrap}
.modal-btn{padding:9px 18px;border-radius:var(--rs);background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.12);cursor:pointer;font-size:13px;
  font-family:inherit;color:var(--white2);transition:all .15s}
.modal-btn:hover{background:rgba(255,255,255,.12)}
.modal-btn.lrnd{background:rgba(29,158,117,.25);border-color:var(--G);color:var(--Gt);font-weight:600}
.modal-btn.flagd{background:var(--Abg);border-color:var(--A);color:var(--At)}
.modal-btn.cls{margin-left:auto;background:rgba(255,255,255,.04)}
@media(max-width:500px){
  #fs-keyword-name{font-size:28px}
  #fs-opts{grid-template-columns:1fr}
  .cat-grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}
}
/* Lists screen */
.list-panel{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:var(--rb);padding:20px;margin-bottom:20px}
.list-section-title{font-size:16px;font-weight:700;color:var(--gold);margin-bottom:16px}
.list-input-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.list-url-input{flex:1;min-width:200px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:var(--rs);color:var(--white);font-size:13px;padding:10px 14px;font-family:inherit;outline:none}
.list-url-input:focus{border-color:var(--gold)}
.list-name-input{flex:1;min-width:180px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:var(--rs);color:var(--white);font-size:14px;padding:10px 14px;font-family:inherit;outline:none}
.list-name-input:focus{border-color:var(--gold)}
.list-parse-header{display:flex;gap:12px;align-items:center;margin:16px 0 12px;flex-wrap:wrap}
.faction-badge{font-size:11px;font-weight:700;letter-spacing:.5px;padding:4px 12px;border-radius:20px;text-transform:uppercase}
.faction-empire{background:rgba(192,57,43,.25);border:1px solid #c0392b;color:#f08080}
.faction-rebels{background:rgba(52,152,219,.25);border:1px solid #3498db;color:#7ec8f5}
.faction-republic{background:rgba(29,158,117,.25);border:1px solid var(--G);color:var(--Gt)}
.faction-separatists{background:rgba(155,89,182,.25);border:1px solid #9b59b6;color:#d7b4f5}
.faction-mercenary{background:rgba(245,166,35,.25);border:1px solid var(--A);color:var(--At)}
.list-pts{font-size:14px;font-weight:700;color:var(--gold)}
.list-parse-units{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
.list-unit-row{display:flex;align-items:center;gap:10px;padding:8px 12px;background:rgba(255,255,255,.04);border-radius:var(--rs);font-size:13px}
.list-unit-count{background:rgba(245,197,24,.15);border:1px solid rgba(245,197,24,.3);border-radius:6px;padding:2px 8px;color:var(--gold);font-weight:700;font-size:12px}
.list-unit-name{color:var(--white);font-weight:600}
.list-unit-kws{color:rgba(255,255,255,.4);font-size:11px;margin-top:2px}
.list-kw-section{margin:12px 0}
.list-kw-title{font-size:13px;color:rgba(255,255,255,.5);margin-bottom:8px}
.list-kw-tags{display:flex;flex-wrap:wrap;gap:6px}
.kw-tag{font-size:12px;padding:4px 10px;border-radius:12px;background:rgba(245,197,24,.12);border:1px solid rgba(245,197,24,.25);color:var(--gold);cursor:default}
.kw-tag.removable{cursor:pointer;transition:all .15s}
.kw-tag.removable:hover{background:rgba(192,57,43,.3);border-color:#c0392b;color:#f08080}
.list-save-row{display:flex;gap:10px;align-items:center;margin-top:14px;flex-wrap:wrap}
#list-save-status{font-size:13px;margin-top:8px;min-height:20px}
.list-card{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:var(--rs);padding:14px 16px;margin-bottom:10px;display:flex;align-items:center;gap:12px;cursor:pointer;transition:all .15s}
.list-card:hover{background:rgba(255,255,255,.07);border-color:rgba(245,197,24,.2)}
.list-card.active-filter{border-color:var(--gold);background:rgba(245,197,24,.08)}
.list-card-info{flex:1}
.list-card-name{font-size:14px;font-weight:700;color:var(--white);margin-bottom:4px}
.list-card-meta{font-size:12px;color:rgba(255,255,255,.4)}
.list-card-actions{display:flex;gap:6px}
.list-btn-filter{font-size:12px;padding:5px 12px;border-radius:12px;background:rgba(29,158,117,.2);border:1px solid var(--G);color:var(--Gt);cursor:pointer;font-family:inherit}
.list-btn-filter.on{background:rgba(29,158,117,.4)}
.list-btn-edit{font-size:12px;padding:5px 12px;border-radius:12px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);color:var(--white2);cursor:pointer;font-family:inherit}
.list-btn-edit:hover{background:rgba(255,255,255,.12)}
.lists-empty{color:rgba(255,255,255,.25);font-size:14px;text-align:center;padding:2rem 0}
/* List modal */
.list-modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:200;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(10px)}
.list-modal-bg.on{display:flex}
.list-modal-box{background:#0d1020;border:1px solid rgba(245,197,24,.2);border-radius:var(--rb);max-width:600px;width:100%;max-height:90vh;overflow-y:auto;box-shadow:0 0 40px rgba(245,197,24,.08)}
.list-modal-header{display:flex;align-items:flex-start;justify-content:space-between;padding:20px 20px 0;gap:12px}
.list-modal-name{font-size:20px;font-weight:800;color:var(--gold)}
.list-modal-meta{font-size:12px;color:rgba(255,255,255,.4);margin-top:4px}
.list-modal-tabs{display:flex;gap:0;border-bottom:1px solid rgba(255,255,255,.08);margin:12px 0 0;padding:0 20px}
.lm-tab{background:none;border:none;border-bottom:2px solid transparent;color:rgba(255,255,255,.45);font-size:14px;padding:10px 16px;cursor:pointer;font-family:inherit;transition:all .15s;margin-bottom:-1px}
.lm-tab.active{border-bottom-color:var(--gold);color:var(--gold)}
.list-add-kw-row{display:flex;gap:8px;margin-top:14px;align-items:center}
/* List pill dropdown */
#list-dropdown-wrap{position:relative;display:inline-block}
#list-dropdown{position:absolute;top:calc(100% + 6px);left:0;min-width:180px;
  background:#0d1020;border:1px solid rgba(245,197,24,.35);border-radius:10px;
  z-index:200;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.6);display:none}
#list-dropdown.open{display:block}
.list-dd-item{padding:9px 14px;font-size:13px;color:var(--white2);cursor:pointer;
  border-bottom:1px solid rgba(255,255,255,.06);transition:background .15s}
.list-dd-item:last-child{border-bottom:none}
.list-dd-item:hover{background:rgba(245,197,24,.1);color:var(--gold)}
.list-dd-item.active{color:var(--gold);font-weight:600}
.list-dd-item.none-item{color:rgba(255,255,255,.4);font-style:italic}
/* Catalog list dropdown */
#cat-list-dropdown-wrap{position:relative;display:inline-block}
#cat-list-dropdown{position:absolute;top:calc(100% + 6px);left:0;min-width:180px;
  background:#0d1020;border:1px solid rgba(245,197,24,.35);border-radius:10px;
  z-index:200;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.6);display:none}
#cat-list-dropdown.open{display:block}
/* Auth screen */
#auth-screen{position:fixed;inset:0;background:#0a0a0f;z-index:9999;
  display:flex;align-items:center;justify-content:center;padding:1rem}
#auth-screen.hidden{display:none}
.auth-box{width:100%;max-width:380px}
.auth-logo{text-align:center;margin-bottom:28px}
.auth-logo-icon{font-size:40px;margin-bottom:8px}
.auth-logo h1{font-size:24px;font-weight:800;color:var(--gold);text-shadow:0 0 20px rgba(245,197,24,.4)}
.auth-logo p{font-size:12px;color:rgba(255,255,255,.35);margin-top:6px}
.auth-card{background:rgba(255,255,255,.04);border:1px solid rgba(245,197,24,.15);
  border-radius:var(--rb);padding:24px}
.auth-tabs{display:flex;border-bottom:1px solid rgba(255,255,255,.08);margin-bottom:20px}
.auth-tab{background:none;border:none;border-bottom:2px solid transparent;
  color:rgba(255,255,255,.4);font-size:14px;padding:8px 16px;cursor:pointer;
  font-family:inherit;transition:all .15s;margin-bottom:-1px}
.auth-tab.active{border-bottom-color:var(--gold);color:var(--gold)}
.auth-fields{display:flex;flex-direction:column;gap:12px}
.auth-status{font-size:13px;min-height:18px;text-align:center;padding:2px 0}
.auth-status.ok{color:#6effc4}.auth-status.err{color:#f08080}.auth-status.work{color:#ffe0a0}
.auth-divider{text-align:center;font-size:12px;color:rgba(255,255,255,.2);margin:4px 0}
.auth-footer{text-align:center;font-size:11px;color:rgba(255,255,255,.2);margin-top:14px}
/* Account dropdown */
#acct-dropdown-wrap{position:relative;display:inline-block}
#acct-dropdown{position:absolute;top:calc(100% + 6px);right:0;min-width:200px;
  background:#0d1020;border:1px solid rgba(245,197,24,.35);border-radius:10px;
  z-index:300;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.6);display:none}
#acct-dropdown.open{display:block}
.acct-email{padding:10px 14px;font-size:12px;color:rgba(255,255,255,.4);
  border-bottom:1px solid rgba(255,255,255,.08)}
.acct-item{padding:10px 14px;font-size:13px;color:var(--white2);cursor:pointer;
  transition:background .15s}
.acct-item:hover{background:rgba(245,197,24,.1);color:var(--gold)}
.acct-item.danger{color:#f08080}
.acct-item.danger:hover{background:rgba(192,57,43,.2);color:#f08080}
</style>
</head>
<body>

<!-- AUTH SCREEN -->
<div id="auth-screen">
  <div class="auth-box">
    <div class="auth-logo">
      <div class="auth-logo-icon">&#9876;</div>
      <h1>SW Legion Keywords</h1>
      <p>Master every keyword in v2.6</p>
    </div>
    <div class="auth-card">
      <div class="auth-tabs">
        <button id="auth-tab-login"  class="auth-tab active" onclick="setAuthMode('login')">Sign In</button>
        <button id="auth-tab-signup" class="auth-tab"        onclick="setAuthMode('signup')">Create Account</button>
      </div>
      <div class="auth-fields">
        <input type="email"    id="auth-email" class="list-url-input" placeholder="Email address"
               autocomplete="email" onkeydown="if(event.key==='Enter')document.getElementById('auth-pwd').focus()">
        <input type="password" id="auth-pwd"   class="list-url-input" placeholder="Password (min 6 characters)"
               autocomplete="current-password" onkeydown="if(event.key==='Enter')authSubmit()">
        <div id="auth-status" class="auth-status"></div>
        <button id="auth-submit" class="big-btn gold" style="width:100%" onclick="authSubmit()">Sign In</button>
        <div class="auth-divider">&#9472;&#9472; or &#9472;&#9472;</div>
        <button class="big-btn ghost" style="width:100%" onclick="guestMode()">Play as Guest</button>
      </div>
    </div>
    <p class="auth-footer">Guest progress is saved locally on this device only.</p>
  </div>
</div>

<!-- FLASHCARD SCREEN -->
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
      <button class="fs-pill active" id="pill-all"     onclick="setTypeFilter('all')">All</button>
      <button class="fs-pill"        id="pill-unit"    onclick="setTypeFilter('unit')">Unit</button>
      <button class="fs-pill"        id="pill-weapon"  onclick="setTypeFilter('weapon')">Weapon</button>
      <button class="fs-pill"        id="pill-concept" onclick="setTypeFilter('noconcept')">No Concepts</button>
      <div id="list-dropdown-wrap">
        <button class="fs-pill" id="pill-list" onclick="toggleListDropdown()">List: None &#9660;</button>
        <div id="list-dropdown"></div>
      </div>
    </div>
    <div id="fs-progress"><div id="fs-pfill" style="width:0%"></div><span id="fs-ctr"></span></div>
    <div id="fs-quiz-stats">
      <div class="fs-stat ok">&#10003;<span id="sc">0</span></div>
      <div class="fs-stat wr">&#10007;<span id="sw">0</span></div>
    </div>
  </div>
  <div id="fs-nav-btns">
    <button class="fs-pill" onclick="showScreen('catalog-screen')">Catalog</button>
    <button class="fs-pill" id="pill-lists" onclick="showScreen('lists-screen')">Lists</button>
    <div id="acct-dropdown-wrap">
      <button class="fs-pill" id="acct-btn" onclick="toggleAcctDropdown()">&#128100;</button>
      <div id="acct-dropdown">
        <div class="acct-email" id="acct-email-label">Guest mode</div>
        <div class="acct-item" id="acct-signin-item" onclick="showAuthFromApp()" style="display:none">Sign in / Switch account</div>
        <div class="acct-item danger" id="acct-signout-item" onclick="authSignOut()" style="display:none">Sign out</div>
        <div class="acct-item" id="acct-guest-label" style="display:none;cursor:default;color:rgba(255,255,255,.3)">Progress saved locally</div>
      </div>
    </div>
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
      <div id="fs-notes-col">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
          <div class="fs-notes-label">Summary / Notes</div>
          <button class="fs-btn" style="font-size:11px;padding:3px 10px;line-height:1.4" onclick="badSummary()">Bad Summary</button>
        </div>
        <textarea id="fs-notes" placeholder="Add your notes..." maxlength="2000"></textarea>
      </div>
      <div id="fs-rules-section">
        <div id="fs-rules-header" onclick="toggleRulesSection()">
          <span class="fs-notes-label">Rules</span>
          <span id="fs-rules-preview"></span>
          <span id="fs-rules-caret">&#9660;</span>
        </div>
        <div id="fs-definition"></div>
      </div>
      <div id="fs-source"></div>
      <div id="fs-actions"></div>
    </div>
  </div>
  <div id="fs-alldone">
    <div style="font-size:56px">&#9889;</div>
    <h2>All keywords learned!</h2>
    <p>You've mastered all active keywords.<br>Reset or change your filter to continue.</p>
    <button class="big-btn gold" onclick="resetLearned()">Start Over</button>
    <button class="big-btn ghost" onclick="showScreen('catalog-screen')">View Catalog</button>
  </div>
</div>

<!-- CATALOG SCREEN -->
<div class="screen" id="catalog-screen" style="background:#0a0a0f;overflow-y:auto">
  <div class="cat-wrap">
    <div class="cat-top">
      <h1>SW Legion Keywords (v2.6)</h1>
      <div class="cat-top-btns">
        <button class="dark-pill" onclick="showScreen('flashcard-screen')">&#8592; Back</button>
      </div>
    </div>
    <div class="cat-filters" id="cat-filters">
      <button class="dark-pill active" onclick="setCF('all',this)">All</button>
      <button class="dark-pill" onclick="setCF('learned',this)">Learned</button>
      <button class="dark-pill" onclick="setCF('unlearned',this)">Unlearned</button>
      <button class="dark-pill" onclick="setCF('unit',this)">Unit Keywords</button>
      <button class="dark-pill" onclick="setCF('weapon',this)">Weapon Keywords</button>
      <button class="dark-pill" onclick="setCF('concept',this)">Concepts Only</button>
      <button class="dark-pill" onclick="setCF('noconcept',this)">No Concepts</button>
      <div id="cat-list-dropdown-wrap">
        <button class="dark-pill" id="cat-pill-list" onclick="toggleCatListDropdown()">List: None &#9660;</button>
        <div id="cat-list-dropdown"></div>
      </div>
    </div>
    <div id="cat-add-row">
      <span class="add-label">Also include:</span>
      <button class="dark-pill" id="cat-add-unit" onclick="toggleCatExtra('unit',this)">+ Unit</button>
      <button class="dark-pill" id="cat-add-weapon" onclick="toggleCatExtra('weapon',this)">+ Weapon</button>
      <button class="dark-pill" id="cat-add-concept" onclick="toggleCatExtra('concept',this)">+ Concept</button>
      <button class="dark-pill" id="cat-add-pinned" onclick="toggleCatExtra('pinned',this)">&#128204; Pinned</button>
    </div>
    <input type="text" id="cat-search" placeholder="&#128269; Search keywords..." oninput="renderCatalog()">
    <div class="cat-count" id="cat-count"></div>
    <div class="cat-grid" id="cat-grid"></div>
  </div>
</div>

<!-- LISTS SCREEN -->
<div class="screen" id="lists-screen" style="background:#0a0a0f;overflow-y:auto">
  <div class="cat-wrap">
    <div class="cat-top">
      <h1>&#9935; Army Lists</h1>
      <div class="cat-top-btns">
        <button class="dark-pill" onclick="showScreen('flashcard-screen')">&#8592; Back</button>
      </div>
    </div>
    <!-- CREATE -->
    <div class="list-panel" id="list-create-panel">
      <h2 class="list-section-title">Import Army List from LegionHQ2</h2>
      <div class="list-input-row">
        <input type="text" id="list-url-input" class="list-url-input"
               placeholder="Paste LegionHQ2 URL: https://legionhq2.com/list/empire/1000:..."
               autocomplete="off" spellcheck="false">
        <button class="dark-pill" onclick="parseListUrl()">Parse</button>
      </div>
      <div id="list-parse-result" style="display:none">
        <div class="list-parse-header">
          <span id="list-parse-faction-badge" class="faction-badge"></span>
          <span id="list-parse-points" class="list-pts"></span>
          <span id="list-parse-unit-count"></span>
        </div>
        <div id="list-parse-units"></div>
        <div class="list-kw-section">
          <div class="list-kw-title">Keywords in this list (<span id="list-kw-count">0</span>):</div>
          <div id="list-kw-tags" class="list-kw-tags"></div>
        </div>
        <div class="list-save-row">
          <input type="text" id="list-name-input" class="list-name-input" placeholder="List name (e.g. Vader Empire 1000pts)" maxlength="60">
          <button class="big-btn gold" onclick="saveList()">Save List</button>
        </div>
        <div id="list-save-status"></div>
      </div>
    </div>
    <!-- SAVED LISTS -->
    <div class="list-panel" id="list-saved-panel">
      <h2 class="list-section-title">Saved Lists</h2>
      <div id="lists-container"></div>
    </div>
  </div>
</div>

<!-- LIST DETAIL MODAL -->
<div id="list-modal-bg" class="list-modal-bg" onclick="closeListModal(event)">
  <div class="list-modal-box" onclick="event.stopPropagation()">
    <div class="list-modal-header">
      <div>
        <div class="list-modal-name" id="lm-name"></div>
        <div id="lm-meta" class="list-modal-meta"></div>
      </div>
      <button class="dark-pill" onclick="closeListModal()">Close</button>
    </div>
    <div class="list-modal-tabs">
      <button class="lm-tab active" id="lm-tab-kw" onclick="setLmTab('kw')">Keywords</button>
      <button class="lm-tab" id="lm-tab-edit" onclick="setLmTab('edit')">Edit</button>
    </div>
    <div id="lm-tab-kw-panel">
      <div class="list-kw-tags" id="lm-kw-tags" style="padding:16px"></div>
    </div>
    <div id="lm-tab-edit-panel" style="display:none">
      <div style="padding:16px">
        <div style="font-size:13px;color:rgba(255,255,255,.5);margin-bottom:12px">
          Click keywords to remove them, or add new ones below.
        </div>
        <div class="list-kw-tags" id="lm-edit-tags"></div>
        <div class="list-add-kw-row">
          <input type="text" id="lm-add-kw-input" class="list-url-input" style="flex:1"
                 placeholder="Add keyword (type to search)..." autocomplete="off" list="kw-datalist">
          <datalist id="kw-datalist"></datalist>
          <button class="dark-pill" onclick="lmAddKeyword()">Add</button>
        </div>
        <div class="list-save-row" style="margin-top:16px">
          <button class="big-btn gold" onclick="lmSaveEdit()">Save Changes</button>
          <button class="big-btn ghost" style="background:rgba(192,57,43,.2);border-color:#c0392b;color:#f08080" onclick="lmDeleteList()">Delete List</button>
        </div>
        <div id="lm-edit-status" style="margin-top:8px;font-size:13px"></div>
      </div>
    </div>
  </div>
</div>

<!-- MODAL -->
<div id="modal-bg" onclick="closeMod(event)">
  <div class="modal-box" onclick="event.stopPropagation()">
    <div id="mod-img"></div>
    <div class="modal-body">
      <div class="modal-name" id="mod-name"></div>
      <div class="modal-type" id="mod-type"></div>
      <div class="modal-def"  id="mod-def"></div>
      <div class="modal-src" id="mod-src"></div>
      <div class="modal-status" id="mod-st"></div>
      <div class="modal-acts">
        <button class="modal-btn" id="mod-lrnd"  onclick="modToggleLearned()"></button>
        <button class="modal-btn" id="mod-pin"   onclick="modTogglePin()">&#128204; Pin</button>
        <button class="modal-btn" id="mod-add-list" onclick="modShowAddToList()">+ List</button>
        <button class="modal-btn" id="mod-edit"  onclick="modToggleEditDef()">Edit Rules</button>
        <button class="modal-btn" id="mod-photo" onclick="modBadPhoto()">Bad photo</button>
        <button class="modal-btn cls"             onclick="closeMod()">Close</button>
      </div>
      <div id="mod-list-picker" style="display:none;margin-top:8px;background:#0d1020;border:1px solid rgba(245,197,24,.3);border-radius:10px;overflow:hidden"></div>
      <textarea id="mod-def-edit" placeholder="Edit the rules text..." maxlength="2000"></textarea>
      <div id="mod-def-edit-acts" style="display:none;gap:8px;flex-wrap:wrap;margin-top:6px">
        <button class="modal-btn" onclick="modSaveDef()">Save</button>
        <button class="modal-btn" onclick="modResetDef()">Reset to Original</button>
      </div>
    </div>
  </div>
</div>

<script>
const CARDS = /*CARD_JSON*/;
const ST = {};
CARDS.forEach(c => { ST[c.name]={idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',pinned:false}; });

function loadState(){
  try{
    const saved=JSON.parse(localStorage.getItem('swlegion_v1')||'{}');
    Object.keys(saved).forEach(n=>{ if(ST[n]) Object.assign(ST[n],saved[n]); });
  }catch(e){}
}
function saveState(){
  const out={};
  Object.keys(ST).forEach(n=>{ const{idx,learned,flagged,notes,customDef,pinned}=ST[n]; out[n]={idx,learned,flagged,notes:notes||'',customDef:customDef||'',pinned:!!pinned}; });
  localStorage.setItem('swlegion_v1',JSON.stringify(out));
  scheduleSync();
}
function s(n){ return ST[n]||{idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',pinned:false}; }
function ci(c){ const st=s(c.name); return (c.imgs&&c.imgs[st.idx])||(c.imgs&&c.imgs[0])||''; }
function ic(c){ return (c.imgs&&c.imgs.length)||0; }

let _st=null;
function setStatus(msg,cls,ms){
  const el=document.getElementById('fs-status');
  el.textContent=msg; el.className='show '+(cls||'ok');
  clearTimeout(_st); if(ms) _st=setTimeout(()=>{el.textContent='';el.className='';},ms);
}
function clrStatus(){ clearTimeout(_st); const el=document.getElementById('fs-status'); el.textContent='';el.className=''; }

function showScreen(id){
  document.querySelectorAll('.screen').forEach(el=>el.classList.remove('on'));
  document.getElementById(id).classList.add('on');
  if(id==='catalog-screen') renderCatalog();
  if(id==='lists-screen'){ renderSavedLists(); }
}

let typeFilter='all';
let activeListId=null; // flashcard/quiz list filter
let catListId=null;    // catalog list filter (null=inherit, ''=explicit none, id=specific)
const catExtras=new Set(); // extra types union-included when a list filter is active

function setTypeFilter(t){
  typeFilter=t;
  ['all','unit','weapon','concept'].forEach(x=>{
    const el=document.getElementById('pill-'+x); if(el) el.classList.remove('active');
  });
  const activeId = t==='noconcept'?'pill-concept':'pill-'+t;
  const activeEl=document.getElementById(activeId); if(activeEl) activeEl.classList.add('active');
  clrStatus(); initDeck(); render();
}
function filteredCards(){
  let cards=CARDS;
  if(activeListId){
    const lst=getListById(activeListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      const base=CARDS.filter(c=>kwSet.has(c.name.toLowerCase()));
      const extras=CARDS.filter(c=>catExtras.has(c.type));
      const pinned=CARDS.filter(c=>s(c.name).pinned);
      cards=[...new Set([...base,...extras,...pinned])];
    }
  }
  const pinnedAll=CARDS.filter(c=>s(c.name).pinned);
  if(typeFilter==='weapon'){const f=cards.filter(c=>c.type==='weapon');return[...new Set([...f,...pinnedAll])];}
  if(typeFilter==='unit'){const f=cards.filter(c=>c.type==='unit');return[...new Set([...f,...pinnedAll])];}
  if(typeFilter==='noconcept'){const f=cards.filter(c=>c.type!=='concept');return[...new Set([...f,...pinnedAll])];}
  return [...new Set([...cards,...pinnedAll])];
}
function setListFilter(listId){
  activeListId=listId||null;
  savePrefs();
  updateListPillLabel();
  updateCatListPillLabel();
  renderListFilterBadges();
  clrStatus(); initDeck(); render();
}
function clearListFilter(){
  activeListId=null;
  savePrefs();
  updateListPillLabel();
  updateCatListPillLabel();
  renderListFilterBadges();
  clrStatus(); initDeck(); render();
}
function updateListPillLabel(){
  const pill=document.getElementById('pill-list'); if(!pill) return;
  if(activeListId){
    const lst=getListById(activeListId);
    pill.innerHTML=(lst?escHtml(lst.name):'List')+' &#9660;';
    pill.classList.add('active');
  } else {
    pill.innerHTML='List: None &#9660;';
    pill.classList.remove('active');
  }
}
function updateCatListPillLabel(){
  const pill=document.getElementById('cat-pill-list'); if(!pill) return;
  if(catListId===null){
    if(activeListId){
      const lst=getListById(activeListId);
      pill.innerHTML='('+escHtml(lst?lst.name:'?')+') &#9660;';
      pill.classList.add('active');
    } else { pill.innerHTML='List: None &#9660;'; pill.classList.remove('active'); }
  } else if(catListId===''){
    pill.innerHTML='List: None &#9660;'; pill.classList.remove('active');
  } else {
    const lst=getListById(catListId);
    pill.innerHTML=(lst?escHtml(lst.name):'List')+' &#9660;';
    pill.classList.add('active');
  }
}
function toggleListDropdown(){
  const dd=document.getElementById('list-dropdown');
  if(dd.classList.contains('open')){ dd.classList.remove('open'); return; }
  // Build items
  const lists=loadLists();
  let html=`<div class="list-dd-item none-item${!activeListId?' active':''}" onclick="setListFilter(null);document.getElementById('list-dropdown').classList.remove('open')">None</div>`;
  lists.forEach(l=>{
    const active=activeListId===l.id;
    html+=`<div class="list-dd-item${active?' active':''}" onclick="setListFilter('${l.id}');document.getElementById('list-dropdown').classList.remove('open')">${escHtml(l.name)}</div>`;
  });
  if(!lists.length) html+=`<div class="list-dd-item none-item">No lists saved</div>`;
  dd.innerHTML=html;
  dd.classList.add('open');
  // Close on outside click
  setTimeout(()=>{ document.addEventListener('click', function _c(e){ if(!document.getElementById('list-dropdown-wrap').contains(e.target)){ dd.classList.remove('open'); document.removeEventListener('click',_c); } }); },0);
}
function toggleCatListDropdown(){
  const dd=document.getElementById('cat-list-dropdown');
  if(dd.classList.contains('open')){ dd.classList.remove('open'); return; }
  const lists=loadLists();
  let html=`<div class="list-dd-item none-item${catListId===''||(catListId===null&&!activeListId)?' active':''}" onclick="setCatList('');document.getElementById('cat-list-dropdown').classList.remove('open')">None</div>`;
  lists.forEach(l=>{
    const active=catListId===l.id;
    html+=`<div class="list-dd-item${active?' active':''}" onclick="setCatList('${l.id}');document.getElementById('cat-list-dropdown').classList.remove('open')">${escHtml(l.name)}</div>`;
  });
  if(!lists.length) html+=`<div class="list-dd-item none-item">No lists saved</div>`;
  dd.innerHTML=html;
  dd.classList.add('open');
  setTimeout(()=>{ document.addEventListener('click', function _c(e){ if(!document.getElementById('cat-list-dropdown-wrap').contains(e.target)){ dd.classList.remove('open'); document.removeEventListener('click',_c); } }); },0);
}
function setCatList(listId){
  catListId=(listId===undefined)?null:listId;
  savePrefs();
  updateCatListPillLabel();
  updateCatAddRow();
  renderCatalog();
}
function updateCatAddRow(){
  const effectiveId=catListId===null?activeListId:catListId;
  const row=document.getElementById('cat-add-row');
  if(row) row.style.display=effectiveId?'flex':'none';
}
function toggleCatExtra(type,btn){
  if(catExtras.has(type)){ catExtras.delete(type); btn.classList.remove('extra-on'); }
  else { catExtras.add(type); btn.classList.add('extra-on'); }
  renderCatalog();
}
function renderListFilterBadges(){
  document.querySelectorAll('.list-card').forEach(el=>{
    el.classList.toggle('active-filter', el.dataset.listId===activeListId);
  });
  document.querySelectorAll('.list-btn-filter').forEach(el=>{
    el.classList.toggle('on', el.dataset.listId===activeListId);
    el.textContent=el.dataset.listId===activeListId?'Filtering':'Filter';
  });
}

let deck=[],cur=0,mode='learn',revealed=false,answered=false,sc=0,sw=0;
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
  const img=document.getElementById('fs-img');
  const src=ci(c);
  if(src){ img.src=src; img.style.display='block'; }
  else   { img.style.display='none'; }
  showFront(c); renderActions(c);
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
let _rulesOpen=false;
function toggleRulesSection(){
  _rulesOpen=!_rulesOpen;
  const defEl=document.getElementById('fs-definition');
  const caretEl=document.getElementById('fs-rules-caret');
  if(defEl) defEl.style.display=_rulesOpen?'block':'none';
  if(caretEl) caretEl.style.transform=_rulesOpen?'rotate(180deg)':'';
}
function autoSummary(def){
  if(!def) return '';
  if(def.length<=700) return def;
  let t=def.slice(0,700);
  const last=Math.max(t.lastIndexOf(' '),t.lastIndexOf('.'),t.lastIndexOf(','));
  if(last>400) t=t.slice(0,last);
  return t+'\u2026';
}
function badSummary(){
  const c=deck[cur]; if(!c) return;
  const st=s(c.name);
  const def=(st.customDef||c.definition||'').trim();
  if(!def){ setStatus('No definition to summarise','err',2000); return; }
  let text=def.replace(/^[A-Z][A-Z\s\-:]+\s+/,'').trim();
  const sents=(text.match(/[^.!?]+[.!?]+/g)||[text]);
  let summary='';
  for(const sent of sents){
    if(summary.length+sent.length>220) break;
    summary+=sent.trim()+' ';
    if(summary.length>=80) break;
  }
  summary=(summary||text.slice(0,220)).trim();
  st.notes=summary; saveState();
  const el=document.getElementById('fs-notes');
  if(el){ el.value=summary; el.oninput=()=>{ st.notes=el.value; saveState(); }; }
  setStatus('Summary shortened','ok',2000);
}
function cardSource(c){ const st=s(c.name); return st.customDef ? 'Admin' : (c.credit||'legion.takras.net'); }
function showBack(c){
  document.getElementById('fs-front-content').style.display='none';
  document.getElementById('fs-back-content').style.display='block';
  document.getElementById('fs-back-name').innerHTML=c.name+' '+typeBadgeHTML(c.type);
  const st=s(c.name);
  const def=st.customDef||c.definition||'';
  // Notes / Summary
  const notesEl=document.getElementById('fs-notes');
  if(notesEl){
    notesEl.value=(st.notes!==undefined&&st.notes!=='')?st.notes:autoSummary(def);
    notesEl.oninput=()=>{ st.notes=notesEl.value; saveState(); };
  }
  // Rules section (collapsed by default)
  _rulesOpen=false;
  const defEl=document.getElementById('fs-definition');
  const caretEl=document.getElementById('fs-rules-caret');
  const previewEl=document.getElementById('fs-rules-preview');
  if(defEl){ defEl.style.display='none'; defEl.textContent=def; }
  if(caretEl) caretEl.style.transform='';
  if(previewEl){
    const first=(def.match(/^[^.!?]+[.!?]/)||[''])[0].trim();
    previewEl.textContent=first||def.slice(0,80);
  }
  // Source
  const srcEl=document.getElementById('fs-source');
  if(srcEl) srcEl.textContent=cardSource(c);
}
function renderActions(c){
  const st=s(c.name), n=ic(c);
  const sn=c.name.replace(/'/g,"\\'");
  const pl=st.busy?'Fetching...':n>1?`Photo (${st.idx+1}/${n})`:'Bad photo';
  document.getElementById('fs-actions').innerHTML=
    `<button class="fs-btn${st.learned?' learned':''}" onclick="toggleLearned('${sn}')">${st.learned?'Learned':'Mark as learned'}</button>`+
    `<button class="fs-btn${st.flagged?' flagged':''}" onclick="badPhoto('${sn}')">${pl}</button>`;
}
function handleTap(){
  if(mode==='quiz'&&!answered) return;
  if(!revealed){ revealed=true; showBack(deck[cur]); }
  else { if(cur<deck.length-1){ cur++; render(); } }
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
  const pool=filteredCards().filter(x=>x.name!==c.name); shuffle(pool);
  const choices=[c,...pool.slice(0,3)]; shuffle(choices);
  const el=document.getElementById('fs-opts'); el.className='on';
  const sn=c.name.replace(/'/g,"\\'");
  el.innerHTML=choices.map(o=>{
    const on=o.name.replace(/'/g,"\\'");
    return `<button class="fs-opt" onclick="pick(this,'${on}','${sn}')">${o.name}</button>`;
  }).join('');
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
function badPhoto(name){
  const c=CARDS.find(x=>x.name===name), st=s(name);
  if(st.busy) return;
  const n=ic(c);
  if(n>1&&st.idx<n-1){ st.idx++; st.flagged=true; saveState(); setStatus(`Photo ${st.idx+1} of ${n}`,'ok',3000); render(); return; }
  st.busy=true; st.flagged=true;
  setStatus(`Fetching photo for "${name}"...`,'work');
  renderActions(c);
  fetchImage(c).then(r=>{
    st.busy=false;
    if(r==='ok')        setStatus(`Photo loaded!`,'ok',5000);
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

let catFilter='all';
function setCF(v,btn){
  catFilter=v;
  document.querySelectorAll('#cat-filters .dark-pill').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active'); renderCatalog();
}
function renderCatalog(){
  let list=[...CARDS];
  // Apply list filter (catListId===null inherits activeListId)
  const effectiveCatListId=catListId===null?activeListId:catListId;
  if(effectiveCatListId){
    const lst=getListById(effectiveCatListId);
    if(lst){
      const kwSet=new Set(lst.keywords.map(k=>k.toLowerCase()));
      const extras=CARDS.filter(c=>catExtras.has(c.type));
      const pinnedExtra=CARDS.filter(c=>catExtras.has('pinned')&&s(c.name).pinned);
      list=[...new Set([...CARDS.filter(c=>kwSet.has(c.name.toLowerCase())),...extras,...pinnedExtra])];
    }
  }
  if(catFilter==='learned')    list=list.filter(c=>s(c.name).learned);
  if(catFilter==='unlearned')  list=list.filter(c=>!s(c.name).learned);
  if(catFilter==='unit')       list=list.filter(c=>c.type==='unit');
  if(catFilter==='weapon')     list=list.filter(c=>c.type==='weapon');
  if(catFilter==='concept')    list=list.filter(c=>c.type==='concept');
  if(catFilter==='noconcept')  list=list.filter(c=>c.type!=='concept');
  // Search filter
  const q=(document.getElementById('cat-search')?.value||'').toLowerCase().trim();
  if(q) list=list.filter(c=>c.name.toLowerCase().includes(q)||(c.definition||'').toLowerCase().includes(q));
  document.getElementById('cat-count').textContent=`${list.length} keyword${list.length!==1?'s':''}`;
  const g=document.getElementById('cat-grid');
  if(!list.length){ g.innerHTML='<p class="empty-msg">Nothing here.</p>'; return; }
  g.innerHTML=list.map(c=>{
    const st=s(c.name), src=ci(c);
    const sn=c.name.replace(/'/g,"\\'");
    const def=st.customDef||c.definition||'';
    const preview=def.length>90?def.slice(0,90).replace(/\s\S*$/,'')+'\u2026':def;
    const th=src
      ?`<img class="cat-thumb" src="${src}" alt="${c.name}" loading="lazy"
             onerror="this.outerHTML='<div class=cat-thumb-ph>${c.name[0]}</div>'">`
      :`<div class="cat-thumb-ph">${c.name[0]}</div>`;
    return `<div class="cat-card${st.learned?' lrnd':''}" onclick="openMod('${sn}')">
      ${th}
      ${st.learned?'<span class="cat-badge badge-learned">Learned</span>':''}${st.pinned?'<span class="cat-badge" style="background:rgba(245,197,24,.9);color:#000;top:6px;left:6px">&#128204;</span>':''}
      <div class="cat-lbl">
        <div class="cat-name">${c.name}</div>
        <div class="cat-type">${c.type}</div>
        <div style="font-size:10px;color:rgba(255,255,255,.3);margin-top:3px;line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${escHtml(preview)}</div>
      </div>
    </div>`;
  }).join('');
}

let mcard=null;
function openMod(name){
  mcard=CARDS.find(c=>c.name===name);
  renderMod(); document.getElementById('modal-bg').classList.add('on');
}
function renderMod(){
  const c=mcard, st=s(c.name), src=ci(c);
  document.getElementById('mod-img').innerHTML=src
    ?`<img class="modal-photo" src="${src}" alt="${c.name}"
           onerror="this.outerHTML='<div class=modal-photo-ph>No image</div>'">`
    :`<div class="modal-photo-ph">No image — use Bad Photo to fetch one</div>`;
  document.getElementById('mod-name').textContent=c.name;
  document.getElementById('mod-type').innerHTML=typeBadgeHTML(c.type);
  const defText=st.customDef||c.definition;
  document.getElementById('mod-def').textContent=defText;
  document.getElementById('mod-def').style.borderColor=st.customDef?'rgba(245,197,24,.3)':'';
  const modSrc=document.getElementById('mod-src');
  if(modSrc) modSrc.textContent='Source: '+cardSource(c);
  const ml=document.getElementById('mod-lrnd');
  ml.textContent=st.learned?'Learned \u2014 reset':'Mark as learned';
  ml.className='modal-btn'+(st.learned?' lrnd':'');
  const mp=document.getElementById('mod-pin');
  if(mp){ mp.innerHTML=st.pinned?'&#128204; Pinned':'&#128204; Pin'; mp.className='modal-btn'+(st.pinned?' pin-on':''); }
  const mb=document.getElementById('mod-photo');
  mb.textContent=st.busy?'Fetching...':'Bad photo';
  mb.className='modal-btn'+(st.flagged?' flagd':'');
  const editTA=document.getElementById('mod-def-edit');
  const editActs=document.getElementById('mod-def-edit-acts');
  if(editTA){ editTA.style.display='none'; document.getElementById('mod-def').style.display='block'; }
  if(editActs) editActs.style.display='none';
}
function modTogglePin(){
  const st=s(mcard.name); st.pinned=!st.pinned;
  saveState(); renderMod(); renderCatalog();
}
function modToggleEditDef(){
  const editTA=document.getElementById('mod-def-edit');
  const editActs=document.getElementById('mod-def-edit-acts');
  const defEl=document.getElementById('mod-def');
  if(!editTA) return;
  const isOpen=editTA.style.display!=='none';
  if(isOpen){
    editTA.style.display='none';
    if(editActs) editActs.style.display='none';
    defEl.style.display='block';
  } else {
    editTA.value=s(mcard.name).customDef||mcard.definition;
    editTA.style.display='block';
    if(editActs) editActs.style.display='flex';
    defEl.style.display='none';
    editTA.focus();
  }
}
function modSaveDef(){
  const val=document.getElementById('mod-def-edit').value.trim();
  s(mcard.name).customDef=val||'';
  saveState();
  document.getElementById('mod-def').textContent=val||mcard.definition;
  document.getElementById('mod-def').style.borderColor=val?'rgba(245,197,24,.3)':'';
  document.getElementById('mod-def-edit').style.display='none';
  document.getElementById('mod-def-edit-acts').style.display='none';
  document.getElementById('mod-def').style.display='block';
  const modSrc=document.getElementById('mod-src');
  if(modSrc) modSrc.textContent='Source: '+cardSource(mcard);
}
function modResetDef(){
  s(mcard.name).customDef='';
  saveState();
  document.getElementById('mod-def-edit').value=mcard.definition;
  document.getElementById('mod-def').textContent=mcard.definition;
  document.getElementById('mod-def').style.borderColor='';
  const modSrc=document.getElementById('mod-src');
  if(modSrc) modSrc.textContent='Source: '+cardSource(mcard);
}
function modToggleLearned(){ toggleLearned(mcard.name); renderMod(); renderCatalog(); }
async function modBadPhoto(){
  const c=mcard, st=s(c.name);
  if(st.busy) return;
  st.busy=true; st.flagged=true;
  document.getElementById('mod-st').textContent='Fetching...';
  document.getElementById('mod-st').className='modal-status work';
  renderMod();
  const r=await fetchImage(c);
  st.busy=false;
  const el=document.getElementById('mod-st');
  if(r==='ok'){el.textContent='Loaded!';el.className='modal-status ok';}
  else if(r==='none'){el.textContent='No image found';el.className='modal-status err';}
  else{el.textContent='Network error';el.className='modal-status err';}
  saveState(); renderMod(); renderCatalog();
}
function closeMod(e){
  if(e&&!e.target.classList.contains('modal-bg')&&e.target.id!=='modal-bg') return;
  const picker=document.getElementById('mod-list-picker');
  if(picker) picker.style.display='none';
  document.getElementById('modal-bg').classList.remove('on'); mcard=null;
}
function modShowAddToList(){
  const picker=document.getElementById('mod-list-picker');
  if(!picker) return;
  if(picker.style.display!=='none'){ picker.style.display='none'; return; }
  const lists=loadLists();
  const stEl=document.getElementById('mod-st');
  if(!lists.length){
    stEl.textContent='No lists saved yet \u2014 go to Lists to create one.';
    stEl.className='modal-status err'; return;
  }
  const kwName=mcard.name;
  picker.innerHTML=lists.map(l=>{
    const has=(l.keywords||[]).some(k=>k.toLowerCase()===kwName.toLowerCase());
    const id=l.id.replace(/'/g,"\\'");
    return `<div class="list-dd-item${has?' active':''}" onclick="modAddToList('${id}')">`+
      `${escHtml(l.name)}`+
      (has?' <span style="color:var(--G);font-size:11px">&#10003; already in list</span>':'')+
      `</div>`;
  }).join('');
  picker.style.display='block';
}
function modAddToList(listId){
  const lists=loadLists();
  const list=lists.find(l=>l.id===listId);
  if(!list||!mcard) return;
  const kwName=mcard.name;
  const stEl=document.getElementById('mod-st');
  const picker=document.getElementById('mod-list-picker');
  const idx=(list.keywords||[]).findIndex(k=>k.toLowerCase()===kwName.toLowerCase());
  if(idx===-1){
    if(!list.keywords) list.keywords=[];
    list.keywords.push(kwName);
    list.keywords.sort();
    saveLists(lists);
    stEl.textContent=`"${kwName}" added to "${list.name}"`;
    stEl.className='modal-status ok';
  } else {
    stEl.textContent=`Already in "${list.name}"`;
    stEl.className='modal-status work';
  }
  if(picker) picker.style.display='none';
}

// ─── UNIT DATABASE (from LegionHQ2) ──────────────────────────────────────────
/*UNIT_DB_JSON*/

// ─── ARMY LIST PARSING ───────────────────────────────────────────────────────
function parseUnitCode(code){
  // Format: {count}{2-char-unit-id}{upgrade-tokens...}
  // upgrade token: '0' = empty slot, otherwise 2 chars = upgrade ID
  let i=0;
  const count=parseInt(code[i++])||1;
  const unitId=code.slice(i,i+2); i+=2;
  const upgrades=[];
  while(i<code.length){
    if(code[i]==='0'){ upgrades.push(null); i++; }
    else{ upgrades.push(code.slice(i,i+2)); i+=2; }
  }
  return {count,unitId,upgrades};
}

function parseLegionHQUrl(url){
  // URL format: https://legionhq2.com/list/{faction}/{points}:{codes}
  // codes = comma-separated unit codes and card IDs
  try{
    const m=url.match(/legionhq2\.com\/list\/([^/]+)\/([^/?#]+)/);
    if(!m) return null;
    const faction=m[1];
    const hashPart=m[2];
    const colonIdx=hashPart.indexOf(':');
    if(colonIdx<0) return null;
    const points=parseInt(hashPart.slice(0,colonIdx))||0;
    const codes=hashPart.slice(colonIdx+1).split(',');
    return {faction,points,codes};
  }catch(e){ return null; }
}

function getUnitFromCode(code){
  const unit=UNIT_DB[code];
  if(unit) return unit; // direct card reference (command/battle card)
  return null;
}

// Normalize keyword base name (strip trailing numbers)
function kwBase(kw){
  return kw.replace(/\s+\d+(\s+.*)?$/,'').replace(/\s*:\s*.+$/,function(m){
    // keep colon for keywords that are defined with subtypes like "Immune: Pierce"
    return m;
  }).trim();
}

function decodeArmy(url){
  const parsed=parseLegionHQUrl(url);
  if(!parsed) return null;
  const {faction,points,codes}=parsed;
  const units=[];
  const allKeywords=new Set();

  for(const code of codes){
    // Check if it's a direct card ID (command/battle - 2 chars, no count prefix)
    if(UNIT_DB[code]){
      // standalone card - skip (command cards, battle cards)
      continue;
    }
    // Try to parse as unit code
    if(code.length<3) continue;
    const firstChar=code[0];
    if(!/[0-9]/.test(firstChar)) continue; // must start with count digit
    const {count,unitId,upgrades}=parseUnitCode(code);
    const unit=UNIT_DB[unitId];
    if(!unit) continue;
    units.push({count,unit,unitId,upgrades});
    // Collect keywords
    (unit.k||[]).forEach(kw=>{
      const base=kw.replace(/\s+\d+(\s+.*)?$/,'').trim();
      allKeywords.add(base);
    });
  }

  return {faction,points,units,keywords:[...allKeywords].sort()};
}

// ─── LIST PERSISTENCE ─────────────────────────────────────────────────────────
function loadLists(){
  try{ return JSON.parse(localStorage.getItem('swlegion_lists')||'[]'); }
  catch(e){ return []; }
}
function saveLists(lists){
  localStorage.setItem('swlegion_lists',JSON.stringify(lists));
  scheduleSync();
}
function getListById(id){
  return loadLists().find(l=>l.id===id)||null;
}

// ─── LISTS SCREEN ─────────────────────────────────────────────────────────────
let _parsedArmy=null;

function parseListUrl(){
  const url=document.getElementById('list-url-input').value.trim();
  if(!url){ showListStatus('Please enter a LegionHQ2 URL','err'); return; }
  if(!url.includes('legionhq2.com')){
    showListStatus('URL must be from legionhq2.com','err'); return;
  }
  _parsedArmy=decodeArmy(url);
  if(!_parsedArmy){
    showListStatus('Could not parse URL. Make sure it includes the list hash.','err'); return;
  }
  renderParseResult(_parsedArmy, url);
}

function renderParseResult(army, url){
  const panel=document.getElementById('list-parse-result');
  panel.style.display='block';

  // Faction badge
  const fb=document.getElementById('list-parse-faction-badge');
  fb.textContent=army.faction.toUpperCase();
  fb.className='faction-badge faction-'+army.faction.toLowerCase();
  document.getElementById('list-parse-points').textContent=army.points+' pts';
  document.getElementById('list-parse-unit-count').textContent=army.units.length+' unit types';

  // Units
  const unitsEl=document.getElementById('list-parse-units');
  unitsEl.innerHTML=army.units.map(({count,unit,unitId})=>{
    const kws=(unit.k||[]).map(k=>k.replace(/\s+\d+(\s+.*)?$/,'').trim()).slice(0,3).join(', ');
    const title=unit.t?` <em style="color:rgba(255,255,255,.4);font-size:11px">${unit.t}</em>`:'';
    return `<div class="list-unit-row">
      <span class="list-unit-count">${count}x</span>
      <div><div class="list-unit-name">${unit.n}${title}</div>
      ${kws?`<div class="list-unit-kws">${kws}${(unit.k||[]).length>3?'...':''}</div>`:''}
      </div></div>`;
  }).join('');

  // Keywords
  document.getElementById('list-kw-count').textContent=army.keywords.length;
  const tagsEl=document.getElementById('list-kw-tags');
  tagsEl.innerHTML=army.keywords.map(kw=>`<span class="kw-tag">${escHtml(kw)}</span>`).join('');

  // Pre-fill list name
  const defaultName=army.faction.charAt(0).toUpperCase()+army.faction.slice(1)+' '+army.points+'pts';
  document.getElementById('list-name-input').value=defaultName;
  document.getElementById('list-save-status').textContent='';
}

function saveList(){
  if(!_parsedArmy){ showListStatus('Parse a URL first','err'); return; }
  const name=document.getElementById('list-name-input').value.trim();
  if(!name){ showListStatus('Enter a list name','err'); return; }
  const url=document.getElementById('list-url-input').value.trim();

  const lists=loadLists();
  const id='lst_'+Date.now();
  lists.push({
    id, name,
    faction:_parsedArmy.faction,
    points:_parsedArmy.points,
    keywords:_parsedArmy.keywords,
    armyUrl:url,
    createdAt:new Date().toISOString()
  });
  saveLists(lists);
  showListStatus('List saved!','ok');
  _parsedArmy=null;
  document.getElementById('list-url-input').value='';
  document.getElementById('list-parse-result').style.display='none';
  renderSavedLists();
  updateListPillLabel();
}

function showListStatus(msg,cls){
  const el=document.getElementById('list-save-status');
  el.textContent=msg;
  el.style.color=cls==='err'?'#f08080':'#6effc4';
}

function renderSavedLists(){
  const lists=loadLists();
  const el=document.getElementById('lists-container');
  if(!lists.length){
    el.innerHTML='<div class="lists-empty">No lists saved yet. Import one above.</div>';
    return;
  }
  el.innerHTML=lists.map(lst=>{
    const isActive=activeListId===lst.id;
    return `<div class="list-card${isActive?' active-filter':''}" data-list-id="${lst.id}" onclick="openListModal('${lst.id}')">
      <div class="list-card-info">
        <div class="list-card-name">${escHtml(lst.name)}</div>
        <div class="list-card-meta">
          <span class="faction-badge faction-${lst.faction||''}" style="font-size:10px;padding:2px 8px">${(lst.faction||'').toUpperCase()}</span>
          &nbsp;${lst.points||0} pts &nbsp;&#183;&nbsp; ${lst.keywords.length} keywords
        </div>
      </div>
      <div class="list-card-actions" onclick="event.stopPropagation()">
        <button class="list-btn-filter${isActive?' on':''}" data-list-id="${lst.id}"
          onclick="toggleListFilter('${lst.id}')">${isActive?'Filtering':'Filter'}</button>
        <button class="list-btn-edit" onclick="openListModal('${lst.id}')">Edit</button>
      </div>
    </div>`;
  }).join('');
}

function toggleListFilter(listId){
  if(activeListId===listId){
    setListFilter(null);
  } else {
    setListFilter(listId);
    showScreen('flashcard-screen');
  }
}

// kept for compatibility - just refreshes pill labels
function updateListSelectDropdown(){ updateListPillLabel(); updateCatListPillLabel(); }

// ─── LIST MODAL ───────────────────────────────────────────────────────────────
let _lmListId=null;
let _lmEditKws=[];

function openListModal(listId){
  _lmListId=listId;
  const lst=getListById(listId);
  if(!lst) return;
  _lmEditKws=[...lst.keywords];
  document.getElementById('lm-name').textContent=lst.name;
  document.getElementById('lm-meta').innerHTML=
    `<span class="faction-badge faction-${lst.faction||''}" style="font-size:10px;padding:2px 7px">${(lst.faction||'').toUpperCase()}</span>`+
    ` &nbsp;${lst.points||0} pts &nbsp;&#183;&nbsp; ${lst.keywords.length} keywords`;

  // KW tab
  document.getElementById('lm-kw-tags').innerHTML=
    lst.keywords.map(kw=>`<span class="kw-tag">${escHtml(kw)}</span>`).join('');

  setLmTab('kw');
  document.getElementById('list-modal-bg').classList.add('on');
}

function closeListModal(e){
  if(e&&e.target.id!=='list-modal-bg') return;
  document.getElementById('list-modal-bg').classList.remove('on');
  _lmListId=null;
}

function setLmTab(tab){
  document.getElementById('lm-tab-kw').classList.toggle('active',tab==='kw');
  document.getElementById('lm-tab-edit').classList.toggle('active',tab==='edit');
  document.getElementById('lm-tab-kw-panel').style.display=tab==='kw'?'block':'none';
  document.getElementById('lm-tab-edit-panel').style.display=tab==='edit'?'block':'none';
  if(tab==='edit') renderLmEditTags();
}

function renderLmEditTags(){
  const el=document.getElementById('lm-edit-tags');
  el.innerHTML=_lmEditKws.map((kw,i)=>
    `<span class="kw-tag removable" onclick="lmRemoveKw(${i})" title="Remove">${escHtml(kw)} &#215;</span>`
  ).join('');
  // Populate datalist
  const dl=document.getElementById('kw-datalist');
  const existing=new Set(_lmEditKws.map(k=>k.toLowerCase()));
  dl.innerHTML=CARDS.map(c=>c.name).filter(n=>!existing.has(n.toLowerCase()))
    .map(n=>`<option value="${escHtml(n)}">`).join('');
}

function lmRemoveKw(idx){
  _lmEditKws.splice(idx,1);
  renderLmEditTags();
}

function lmAddKeyword(){
  const inp=document.getElementById('lm-add-kw-input');
  const val=inp.value.trim();
  if(!val) return;
  if(!_lmEditKws.map(k=>k.toLowerCase()).includes(val.toLowerCase())){
    _lmEditKws.push(val);
    renderLmEditTags();
  }
  inp.value='';
}

function lmSaveEdit(){
  const lists=loadLists();
  const idx=lists.findIndex(l=>l.id===_lmListId);
  if(idx<0) return;
  lists[idx].keywords=[..._lmEditKws];
  saveLists(lists);
  // Refresh view
  openListModal(_lmListId);
  setLmTab('kw');
  renderSavedLists();
  updateListPillLabel();
  // Update active filter if needed
  if(activeListId===_lmListId){ clrStatus(); initDeck(); render(); }
  document.getElementById('lm-edit-status').textContent='Saved!';
  document.getElementById('lm-edit-status').style.color='#6effc4';
}

function lmDeleteList(){
  if(!confirm('Delete this list?')) return;
  let lists=loadLists();
  lists=lists.filter(l=>l.id!==_lmListId);
  saveLists(lists);
  if(activeListId===_lmListId) setListFilter(null);
  document.getElementById('list-modal-bg').classList.remove('on');
  renderSavedLists();
  updateListPillLabel();
}

function escHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ─── SUPABASE AUTH & CLOUD SYNC ───────────────────────────────────────────────
const SUPA_URL = 'https://ddpretixfmrvkhyllcbm.supabase.co';
const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRkcHJldGl4Zm1ydmtoeWxsY2JtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU0NDA5NTUsImV4cCI6MjA5MTAxNjk1NX0.VFSG5ybkTu2pUW4Yjw9GN8r4Vl1CQt59w4tXlJ-hwoU';
let _supa = null, _currentUser = null, _syncTimer = null, _isGuest = false;
let _authReady = false; // tracks whether initAuth completed

function _timeout(ms, label){
  return new Promise((_,rej)=>setTimeout(()=>rej(new Error(label+' timed out after '+ms+'ms')),ms));
}

function initSupabase(){
  try{
    console.log('[AUTH] Creating Supabase client...');
    _supa = supabase.createClient(SUPA_URL, SUPA_KEY);
    console.log('[AUTH] Supabase client created OK');
  }catch(e){
    console.error('[AUTH] Supabase init FAILED:', e);
  }
}

async function initAuth(){
  console.log('[AUTH] initAuth starting...');
  initSupabase();
  if(!_supa){ console.warn('[AUTH] No client, going guest'); guestMode(); return; }

  // Register auth state listener
  _supa.auth.onAuthStateChange(async (event, session)=>{
    console.log('[AUTH] onAuthStateChange:', event, session?.user?.email||'no user');
    if(event==='SIGNED_IN' && session){
      _currentUser = session.user; _isGuest = false;
      console.log('[AUTH] SIGNED_IN — loading cloud state...');
      await loadCloudState();
      hideAuthScreen();
      startApp();
    } else if(event==='SIGNED_OUT'){
      _currentUser = null;
      console.log('[AUTH] SIGNED_OUT');
    }
  });

  // Check for existing session (with timeout so it never blocks forever)
  try{
    console.log('[AUTH] Calling getSession...');
    const t0 = Date.now();
    const { data, error } = await Promise.race([
      _supa.auth.getSession(),
      _timeout(5000, 'getSession')
    ]);
    console.log('[AUTH] getSession completed in', Date.now()-t0, 'ms',
      data?.session ? 'HAS SESSION ('+data.session.user.email+')' : 'no session',
      error || '');
    if(data?.session){
      _currentUser = data.session.user; _isGuest = false;
      await loadCloudState();
      hideAuthScreen();
      startApp();
    }
  }catch(e){
    console.warn('[AUTH] getSession failed:', e.message);
  }
  _authReady = true;
  console.log('[AUTH] initAuth complete, _authReady=true');
  // Always ensure auth screen is visible if no user
  if(!_currentUser) showAuthScreen();
}

function savePrefs(){
  try{ localStorage.setItem('swlegion_prefs',JSON.stringify({activeListId:activeListId,catListId:catListId})); }catch(e){}
}
function loadPrefs(){
  try{
    const p=JSON.parse(localStorage.getItem('swlegion_prefs')||'{}');
    if(p.activeListId!==undefined) activeListId=p.activeListId;
    if(p.catListId!==undefined) catListId=p.catListId;
  }catch(e){}
}
function startApp(){
  console.log('[AUTH] startApp, user:', _currentUser?.email||'guest');
  loadState();
  loadPrefs();
  updateListPillLabel();
  updateCatListPillLabel();
  updateCatAddRow();
  updateAccountUI();
  setMode('learn');
}

async function loadCloudState(){
  if(!_supa || !_currentUser) return;
  try{
    console.log('[AUTH] loadCloudState for', _currentUser.id);
    const t0 = Date.now();
    const { data, error } = await Promise.race([
      _supa.from('user_state').select('card_states,army_lists').eq('user_id', _currentUser.id).maybeSingle(),
      _timeout(5000, 'loadCloudState')
    ]);
    console.log('[AUTH] loadCloudState completed in', Date.now()-t0, 'ms',
      data ? 'got data' : 'no data', error || '');
    if(data){
      if(data.card_states && Object.keys(data.card_states).length)
        localStorage.setItem('swlegion_v1', JSON.stringify(data.card_states));
      if(data.army_lists && data.army_lists.length)
        localStorage.setItem('swlegion_lists', JSON.stringify(data.army_lists));
    }
  }catch(e){ console.warn('[AUTH] Cloud load failed:', e.message); }
}

async function syncToCloud(){
  if(!_supa || !_currentUser || _isGuest) return;
  try{
    const out={};
    Object.keys(ST).forEach(n=>{ const{idx,learned,flagged,notes,customDef,pinned}=ST[n]; out[n]={idx,learned,flagged,notes:notes||'',customDef:customDef||'',pinned:!!pinned}; });
    console.log('[AUTH] syncToCloud starting...');
    const t0 = Date.now();
    const { error } = await Promise.race([
      _supa.from('user_state').upsert({
        user_id: _currentUser.id,
        card_states: out,
        army_lists: loadLists(),
        updated_at: new Date().toISOString()
      }, { onConflict: 'user_id' }),
      _timeout(5000, 'syncToCloud')
    ]);
    console.log('[AUTH] syncToCloud completed in', Date.now()-t0, 'ms', error || 'OK');
  }catch(e){ console.warn('[AUTH] Cloud sync failed:', e.message); }
}

function scheduleSync(){
  if(!_currentUser || _isGuest) return;
  clearTimeout(_syncTimer);
  _syncTimer = setTimeout(syncToCloud, 2000);
}

// Auth screen visibility
function showAuthScreen(){
  document.getElementById('auth-screen').classList.remove('hidden');
}
function hideAuthScreen(){
  document.getElementById('auth-screen').classList.add('hidden');
}
function showAuthFromApp(){
  closeAcctDropdown();
  showAuthScreen();
}

// Auth mode tabs
let _authMode = 'login';
function setAuthMode(m){
  _authMode = m;
  document.getElementById('auth-tab-login').classList.toggle('active', m==='login');
  document.getElementById('auth-tab-signup').classList.toggle('active', m==='signup');
  document.getElementById('auth-submit').textContent = m==='login'?'Sign In':'Create Account';
  document.getElementById('auth-status').textContent = '';
  document.getElementById('auth-status').className = 'auth-status';
}
function setAuthStatus(msg, cls){
  const el = document.getElementById('auth-status');
  el.textContent = msg;
  el.className = 'auth-status ' + (cls||'');
}

// Sign in / sign up
async function authSubmit(){
  if(!_supa){ console.warn('[AUTH] No client in authSubmit'); guestMode(); return; }
  const email = document.getElementById('auth-email').value.trim();
  const pwd   = document.getElementById('auth-pwd').value;
  if(!email){ setAuthStatus('Enter your email','err'); return; }
  if(!pwd)  { setAuthStatus('Enter your password','err'); return; }
  console.log('[AUTH] authSubmit:', _authMode, email, '_authReady='+_authReady);
  const btn = document.getElementById('auth-submit');
  btn.disabled = true;
  try{
    if(_authMode === 'login'){
      setAuthStatus('Signing in…','work');
      console.log('[AUTH] calling signInWithPassword...');
      const t0 = Date.now();
      const result = await Promise.race([
        _supa.auth.signInWithPassword({ email, password: pwd }),
        _timeout(10000, 'signInWithPassword')
      ]);
      const ms = Date.now()-t0;
      console.log('[AUTH] signInWithPassword completed in', ms, 'ms');
      console.log('[AUTH] result:', JSON.stringify({error:result.error?.message, user:result.data?.user?.email}));
      btn.disabled = false;
      if(result.error){
        const msg = result.error.message.includes('Email not confirmed')
          ? 'Email not confirmed — check your inbox (or disable confirmation in Supabase dashboard)'
          : result.error.message;
        setAuthStatus(msg,'err');
      }
      // success handled by onAuthStateChange
    } else {
      if(pwd.length < 6){ btn.disabled=false; setAuthStatus('Password must be at least 6 characters','err'); return; }
      setAuthStatus('Creating account…','work');
      console.log('[AUTH] calling signUp...');
      const t0 = Date.now();
      const result = await Promise.race([
        _supa.auth.signUp({ email, password: pwd }),
        _timeout(10000, 'signUp')
      ]);
      const ms = Date.now()-t0;
      console.log('[AUTH] signUp completed in', ms, 'ms');
      console.log('[AUTH] result:', JSON.stringify({error:result.error?.message, user:result.data?.user?.email, confirmed:result.data?.user?.confirmed_at}));
      btn.disabled = false;
      if(result.error){
        setAuthStatus(result.error.message,'err');
      } else if(result.data?.user && !result.data.user.confirmed_at){
        setAuthStatus('Account created! Check your email to confirm, then sign in.','ok');
      } else {
        setAuthStatus('Signed up and logged in!','ok');
      }
    }
  }catch(e){
    btn.disabled = false;
    console.error('[AUTH] authSubmit error:', e);
    setAuthStatus(e.message||'Connection error — try again','err');
  }
}

async function authSignOut(){
  closeAcctDropdown();
  // Flush any pending sync first
  clearTimeout(_syncTimer);
  await syncToCloud();
  if(_supa) await _supa.auth.signOut();
  _currentUser = null; _isGuest = false;
  // Clear local cache
  localStorage.removeItem('swlegion_v1');
  localStorage.removeItem('swlegion_lists');
  // Reset in-memory state
  CARDS.forEach(c=>{ ST[c.name]={idx:0,learned:false,flagged:false,busy:false,notes:'',customDef:'',pinned:false}; });
  // Reset auth form
  document.getElementById('auth-email').value = '';
  document.getElementById('auth-pwd').value = '';
  setAuthStatus('','');
  showAuthScreen();
}

function guestMode(){
  _isGuest = true; _currentUser = null;
  hideAuthScreen();
  startApp();
}

// Account button dropdown
function toggleAcctDropdown(){
  const dd = document.getElementById('acct-dropdown');
  if(dd.classList.contains('open')){ closeAcctDropdown(); return; }
  dd.classList.add('open');
  setTimeout(()=>{ document.addEventListener('click', function _c(e){
    if(!document.getElementById('acct-dropdown-wrap').contains(e.target)){
      closeAcctDropdown(); document.removeEventListener('click',_c);
    }
  }); },0);
}
function closeAcctDropdown(){
  document.getElementById('acct-dropdown').classList.remove('open');
}
function updateAccountUI(){
  const btn   = document.getElementById('acct-btn');
  const label = document.getElementById('acct-email-label');
  const siItem = document.getElementById('acct-signin-item');
  const soItem = document.getElementById('acct-signout-item');
  const gLabel = document.getElementById('acct-guest-label');
  if(!btn) return;
  const loggedIn = !!_currentUser;
  const notesCol = document.getElementById('fs-notes-col');
  const editRulesBtn = document.getElementById('mod-edit');
  if(notesCol) notesCol.style.display = loggedIn ? '' : 'none';
  if(editRulesBtn) editRulesBtn.style.display = loggedIn ? '' : 'none';
  if(loggedIn){
    const email = _currentUser.email || '';
    const short = email.split('@')[0].substring(0,10);
    btn.textContent   = '\u{1F464} ' + short;
    label.textContent = email;
    siItem.style.display = 'none';
    soItem.style.display = 'block';
    gLabel.style.display = 'none';
  } else {
    btn.textContent   = '\u{1F464}';
    label.textContent = 'Guest mode';
    siItem.style.display = 'block';
    soItem.style.display = 'none';
    gLabel.style.display = 'block';
  }
}

// Boot
initAuth();
</script>
</body>
</html>"""


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
                total_kb = sum(os.path.getsize(os.path.join(HERE, p)) // 1024
                               for p in img_paths if os.path.exists(os.path.join(HERE, p)))
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
            "type":        kw["type"],
            "imgs":        img_paths,
            "credit":      kw.get("credit", "legion.takras.net"),
            "card_source": card_source,
        })

    ok = len(keywords) - len(failed)
    print()
    if failed:
        short = ', '.join(failed[:5]) + ('...' if len(failed) > 5 else '')
        print(f"  No image: {short}")
    print(f"  {ok}/{len(keywords)} keywords have images")

    # Step 3: Build HTML
    print(f"\n[3/3] Building swlegion_flashcards.html...")
    html = build_html(card_data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    kb = os.path.getsize(OUT) // 1024
    print(f"      swlegion_flashcards.html  ({kb} KB)")
    print(f"      images/                   ({ok} images)")
    print()
    print("  Open swlegion_flashcards.html in your browser.")
    print("  Keep the images/ folder in the same directory.")
    print("=" * 62)


if __name__ == "__main__":
    main()
