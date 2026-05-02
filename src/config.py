"""
Centralised path constants and URL constants for SWLegion-FlashCards.
All other modules import from here.
"""
import os, re, json, time, sys
import requests
from urllib.parse import urlencode

# src/ is one level below the project root
HERE          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR     = os.path.join(HERE, 'cache')
IMGDIR        = os.path.join(CACHE_DIR, 'images')        # download cache (gitignored)
DIST_DIR      = os.path.join(HERE, 'dist')
DIST_IMGDIR   = os.path.join(DIST_DIR, 'images')         # final distributed images
OVERRIDES_DIR = os.path.join(HERE, 'overrides')          # card_art + manual
DATA_DIR      = os.path.join(HERE, 'data')
TEMPLATE_DIR  = os.path.join(HERE, 'template')
OUT           = os.path.join(DIST_DIR, 'index.html')
# Keep these for backward compat with code that uses them:
CARD_ART_DIR  = OVERRIDES_DIR
MANUAL_DIR    = OVERRIDES_DIR

# ── Rulebook PDF (update this list when a new rulebook drops) ────────────────
# Order matters: NEWEST first. find_pdf() picks the first one it finds on disk
# in documents/ or the project root. To switch to a new rulebook, drop the PDF
# into documents/ and prepend its filename here. Old entries can stay as
# fallbacks until the file is removed.
RULEBOOK_PDFS = [
    "DOC51_SWQ_Rulebook_05-01_Update.pdf",   # 2026-05-01 update
    "SWQ_Rulebook_2.6.0-1.pdf",              # 2.6.0-1
    "SWQ_Rulebook_2_6_0-1.pdf",              # alternate spelling
]
# Credit shown on cards whose definition came from the PDF.
# Change this when bumping rulebooks so card credits track the source.
RULEBOOK_CREDIT = "AMG Rulebook 2026-05-01"

BASE             = 'https://legion.takras.net'
CDN              = 'https://d2maxvwz12z6fm.cloudfront.net'
LEGIONHQ_CDN     = 'https://d2maxvwz12z6fm.cloudfront.net/unitCards/'
WIKI_COMMONS_API = 'https://commons.wikimedia.org/w/api.php'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
