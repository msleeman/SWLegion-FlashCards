"""Shared pytest fixtures for SWLegion-FlashCards test suite."""
import os
import sys
import subprocess
import pytest

# Project root is one level above this tests/ directory
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_FILE = os.path.join(PROJECT, "swlegion_flashcards.html")


# ── Python / build fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def project_dir():
    return PROJECT


@pytest.fixture(scope="session")
def html_content():
    """Contents of the current committed swlegion_flashcards.html."""
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
def build_template(bld):
    """The HTML_TEMPLATE string embedded in build_swlegion_v4.py."""
    return bld.HTML_TEMPLATE


# ── Rebuild fixture (runs rebuild_html_only.py, then restores original) ───────

@pytest.fixture(scope="module")
def rebuilt_html():
    """
    Executes rebuild_html_only.py, yields (rebuilt_html_str, CompletedProcess).
    Always restores the original HTML when the module finishes, even on failure.
    """
    with open(HTML_FILE, encoding="utf-8") as f:
        original = f.read()

    rebuild_script = os.path.join(PROJECT, "rebuild_html_only.py")
    result = subprocess.run(
        ["py", rebuild_script],
        capture_output=True, text=True, cwd=PROJECT, timeout=180
    )

    try:
        with open(HTML_FILE, encoding="utf-8") as f:
            rebuilt = f.read()
        yield rebuilt, result
    finally:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
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
