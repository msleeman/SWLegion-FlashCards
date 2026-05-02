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

BASE             = 'https://legion.takras.net'
CDN              = 'https://d2maxvwz12z6fm.cloudfront.net'
LEGIONHQ_CDN     = 'https://d2maxvwz12z6fm.cloudfront.net/unitCards/'
WIKI_COMMONS_API = 'https://commons.wikimedia.org/w/api.php'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
