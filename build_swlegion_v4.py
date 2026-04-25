#!/usr/bin/env python3
"""Legacy entry point — delegates to src.build.

Use:
    py -m src.build          # preferred
    py build_swlegion_v4.py  # legacy shim (still works)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.build import main

# Re-export symbols that other scripts (rebuild_html_only.py, refresh_definitions.py)
# import directly from this module so they continue to work unchanged.
from src.config import HERE, CACHE_DIR, IMGDIR, DIST_DIR, DIST_IMGDIR, OVERRIDES_DIR, DATA_DIR, OUT
from src.config import CARD_ART_DIR, MANUAL_DIR, BASE, CDN, LEGIONHQ_CDN, WIKI_COMMONS_API, HEADERS
from src.data_tables import KEYWORD_PAGES, KEYWORD_CARDS, KEYWORD_CARD_IMAGES, BUNDLED_KEYWORDS
from src.overrides import (
    safe_filename, _get_ext, _kw_lookup_key, _keyword_stem,
    find_card_art, find_card_art_credit,
    find_manual_definition, find_manual_summary,
    has_manual_override, apply_manual_overlays,
)
from src.scrape import find_pdf, extract_keywords_from_pdf, scrape_keyword_page, scrape_keywords
from src.images import download_images, search_images_wiki
from src.render import build_unit_db_js, next_version, build_html

if __name__ == '__main__':
    main()
