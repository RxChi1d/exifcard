"""Missing glyphs are reported, because nothing else notices them."""

from __future__ import annotations

from exifcard import glyphs


def test_ordinary_card_text_is_fully_covered():
    assert glyphs.missing("FUJIFILM X-T5", "56mm · f/1.4 · 1/250s · ISO 400") == []


def test_greek_alpha_is_covered_by_the_bundled_fallback():
    # Archivo alone cannot draw it, which is the whole reason Noto Sans ships.
    assert glyphs.missing("α7C II") == []


def test_uncovered_characters_are_named():
    absent = glyphs.missing("伏見稲荷")
    assert absent
    assert "U+" in glyphs.describe(absent)


def test_whitespace_is_not_reported_as_missing():
    assert glyphs.missing("  \t\n") == []
