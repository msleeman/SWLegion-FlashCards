"""
Unit injection logic for SWLegion-FlashCards.
Adds a 'units' field to each card listing which units have that keyword.
"""
import os
import re
import json
from collections import defaultdict

from src.config import DATA_DIR


def inject_units(card_data):
    """Add 'units' field to each card listing which units have that keyword."""
    unit_db_path = os.path.join(DATA_DIR, 'unit_db.json')
    if not os.path.exists(unit_db_path):
        return

    with open(unit_db_path, encoding="utf-8") as f:
        units = json.load(f)

    def _norm_cache(name):
        n = re.sub(r'\s*\[\]$', '', name)
        n = re.sub(r'\s*:\s*.+$', '', n)
        n = re.sub(r'\s+X$', '', n)
        n = re.sub(r'\s+\d+$', '', n)
        return n.strip().lower()

    def _norm_unit(kw):
        n = re.sub(r'\s+\d+(\s*:\s*.+)?$', '', kw)
        n = re.sub(r'\s*:\s*.+$', '', n)
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

    cache_lookup = {}
    for e in card_data:
        b = _norm_cache(e['name'])
        if b not in cache_lookup:
            cache_lookup[b] = e['name']

    def _find_cache_name(kw):
        base = _norm_unit(kw)
        if base in _manual:
            return _manual[base]
        for pfx, cn in _manual.items():
            if base.startswith(pfx + ' ') or base == pfx:
                return cn
        return cache_lookup.get(base)

    kw_units = defaultdict(list)
    for u in units.values():
        dname = u['name']
        for kw in u.get('keywords', []):
            cn = _find_cache_name(kw)
            if cn and dname not in kw_units[cn]:
                kw_units[cn].append(dname)
    for k in kw_units:
        kw_units[k].sort()
    for e in card_data:
        ul = kw_units.get(e['name'], [])
        e['units'] = ', '.join(ul)
    print(f"      Injected 'units' field ({sum(1 for e in card_data if e.get('units'))} keywords have units)")
