"""
Unit tests for the Python build pipeline (build_swlegion_v4.py).

These validate that build utility functions work correctly and that
data structures (like KEYWORD_CARD_IMAGES) are set up as expected.
"""
import os
import pytest


# ─── _kw_lookup_key ───────────────────────────────────────────────────────────

class TestKwLookupKey:
    # _kw_lookup_key strips trailing X / [] markers but preserves original case.
    # KEYWORD_CARD_IMAGES uses title-case keys that match this output directly.

    def test_plain_name_unchanged(self, bld):
        assert bld._kw_lookup_key("Cunning") == "Cunning"

    def test_strips_trailing_x(self, bld):
        """'Armor X' → 'Armor' (variable-value keywords)."""
        assert bld._kw_lookup_key("Armor X") == "Armor"

    def test_strips_trailing_brackets(self, bld):
        """'Keyword []' → 'Keyword'."""
        result = bld._kw_lookup_key("Keyword []")
        assert "[]" not in result

    def test_multiword_preserved(self, bld):
        assert bld._kw_lookup_key("Anti-Materiel X") == "Anti-Materiel"

    def test_cunning_lookup_matches_dict(self, bld):
        """The normalised key must actually be present in KEYWORD_CARD_IMAGES."""
        key = bld._kw_lookup_key("Cunning")
        assert key in bld.KEYWORD_CARD_IMAGES, (
            f"Normalised key {key!r} not found in KEYWORD_CARD_IMAGES"
        )


# ─── safe_filename ────────────────────────────────────────────────────────────

class TestSafeFilename:

    def test_no_spaces(self, bld):
        fname = bld.safe_filename("Director Orson Krennic", ext=".webp")
        assert " " not in fname

    def test_correct_extension(self, bld):
        assert bld.safe_filename("Cunning", ext=".webp").endswith(".webp")
        assert bld.safe_filename("Something", ext=".jpg").endswith(".jpg")

    def test_non_empty(self, bld):
        assert bld.safe_filename("Cunning", ext=".webp") != ""

    def test_apostrophe_safe(self, bld):
        """Apostrophes in names must not break filenames."""
        fname = bld.safe_filename("Han Solo's Blaster", ext=".webp")
        assert fname  # non-empty
        assert "/" not in fname and "\\" not in fname


# ─── _get_ext ─────────────────────────────────────────────────────────────────

class TestGetExt:

    def test_webp(self, bld):
        assert bld._get_ext("Director%20Orson%20Krennic.webp") == ".webp"

    def test_jpg(self, bld):
        assert bld._get_ext("some_image.jpg") == ".jpg"

    def test_jpeg_normalised_to_jpg(self, bld):
        """_get_ext normalises .jpeg → .jpg (no separate jpeg handling)."""
        assert bld._get_ext("photo.jpeg") == ".jpg"

    def test_url_with_path(self, bld):
        ext = bld._get_ext("https://example.com/cards/Cunning.webp")
        assert ext == ".webp"


# ─── KEYWORD_CARD_IMAGES ──────────────────────────────────────────────────────

class TestKeywordCardImages:

    def test_cunning_maps_to_krennic(self, bld):
        """Core regression: Cunning must use Krennic, not Count Dooku."""
        key = bld._kw_lookup_key("Cunning")
        override = bld.KEYWORD_CARD_IMAGES.get(key, "")
        assert override, f"No image override found for 'cunning'"
        assert "Krennic" in override, (
            f"Cunning must map to Director Orson Krennic, got: {override!r}"
        )
        assert "Dooku" not in override, (
            f"Cunning must NOT still map to Count Dooku, got: {override!r}"
        )

    def test_all_values_have_valid_extension(self, bld):
        valid_exts = (".webp", ".jpg", ".jpeg", ".png")
        for kw, fname in bld.KEYWORD_CARD_IMAGES.items():
            assert any(fname.lower().endswith(e) for e in valid_exts), (
                f"KEYWORD_CARD_IMAGES[{kw!r}] = {fname!r} — unrecognised extension"
            )

    def test_no_blank_values(self, bld):
        for kw, fname in bld.KEYWORD_CARD_IMAGES.items():
            assert fname.strip(), f"Blank image override for keyword: {kw!r}"

    def test_map_is_non_empty(self, bld):
        assert len(bld.KEYWORD_CARD_IMAGES) > 10, "KEYWORD_CARD_IMAGES seems unexpectedly empty"


# ─── find_pdf ─────────────────────────────────────────────────────────────────

class TestFindPdf:

    def test_pdf_is_found(self, bld):
        """The PDF rulebook must be present in the repo (documents/ or root)."""
        path = bld.find_pdf()
        assert path is not None, (
            "PDF not found — SWQ_Rulebook_2.6.0-1.pdf must be in documents/ or project root"
        )

    def test_pdf_exists_on_disk(self, bld):
        path = bld.find_pdf()
        assert path and os.path.exists(path), f"PDF path returned but file missing: {path}"

    def test_pdf_is_not_trivially_small(self, bld):
        path = bld.find_pdf()
        assert path and os.path.getsize(path) > 500_000, (
            "PDF file seems too small — may be corrupt or a placeholder"
        )


# ─── build_html ───────────────────────────────────────────────────────────────

class TestBuildHtml:

    def test_returns_string(self, bld):
        html = bld.build_html([{
            "name": "Test", "definition": "A test.", "type": "unit",
            "imgs": [], "credit": "test", "card_source": ""
        }])
        assert isinstance(html, str)

    def test_html_doctype(self, bld):
        html = bld.build_html([{
            "name": "Test", "definition": "A test.", "type": "unit",
            "imgs": [], "credit": "test", "card_source": ""
        }])
        assert "<!DOCTYPE html>" in html

    def test_card_name_injected(self, bld):
        html = bld.build_html([{
            "name": "UniqueTestKeyword_XYZ_999",
            "definition": "A test keyword definition.",
            "type": "unit", "imgs": [], "credit": "test", "card_source": ""
        }])
        assert "UniqueTestKeyword_XYZ_999" in html

    def test_output_substantial_size(self, bld):
        """A real build with real card data should produce a large file."""
        import json
        cache = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "cards_cache.json")
        if not os.path.exists(cache):
            pytest.skip("cards_cache.json not present — skipping size check")
        with open(cache, encoding="utf-8") as f:
            card_data = json.load(f)
        html = bld.build_html(card_data)
        assert len(html) > 200_000, (
            f"Built HTML should be > 200 KB with full card data, got {len(html)} bytes"
        )
