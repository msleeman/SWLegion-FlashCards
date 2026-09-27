"""Shared pytest fixtures for SWLegion-FlashCards test suite."""
import os
import sys
import subprocess
import pytest

# Project root is one level above this tests/ directory
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The built app. swlegion_flashcards.html at the root is only a redirect here.
HTML_FILE = os.path.join(PROJECT, "dist", "index.html")
TEMPLATE_DIR = os.path.join(PROJECT, "template")


# ── Python / build fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def project_dir():
    return PROJECT


@pytest.fixture(scope="session")
def html_content():
    """Contents of the built dist/index.html."""
    with open(HTML_FILE, encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="session")
def bld():
    """Imported build_swlegion_v4 module (session-scoped to load only once)."""
    sys.path.insert(0, PROJECT)
    import importlib
    import build_swlegion_v4
    return importlib.reload(build_swlegion_v4)


@pytest.fixture(scope="session")
def build_template():
    """The template sources every rebuild starts from: template/index.html,
    app.css and app.js, joined so a fix in any of them is visible."""
    parts = []
    for name in ("index.html", "app.css", "app.js"):
        with open(os.path.join(TEMPLATE_DIR, name), encoding="utf-8") as f:
            parts.append(f.read())
    return "\n".join(parts)


# ── Rebuild fixture (runs rebuild_html_only.py, then restores original) ───────

@pytest.fixture(scope="module")
def rebuilt_html():
    """
    Executes rebuild_html_only.py, yields (rebuilt_html_str, CompletedProcess).
    Always restores the original dist/index.html when the module finishes,
    even on failure.
    """
    with open(HTML_FILE, "rb") as f:
        original = f.read()

    rebuild_script = os.path.join(PROJECT, "rebuild_html_only.py")
    result = subprocess.run(
        [sys.executable, rebuild_script],
        capture_output=True, text=True, cwd=PROJECT, timeout=180,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    try:
        with open(HTML_FILE, encoding="utf-8") as f:
            rebuilt = f.read()
        yield rebuilt, result
    finally:
        with open(HTML_FILE, "wb") as f:
            f.write(original)


# ── Playwright base URL (file://) ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def page_url():
    return "file:///" + HTML_FILE.replace("\\", "/")


@pytest.fixture()
def guest_page(page, page_url):
    """Open the app, skip auth by clicking Play as Guest, yield the page."""
    page.goto(page_url)
    page.click("text=Play as Guest")
    page.wait_for_selector("#flashcard-screen.on", timeout=8000)
    return page


@pytest.fixture()
def catalog_page(guest_page):
    """Open the app already on the Catalog screen."""
    guest_page.click("button:has-text('Catalog')")
    guest_page.wait_for_selector("#catalog-screen.on", timeout=5000)
    return guest_page
