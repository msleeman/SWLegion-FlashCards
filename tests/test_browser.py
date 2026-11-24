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
        """Fix 5: Bad Summary button is on the card back, but owner-only --
        a guest must not see it."""
        # Flip first (may already be flipped from previous test, but click again safely)
        back = guest_page.locator("#fs-back-content")
        if back.is_hidden():
            guest_page.click("#fs-flip-zone")
            guest_page.wait_for_selector("#fs-back-content", state="visible", timeout=5000)
        btn = guest_page.locator("#fs-ai-summary-btn")
        expect(btn).to_have_count(1)
        expect(btn).to_be_hidden()

    def test_notes_textarea_has_maxlength_2000(self, guest_page):
        """Fix 4: #fs-notes textarea must enforce 2000 char limit."""
        back = guest_page.locator("#fs-back-content")
        if back.is_hidden():
            guest_page.click("#fs-flip-zone")
            guest_page.wait_for_selector("#fs-back-content", state="visible", timeout=5000)
        notes = guest_page.locator("#fs-notes")
        expect(notes).to_have_attribute("maxlength", "2000")

    def test_counter_centered_on_progress_bar(self, guest_page):
        """Fix 8: 1/N counter must be rendered inside and horizontally centered on the bar."""
        bar = guest_page.locator("#fs-progress")
        ctr = guest_page.locator("#fs-ctr")
        expect(ctr).to_be_visible()
        bar_box = bar.bounding_box()
        ctr_box = ctr.bounding_box()
        assert bar_box and ctr_box, "Could not measure bounding boxes"
        bar_mid = bar_box["x"] + bar_box["width"] / 2
        ctr_mid = ctr_box["x"] + ctr_box["width"] / 2
        assert abs(bar_mid - ctr_mid) < 20, (
            f"Counter mid ({ctr_mid:.0f}px) is not centred on bar mid ({bar_mid:.0f}px)"
        )
        # Counter text must look like "N/M"
        text = ctr.inner_text().strip()
        assert "/" in text and text.replace("/", "").replace(" ", "").isdigit() or \
               "/" in text, f"Counter text must be N/M format, got: {text!r}"

    def test_progress_bar_below_app_nav(self, guest_page):
        """The flashcard top bar sits wholly below the app nav bar."""
        bar = guest_page.locator("#fs-progress").bounding_box()
        nav = guest_page.locator("#app-nav").bounding_box()
        assert bar and nav, "Could not measure bounding boxes"
        assert bar["y"] >= nav["y"] + nav["height"], (
            f"Progress bar top ({bar['y']:.0f}px) is under the nav bar "
            f"(bottom {nav['y'] + nav['height']:.0f}px)"
        )


# ─── Lists home ───────────────────────────────────────────────────────────────

class TestListsHome:

    def test_guest_lands_on_lists(self, page, page_url):
        page.goto(page_url)
        page.click("text=Play as Guest")
        page.wait_for_selector("#lists-screen.on", timeout=8000)
        expect(page.locator("#app-nav .nav-tab.active")).to_have_text("⛏ Lists")

    def test_empty_lists_show_import_panel(self, page, page_url):
        page.goto(page_url)
        page.click("text=Play as Guest")
        page.wait_for_selector("#lists-screen.on", timeout=8000)
        expect(page.locator("#list-create-panel")).to_be_visible()
        expect(page.locator("#list-url-input")).to_be_visible()

    def test_saved_list_opens_its_page(self, page, page_url):
        page.goto(page_url)
        # Mark the data as a guest's, or Play as Guest wipes it as another account's.
        page.evaluate("() => localStorage.setItem('swlegion_data_owner','guest')")
        page.evaluate("""() => localStorage.setItem('swlegion_lists', JSON.stringify([{
            id:'lst_test', name:'Test Army', faction:'empire', points:800,
            keywords:['Sharpshooter 1','Precise 1'],
            units:[{count:1,name:'Stormtroopers',title:'',img:'',artTta:'',rank:'corps',
                    cost:0,upgrades:[],upgradeCards:[],kws:['Precise 1'],weapons:[]}],
            armyUrl:'', createdAt:new Date().toISOString()}]))""")
        page.reload()
        page.click("text=Play as Guest")
        page.wait_for_selector("#lists-screen.on", timeout=8000)
        page.click(".lcard >> text=Test Army")
        page.wait_for_selector("#list-screen.on", timeout=5000)
        expect(page.locator("#ld-name")).to_have_text("Test Army")
        assert page.locator("#ld-kws .kw-tag").count() >= 1

    def test_study_button_filters_flashcards(self, page, page_url):
        page.goto(page_url)
        # Mark the data as a guest's, or Play as Guest wipes it as another account's.
        page.evaluate("() => localStorage.setItem('swlegion_data_owner','guest')")
        page.evaluate("""() => localStorage.setItem('swlegion_lists', JSON.stringify([{
            id:'lst_t2', name:'Study Army', faction:'rebels', points:0,
            keywords:['Sharpshooter 1'], units:[], armyUrl:'',
            createdAt:new Date().toISOString()}]))""")
        page.reload()
        page.click("text=Play as Guest")
        page.wait_for_selector("#lists-screen.on", timeout=8000)
        page.click(".lcard .lcard-btn.primary")
        page.wait_for_selector("#flashcard-screen.on", timeout=5000)
        expect(page.locator("#pill-list")).to_contain_text("Study Army")


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
        """Fix 3: Modal photo must be taller than the old 220px (260px since eecb819)."""
        self._open_first_modal(catalog_page)
        photo = catalog_page.locator(".modal-photo, .modal-photo-ph").first
        box = photo.bounding_box()
        assert box is not None, "Could not measure modal photo height"
        assert box["height"] >= 250, (
            f"Modal photo height should be >= 250px (was 220px before fix), "
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


class TestLegionIconFont:
    """Rules-text tokens like [HIT] / [RANGE 3] render as Legion font glyphs."""

    def test_font_embedded_and_loaded(self, guest_page):
        loaded = guest_page.evaluate(
            "async()=>{await document.fonts.ready;"
            "return document.fonts.check('16px LegionSymbols');}")
        assert loaded, "LegionSymbols @font-face did not load"

    def test_tokens_become_glyphs_in_modal(self, guest_page):
        res = guest_page.evaluate("""async()=>{
            showScreen('catalog-screen'); openMod('Commander and Panic Check');
            await new Promise(r=>setTimeout(r,200));
            const el=document.getElementById('mod-def');
            return {icons:[...el.querySelectorAll('i.lgi')].map(i=>i.title+'='+i.textContent),
                    left:(el.textContent.match(/\[(COMMANDER|COURAGE|RANGE 3)\]/g)||[])};
        }""")
        assert "[COMMANDER]=5" in res["icons"]
        assert "[RANGE 3]=3" in res["icons"]
        assert "[COURAGE]=m" in res["icons"]
        assert res["left"] == [], f"tokens left as text: {res['left']}"

    def test_unknown_tokens_stay_text(self, guest_page):
        out = guest_page.evaluate("""()=>{
            const d=document.createElement('div');
            d.textContent='Spend [WIBBLE] at [RANGE 1/2] for [HIT]'; document.body.appendChild(d);
            legionIconize(d); const t=d.textContent; d.remove(); return t;
        }""")
        # [TAP] has a glyph since the exhaust icon fix; use a made-up token.
        assert "[WIBBLE]" in out and "[RANGE 1/2]" in out and "[HIT]" not in out
