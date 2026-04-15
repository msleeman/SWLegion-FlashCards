"""
Feature contract tests — check every fix is present in BOTH:
  1. The built swlegion_flashcards.html (what users see now)
  2. The HTML_TEMPLATE inside build_swlegion_v4.py (so rebuilds preserve fixes)

A test here goes RED the moment a feature disappears from either source.
When adding a new fix, add a corresponding test class here AND in test_rebuild.py.
"""
import pytest


# ─── Parametrise every test over both sources automatically ──────────────────

@pytest.fixture(params=["html_file", "build_template"])
def source(request, html_content, build_template):
    """Run each test twice: once against the live HTML, once against the template."""
    label = request.param
    text = html_content if label == "html_file" else build_template
    return label, text


def assertIn(needle, haystack, label):
    assert needle in haystack, (
        f"[{label}] Expected to find:\n  {needle!r}\n"
        f"  in the {'built HTML file' if label == 'html_file' else 'HTML_TEMPLATE in build_swlegion_v4.py'}"
    )


# ─── Fix 1: Cunning uses Director Orson Krennic image ─────────────────────────

class TestCunningKrennicImage:

    def test_build_override_maps_cunning_to_krennic(self, bld):
        """KEYWORD_CARD_IMAGES['cunning'] must point to Krennic, not Count Dooku."""
        key = bld._kw_lookup_key("Cunning")
        override = bld.KEYWORD_CARD_IMAGES.get(key, "")
        assert "Krennic" in override, (
            f"Cunning image override must be Krennic, got: {override!r}"
        )
        assert "Dooku" not in override, (
            f"Cunning must not use Count Dooku image, got: {override!r}"
        )

    def test_built_html_cunning_cdn_url(self, html_content):
        """Live HTML: Cunning card imgs must use the Krennic CDN URL."""
        assert "Director%20Orson%20Krennic.webp" in html_content, (
            "Built HTML: Cunning card must reference Director Orson Krennic CDN image"
        )

    def test_built_html_cunning_card_source(self, html_content):
        assert '"card_source": "See: Director Orson Krennic"' in html_content


# ─── Fix 2: Catalog "None" filter sets explicit no-filter ────────────────────

class TestCatalogNoneFilter:

    def test_catalog_none_calls_empty_string(self, source):
        """None dropdown item must call setCatList('') — not setCatList(null)."""
        label, text = source
        assertIn("setCatList('')", text, label)

    def test_catalog_dropdown_built_correctly(self, source):
        """The catalog list dropdown function must exist."""
        label, text = source
        assertIn("toggleCatListDropdown", text, label)


# ─── Fix 3: Modal photo 340 px tall, object-fit contain ──────────────────────

class TestModalPhotoSize:

    def test_height_340px(self, source):
        label, text = source
        assertIn("height:340px", text, label)

    def test_object_fit_contain(self, source):
        label, text = source
        assertIn("object-fit:contain", text, label)

    def test_old_220px_height_gone(self, source):
        """The old 220 px height must not appear on .modal-photo."""
        label, text = source
        assert ".modal-photo{width:100%;height:220px" not in text, (
            f"[{label}] Old 220px modal-photo height is still present"
        )


# ─── Fix 4: Notes & Rules edit textarea maxlength 2000 ───────────────────────

class TestCharacterLimits:

    def test_notes_textarea_maxlength_2000(self, source):
        label, text = source
        # Both id and attribute must appear in the same source
        assert 'id="fs-notes"' in text, f"[{label}] #fs-notes not found"
        assertIn('maxlength="2000"', text, label)

    def test_def_edit_textarea_maxlength_2000(self, source):
        label, text = source
        assert 'id="mod-def-edit"' in text, f"[{label}] #mod-def-edit not found"
        assertIn('maxlength="2000"', text, label)


# ─── Fix 5: Bad Summary button + JS function ─────────────────────────────────

class TestBadSummary:

    def test_button_label_exists(self, source):
        label, text = source
        assertIn("Bad Summary", text, label)

    def test_js_function_defined(self, source):
        label, text = source
        assertIn("function badSummary()", text, label)

    def test_function_writes_to_notes_element(self, source):
        """badSummary() must update #fs-notes so the user sees the result."""
        label, text = source
        idx = text.find("function badSummary()")
        assert idx != -1, f"[{label}] function badSummary() not found"
        body = text[idx: idx + 900]
        assert "fs-notes" in body, (
            f"[{label}] badSummary() body must reference #fs-notes element"
        )

    def test_function_calls_save_state(self, source):
        label, text = source
        idx = text.find("function badSummary()")
        assert idx != -1
        body = text[idx: idx + 900]
        assert "saveState()" in body, (
            f"[{label}] badSummary() must call saveState() to persist the summary"
        )


# ─── Fix 6: Progress bar ends before Catalog chip ────────────────────────────

class TestProgressBarLayout:

    def test_topbar_right_padding_205px(self, source):
        label, text = source
        assertIn("padding:14px 205px 0 16px", text, label)

    def test_old_equal_padding_gone(self, source):
        label, text = source
        assert "padding:14px 16px 0;" not in text and \
               "padding:14px 16px 0\n" not in text, (
            f"[{label}] Old equal-sided padding still present in #fs-topbar"
        )


# ─── Fix 7: "Add to List" button in catalog modal ───────────────────────────

class TestAddToList:

    def test_button_element_exists(self, source):
        label, text = source
        assertIn("mod-add-list", text, label)

    def test_list_picker_div_exists(self, source):
        label, text = source
        assertIn("mod-list-picker", text, label)

    def test_show_function_defined(self, source):
        label, text = source
        assertIn("function modShowAddToList()", text, label)

    def test_add_function_defined(self, source):
        label, text = source
        assertIn("function modAddToList(", text, label)

    def test_close_mod_hides_picker(self, source):
        """closeMod() must hide mod-list-picker so it doesn't persist after close."""
        label, text = source
        idx = text.find("function closeMod(")
        assert idx != -1, f"[{label}] closeMod() not found"
        body = text[idx: idx + 400]
        assert "mod-list-picker" in body, (
            f"[{label}] closeMod() must hide the #mod-list-picker element"
        )

    def test_add_to_list_persists_via_save_lists(self, source):
        """modAddToList() must call saveLists() so the change survives a reload."""
        label, text = source
        idx = text.find("function modAddToList(")
        assert idx != -1, f"[{label}] function modAddToList() not found"
        body = text[idx: idx + 900]
        assert "saveLists(" in body, (
            f"[{label}] modAddToList() must call saveLists() to persist"
        )


# ─── Fix 8: Progress counter centred on top of progress bar ──────────────────

class TestProgressCounter:

    def test_fs_ctr_inside_fs_progress(self, source):
        """#fs-ctr span must be a child of #fs-progress, not a sibling."""
        label, text = source
        idx = text.find('id="fs-progress"')
        assert idx != -1, f"[{label}] #fs-progress not found"
        # Grab the opening tag + inner content until the closing </div>
        chunk = text[idx: idx + 200]
        assert 'id="fs-ctr"' in chunk, (
            f"[{label}] #fs-ctr must be inside #fs-progress, not a sibling"
        )

    def test_fs_progress_position_relative(self, source):
        """#fs-progress must be position:relative so the absolute counter works."""
        label, text = source
        assertIn("position:relative", text, label)

    def test_fs_ctr_position_absolute_centered(self, source):
        """#fs-ctr must be absolutely positioned and centred with transform."""
        label, text = source
        assertIn("left:50%", text, label)
        assertIn("transform:translate(-50%,-50%)", text, label)

    def test_fs_ctr_small_font(self, source):
        """Counter must use a small font (≤9px) — not the old 13px."""
        label, text = source
        # Must have 9px somewhere in the ctr rule
        assertIn("font-size:9px", text, label)
        # The old 13px rule for #fs-ctr must be gone
        assert "#fs-ctr{color:var(--white2);font-size:13px" not in text, (
            f"[{label}] Old 13px #fs-ctr style is still present"
        )

