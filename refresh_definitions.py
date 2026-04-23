#!/usr/bin/env python3
"""Re-scrape definitions for cards with garbage/short definitions in cards_cache.json.

The cache historically contained ~195 cards with placeholder text like
"Backup [] - Legion Helper" because an older scraper missed them.
The current scrape_keyword_page() in build_swlegion_v4 handles these correctly,
so this script just re-runs it for the bad cards and saves the cache.
"""
import json, os, re, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_swlegion_v4 as bld

CACHE_PATH = os.path.join(HERE, "cards_cache.json")

# Build slug lookup: name -> slug (handles both raw and []-stripped names)
SLUG_BY_NAME = {}
for slug, name in bld.KEYWORD_PAGES:
    SLUG_BY_NAME[name] = slug
    SLUG_BY_NAME[name.replace("[]", "").strip()] = slug


def is_garbage(definition: str, name: str) -> bool:
    """Return True if the definition looks like a scrape placeholder."""
    if not definition or len(definition) < 60:
        return True
    bare = name.replace("[]", "").strip().lower()
    norm = re.sub(r"\s+", " ", definition.lower()).strip()
    # Patterns like "<name> - Legion Helper" or "<name> Legion Helper"
    if "legion helper" in norm and len(definition) < 80:
        return True
    if norm.startswith(bare) and len(definition) < 80:
        return True
    return False


def main():
    with open(CACHE_PATH, encoding="utf-8") as f:
        cards = json.load(f)
    print(f"Loaded {len(cards)} cards")

    bad = [c for c in cards if is_garbage(c.get("definition", ""), c["name"])]
    print(f"{len(bad)} cards have garbage definitions")

    session = requests.Session()
    fixed = 0
    still_bad = []
    for i, c in enumerate(bad, 1):
        name = c["name"]
        slug = SLUG_BY_NAME.get(name) or SLUG_BY_NAME.get(name.replace("[]", "").strip())
        if not slug:
            print(f"  [{i:3d}/{len(bad)}] {name[:42]:<42} NO SLUG")
            still_bad.append(name)
            continue
        result = bld.scrape_keyword_page(slug, name, session)
        if result and result.get("definition") and not is_garbage(result["definition"], name):
            c["definition"] = result["definition"]
            c["type"] = result["type"]
            c["credit"] = "legion.takras.net"
            fixed += 1
            print(f"  [{i:3d}/{len(bad)}] {name[:42]:<42} OK ({len(result['definition'])} chars)")
        else:
            still_bad.append(name)
            print(f"  [{i:3d}/{len(bad)}] {name[:42]:<42} STILL BAD")
        time.sleep(0.25)

    # Save cache
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    print(f"\nFixed {fixed}/{len(bad)} cards")
    if still_bad:
        print(f"\n{len(still_bad)} cards still have no usable definition:")
        for n in still_bad[:30]:
            print(f"  {n}")


if __name__ == "__main__":
    main()
