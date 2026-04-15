"""
Playwright browser tests — load the actual HTML in a real Chromium instance
and verify UI elements and behaviour.

These are slower than the content tests but catch issues that only manifest
at runtime (missing DOM elements, JS errors, layout problems).
"""
import pytest
from playwright.sync_api import expect


# ─── Flashcard screen ─────────────────────────────────────────────────────────

class TestFlashcardScreen:

    def test_page_loads_and_auth_shown(self, page, page_url):
        page.goto(page_url)
        expect(page.locator("#auth-screen")).to_be_visible()

    def test_guest_mode_enters_app(self, guest_page):
        expect(guest_page.locator("#flashcard-screen")).to_be_visible()

    def test_progress_bar_visible(self, guest_page):
        expect(guest_page.locator("#fs-progress")).to_be_visible()

    def test_card_name_rendered(self, guest_page):
        """At least one keyword name must appear on the front of the card."""
        name_el = guest_page.locator("#fs-keyword-name")
        expect(name_el).to_be_visible()
        assert name_el.inner_text().strip() != "", "Keyword name must be non-empty"

    def test_flip_reveals_back(self, guest_page):
        guest_page.click("#fs-flip-zone")
        guest_page.wait_for_selector("#fs-back-content", state="visible", timeout=5000)
        expect(guest_page.locator("#fs-back-content")).to_be_visible()

    def test_bad_summary_button_visible_on_back(self, guest_page):
        """Fix 5: Bad Summary button must appear on the card back."""
        # Flip first (may already be flipped from previous test, but click again safely)
        back = guest_page.locator("#fs-back-content")
        if back.is_hidden():
            guest_page.click("#fs-flip-zone")
            guest_page.wait_for_selector("#fs-back-content", state="visible", timeout=5000)
        expect(guest_page.locator("button:has-text('Bad Summary')")).to_be_visible()

    def test_notes_textarea_has_maxlength_2000(self, guest_page):
        """Fix 4: #fs-notes textarea must enforce 2000 char limit."""
        back = guest_page.locator("#fs-back-content")
        if back.is_hidden():
            guest_page.click("#fs-flip-zone")
            guest_page.wait_for_selector("#fs-back-content", state="visible", timeout=5000)
        notes = guest_page.locator("#fs-notes")
        expect(notes).to_have_attribute("maxlength", "2000")

    def test_progress_bar_does_not_overlap_catalog_chip(self, guest_page):
        """Fix 6: Progress bar right edge must not overlap the Catalog button."""
        bar = guest_page.locator("#fs-progress")
        # Use the specific nav button, not the 'View Catalog' button on the done screen
        catalog_btn = guest_page.locator("#fs-nav-btns button:has-text('Catalog')")
        bar_box = bar.bounding_box()
        cat_box = catalog_btn.bounding_box()
        assert bar_box and cat_box, "Could not measure bounding boxes"
        bar_right = bar_box["x"] + bar_box["width"]
        cat_left = cat_box["x"]
        assert bar_right <= cat_left + 5, (  # 5px tolerance
            f"Progress bar right edge ({bar_right:.0f}px) overlaps "
            f"Catalog button left edge ({cat_left:.0f}px)"
        )


# ─── Catalog screen ───────────────────────────────────────────────────────────

class TestCatalogScreen:

    def test_catalog_opens(self, catalog_page):
        expect(catalog_page.locator("#catalog-screen")).to_be_visible()

    def test_catalog_renders_cards(self, catalog_page):
        cards = catalog_page.locator(".cat-card")
        assert cards.count() > 10, "Catalog must render at least 10 keyword cards"

    def test_catalog_search_filters(self, catalog_page):
        catalog_page.fill("#cat-search", "cunning")
        catalog_page.wait_for_timeout(300)
        cards = catalog_page.locator(".cat-card")
        assert cards.count() >= 1, "Search for 'cunning' must return at least one result"
        catalog_page.fill("#cat-search", "")  # reset

    def test_catalog_none_pill_no_parens(self, catalog_page):
        """Fix 2: After selecting None the pill must NOT show '(list name)'."""
        # Open the list dropdown and click None
        catalog_page.click("#cat-pill-list")
        catalog_page.wait_for_selector("#cat-list-dropdown.open", timeout=3000)
        catalog_page.locator(".none-item").first.click()
        catalog_page.wait_for_timeout(200)
        pill_text = catalog_page.locator("#cat-pill-list").inner_text()
        assert "(" not in pill_text, (
            f"After selecting None, catalog pill must not show '(list name)', got: {pill_text!r}"
        )


# ─── Catalog keyword modal ────────────────────────────────────────────────────

class TestCatalogModal:

    def _open_first_modal(self, page):
        page.locator(".cat-card").first.click()
        page.wait_for_selector("#modal-bg.on", timeout=5000)

    def test_modal_opens_on_card_click(self, catalog_page):
        self._open_first_modal(catalog_page)
        expect(catalog_page.locator("#modal-bg")).to_be_visible()

    def test_modal_photo_taller_than_220px(self, catalog_page):
        """Fix 3: Modal photo must be taller than the old 220px."""
        self._open_first_modal(catalog_page)
        photo = catalog_page.locator(".modal-photo, .modal-photo-ph").first
        box = photo.bounding_box()
        assert box is not None, "Could not measure modal photo height"
        assert box["height"] >= 300, (
            f"Modal photo height should be >= 300px (was 220px before fix), "
            f"got {box['height']:.0f}px"
        )

    def test_add_to_list_button_visible(self, catalog_page):
        """Fix 7: + List button must be present in the modal."""
        self._open_first_modal(catalog_page)
        expect(catalog_page.locator("#mod-add-list")).to_be_visible()

    def test_add_to_list_shows_picker_or_message(self, catalog_page):
        """Fix 7: Clicking + List must show the picker or a 'no lists' message."""
        self._open_first_modal(catalog_page)
        catalog_page.click("#mod-add-list")
        catalog_page.wait_for_timeout(300)
        # Either the picker is visible OR the status message indicates no lists
        picker = catalog_page.locator("#mod-list-picker")
        status = catalog_page.locator("#mod-st")
        picker_visible = picker.is_visible() and picker.inner_text().strip() != ""
        status_visible = status.is_visible() and status.inner_text().strip() != ""
        assert picker_visible or status_visible, (
            "Clicking + List must either show the list picker or a status message"
        )

    def test_modal_closes_cleanly(self, catalog_page):
        self._open_first_modal(catalog_page)
        catalog_page.click(".modal-btn.cls")
        catalog_page.wait_for_selector("#modal-bg.on", state="hidden", timeout=3000)
        expect(catalog_page.locator("#modal-bg")).to_be_hidden()

    def test_picker_hidden_after_close(self, catalog_page):
        """Fix 7: mod-list-picker must be hidden after closeMod()."""
        self._open_first_modal(catalog_page)
        # Open the picker
        catalog_page.click("#mod-add-list")
        catalog_page.wait_for_timeout(200)
        # Close the modal
        catalog_page.click(".modal-btn.cls")
        catalog_page.wait_for_selector("#modal-bg.on", state="hidden", timeout=3000)
        # Re-open to verify picker starts hidden
        self._open_first_modal(catalog_page)
        picker = catalog_page.locator("#mod-list-picker")
        assert not picker.is_visible() or picker.inner_text().strip() == "", (
            "mod-list-picker must be hidden when modal opens fresh"
        )
        # Clean up
        catalog_page.click(".modal-btn.cls")
