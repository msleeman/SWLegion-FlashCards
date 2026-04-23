#!/usr/bin/env python3
"""Re-scrape definitions for cards in cards_cache.json.

Usage:
  py refresh_definitions.py                     # only re-scrape garbage definitions
  py refresh_definitions.py --all               # re-scrape every keyword
  py refresh_definitions.py --keywords Backup,Pierce X,Armor X
  py refresh_definitions.py --force-manual      # also overwrite manually-edited cards

Cards with a manual/ override file are always skipped unless --force-manual is given.
Cards with a good (non-garbage) definition are skipped unless --all or --keywords targets them.
"""
import argparse, json, os, re, sys, time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_swlegion_v4 as bld

CACHE_PATH = os.path.join(HERE, "cards_cache.json")

# Build slug lookup: normalized name -> slug
SLUG_BY_NORM = {}
for slug, name in bld.KEYWORD_PAGES:
    bare = name.replace("[]", "").strip()
    norm = re.sub(r'[^a-z0-9]', '', bare.lower())
    SLUG_BY_NORM[norm] = slug


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def is_garbage(definition: str, name: str) -> bool:
    if not definition or len(definition) < 60:
        return True
    bare = name.replace("[]", "").strip().lower()
    norm_def = re.sub(r"\s+", " ", definition.lower()).strip()
    if "legion helper" in norm_def and len(definition) < 120:
        return True
    if norm_def.startswith(bare) and len(definition) < 120:
        return True
    return False


def slug_for(card_name):
    return SLUG_BY_NORM.get(_norm(card_name))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true",
                        help="Re-scrape every keyword regardless of current definition quality")
    parser.add_argument("--keywords", metavar="NAME1,NAME2,...",
                        help="Comma-separated list of keyword names to re-scrape")
    parser.add_argument("--force-manual", action="store_true",
                        help="Also re-scrape cards that have a manual/ override file")
    args = parser.parse_args()

    with open(CACHE_PATH, encoding="utf-8") as f:
        cards = json.load(f)
    print(f"Loaded {len(cards)} cards")

    # Build target set
    if args.keywords:
        target_norms = {_norm(k.strip()) for k in args.keywords.split(",")}
        targets = [c for c in cards if _norm(c["name"]) in target_norms]
        print(f"Targeting {len(targets)} keyword(s) by name")
    elif args.all:
        targets = list(cards)
        print(f"Targeting all {len(targets)} cards (--all)")
    else:
        targets = [c for c in cards if is_garbage(c.get("definition", ""), c["name"])]
        print(f"{len(targets)} cards have garbage definitions")

    # Filter out manual overrides (unless --force-manual)
    if not args.force_manual:
        before = len(targets)
        targets = [c for c in targets if not bld.has_manual_override(c["name"])]
        skipped = before - len(targets)
        if skipped:
            print(f"  Skipping {skipped} card(s) with manual/ overrides (use --force-manual to override)")

    if not targets:
        print("Nothing to re-scrape.")
        return

    session = requests.Session()
    fixed = 0
    still_bad = []

    for i, c in enumerate(targets, 1):
        name = c["name"]
        slug = slug_for(name)
        if not slug:
            print(f"  [{i:3d}/{len(targets)}] {name[:42]:<42} NO SLUG — skipping")
            still_bad.append(name)
            continue

        result = bld.scrape_keyword_page(slug, name, session)
        if result and result.get("definition") and not is_garbage(result["definition"], name):
            c["definition"] = result["definition"]
            c["type"]       = result["type"]
            c["credit"]     = "legion.takras.net"
            # Clear stale summary so it gets re-derived from new definition
            if not bld.find_manual_summary(name):
                c.pop("summary", None)
            fixed += 1
            print(f"  [{i:3d}/{len(targets)}] {name[:42]:<42} OK ({len(result['definition'])} chars)")
        else:
            still_bad.append(name)
            print(f"  [{i:3d}/{len(targets)}] {name[:42]:<42} STILL BAD")
        time.sleep(0.25)

    # Apply manual overlays so they're in the cache too
    bld.apply_manual_overlays(cards)

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    print(f"\nFixed {fixed}/{len(targets)} cards — cache saved")
    if still_bad:
        print(f"\n{len(still_bad)} cards could not be fixed:")
        for n in still_bad:
            print(f"  {n}")
    print("\nRun: py rebuild_html_only.py")


if __name__ == "__main__":
    main()
