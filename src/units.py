"""
Unit injection logic for SWLegion-FlashCards.
Adds a 'units' field to each card listing which units have that keyword.
"""
import os
import re
import json
from collections import defaultdict

from src.config import DATA_DIR


def _load_mappings():
    """Load unit keyword → card name mappings from data/unit_keyword_mappings.json."""
    path = os.path.join(DATA_DIR, 'unit_keyword_mappings.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    # Strip the _comment key if present
    return {k: v for k, v in data.items() if not k.startswith('_')}


def inject_units(card_data):
    """Add 'units' field to each card listing which units have that keyword."""
    unit_db_path = os.path.join(DATA_DIR, 'unit_db.json')
    if not os.path.exists(unit_db_path):
        return

    with open(unit_db_path, encoding="utf-8") as f:
        units = json.load(f)

    _manual = _load_mappings()

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
