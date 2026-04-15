"""
Integration test: run rebuild_html_only.py end-to-end and assert that every
feature fix survives in the output.

These tests will go RED if HTML_TEMPLATE in build_swlegion_v4.py is ever
changed to remove a feature that exists in the live swlegion_flashcards.html.
The conftest.py fixture saves the original HTML and restores it after the module.

Rule: any new fix added to test_html_features.py MUST also get a corresponding
      test here so the rebuild contract stays complete.
"""
import pytest


class TestRebuildSanity:
    """The rebuild must complete and produce a valid HTML file."""

    def test_rebuild_exits_zero(self, rebuilt_html):
        _, result = rebuilt_html
        assert result.returncode == 0, (
            f"rebuild_html_only.py failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )

    def test_rebuild_output_is_substantial(self, rebuilt_html):
        html, _ = rebuilt_html
        assert len(html) > 200_000, (
            f"Rebuilt HTML is suspiciously small ({len(html)} bytes) — "
            "something likely went wrong in the build"
        )

    def test_rebuild_is_valid_html(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html

    def test_rebuild_has_card_data(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "const CARDS = [" in html, "Rebuilt HTML must contain the CARDS array"

    def test_rebuild_pdf_overlay_ran(self, rebuilt_html):
        """The rebuild stdout should confirm PDF definitions were overlaid."""
        _, result = rebuilt_html
        # If the PDF is present, the overlay message should appear
        assert "PDF" in result.stdout or "pdf" in result.stdout.lower() or \
               "definition" in result.stdout.lower(), (
            "Expected rebuild to mention PDF overlay in stdout.\n"
            f"stdout: {result.stdout[:500]}"
        )


# ─── Fix 1: Cunning → Krennic ─────────────────────────────────────────────────

class TestRebuildCunningKrennic:

    def test_cunning_uses_krennic_image(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "Krennic" in html or "Director%20Orson%20Krennic" in html, (
            "Rebuilt HTML: Cunning card must reference Director Orson Krennic image"
        )


# ─── Fix 2: Catalog None filter ──────────────────────────────────────────────

class TestRebuildCatalogNoneFilter:

    def test_catalog_none_calls_empty_string(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "setCatList('')" in html, (
            "Rebuilt HTML: Catalog None dropdown must call setCatList('') not null"
        )


# ─── Fix 3: Modal photo size ──────────────────────────────────────────────────

class TestRebuildModalPhoto:

    def test_modal_photo_height_340(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "height:340px" in html, (
            "Rebuilt HTML: .modal-photo height must be 340px"
        )

    def test_modal_photo_object_fit_contain(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "object-fit:contain" in html, (
            "Rebuilt HTML: .modal-photo must use object-fit:contain"
        )

    def test_old_220px_not_present(self, rebuilt_html):
        html, _ = rebuilt_html
        assert ".modal-photo{width:100%;height:220px" not in html, (
            "Rebuilt HTML: old 220px modal-photo height must be gone"
        )


# ─── Fix 4: Character limits ─────────────────────────────────────────────────

class TestRebuildCharacterLimits:

    def test_notes_textarea_maxlength(self, rebuilt_html):
        html, _ = rebuilt_html
        assert 'id="fs-notes"' in html
        assert 'maxlength="2000"' in html, (
            "Rebuilt HTML: #fs-notes textarea must have maxlength=\"2000\""
        )

    def test_def_edit_textarea_maxlength(self, rebuilt_html):
        html, _ = rebuilt_html
        assert 'id="mod-def-edit"' in html
        assert 'maxlength="2000"' in html, (
            "Rebuilt HTML: #mod-def-edit textarea must have maxlength=\"2000\""
        )


# ─── Fix 5: Bad Summary ───────────────────────────────────────────────────────

class TestRebuildBadSummary:

    def test_bad_summary_button_exists(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "Bad Summary" in html, (
            "Rebuilt HTML: Bad Summary button must exist"
        )

    def test_bad_summary_function_exists(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "function badSummary()" in html, (
            "Rebuilt HTML: badSummary() JS function must exist"
        )


# ─── Fix 6: Progress bar layout ──────────────────────────────────────────────

class TestRebuildProgressBarLayout:

    def test_topbar_right_padding(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "padding:14px 205px 0 16px" in html, (
            "Rebuilt HTML: #fs-topbar must have 205px right padding to clear nav chips"
        )


# ─── Fix 7: Add to List ──────────────────────────────────────────────────────

class TestRebuildAddToList:

    def test_plus_list_button_exists(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "mod-add-list" in html, (
            "Rebuilt HTML: + List button (id=mod-add-list) must exist in modal"
        )

    def test_list_picker_div_exists(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "mod-list-picker" in html, (
            "Rebuilt HTML: #mod-list-picker div must exist"
        )

    def test_show_add_to_list_function(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "function modShowAddToList()" in html, (
            "Rebuilt HTML: modShowAddToList() function must exist"
        )

    def test_add_to_list_function(self, rebuilt_html):
        html, _ = rebuilt_html
        assert "function modAddToList(" in html, (
            "Rebuilt HTML: modAddToList() function must exist"
        )
