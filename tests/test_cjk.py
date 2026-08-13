"""Chinese, Japanese and Korean in the location caption.

Han ink sits higher than the monospace digits it shares a line with, so at one
font-size a place name overpowers the date beside it -- the wrong way round for
the quietest line on the card. The compensation is a single ratio, which these
tests hold to the measurement it came from.

The two fonts here are subsets of Noto, cut to the handful of characters these
tests need and renamed so neither can be mistaken for the font it came from.
Nothing CJK is bundled with exifcard: the files are large and which one is
right depends on where you photograph, so the user registers their own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from exifcard import glyphs, layout, logos, strip
from exifcard.metadata import CardData

pytest.importorskip("playwright.sync_api")

GOLDEN = Path(__file__).parent / "golden"
HAN = GOLDEN / "han-sample.ttf"
HANGUL = GOLDEN / "hangul-sample.ttf"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def sample():
    return CardData(
        make="FUJIFILM",
        make_key="FUJIFILM",
        brand_label="FUJIFILM",
        body="X-T5",
        lens_brand="SIGMA",
        lens="56mm F1.4 DC DN",
        exposure="56mm · f/1.4 · 1/250s · ISO 400",
        date="2026.03.14",
    )


def spec_for(data, ratio=(3, 2), **kwargs):
    return strip.StripSpec(
        data=data,
        card_width=1000,
        canvas_width=layout.canvas_width_for(*ratio),
        logo=logos.find("FUJIFILM", "X-T5"),
        **kwargs,
    )


def sizes_in(markup: str) -> list[float]:
    return [float(size) for size in re.findall(r"font-size:([\d.]+)px", markup)]


# 1. The compensation itself.


def test_a_han_run_is_set_at_the_compensated_size(sample):
    sample.location = "京都"
    markup = strip.build_html(spec_for(sample))
    span = re.search(r'<span style="font-size:([\d.]+)px;[^"]*">京都</span>', markup)
    assert span, markup[markup.find("timeline") :][:400]
    assert float(span.group(1)) == pytest.approx(layout.SIZE_DATE * layout.CJK_SIZE_RATIO)


def test_the_ratio_matches_the_measured_ink(sample):
    """0.88 is where Han ink and monospace digits reach the same height.

    Measured from the outlines rather than the declared ascent, because it is
    the ink that the eye levels against, not the metrics box.
    """
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    def ink_top(path, chars):
        font = TTFont(path, fontNumber=0)
        upm, cmap, glyph_set = font["head"].unitsPerEm, font.getBestCmap(), font.getGlyphSet()
        highest = 0.0
        for char in chars:
            pen = BoundsPen(glyph_set)
            glyph_set[cmap[ord(char)]].draw(pen)
            if pen.bounds:
                highest = max(highest, pen.bounds[3] / upm)
        return highest

    digits = ink_top(strip.FONTS / "JetBrainsMono.ttf", "0123456789")
    han = ink_top(HAN, "京都伏見稲荷大社臺北國永")
    assert digits / han == pytest.approx(layout.CJK_SIZE_RATIO, abs=0.02)


# 2. Mixed scripts.


def test_latin_in_a_mixed_caption_keeps_its_size(sample):
    sample.location = "京都 Fushimi Inari"
    markup = strip.build_html(spec_for(sample))
    timeline = markup[markup.find('id="timeline"') :]
    timeline = timeline[: timeline.find("</div>")]

    assert '<span style="font-size:7.92px;letter-spacing:0.1em">京都</span>' in timeline
    assert "Fushimi Inari" in timeline
    # The Latin sits outside any resized span, so it stays on the line's size.
    assert timeline.count("<span") == 1


def test_the_caption_is_still_escaped(sample):
    sample.location = "京都 <script>& Kyoto"
    markup = strip.build_html(spec_for(sample))
    assert "<script>" not in markup
    assert "&lt;script&gt;&amp; Kyoto" in markup


def test_halfwidth_katakana_is_left_alone(sample):
    """It is not full-width, so it was never mis-sized to begin with."""
    sample.location = "ｷｮｳﾄ"
    markup = strip.build_html(spec_for(sample))
    assert "<span" not in markup[markup.find('id="timeline"') :].split("</div>")[0]


# 3. Row 2 keeps its height.


def test_the_date_line_box_fits_the_row_it_is_given():
    """0.2px of headroom, which the next person to touch these numbers loses.

    Overflow here does not spill downward into the paper, it pushes up into
    row 1 -- the same failure the signature had.
    """
    left = layout.ROW2_HEIGHT - layout.SIZE_LENS * layout.LINE_HEIGHT - layout.ROW2_LINE_GAP
    assert layout.SIZE_DATE * layout.LINE_HEIGHT <= left
    assert layout.SIZE_DATE * layout.CJK_SIZE_RATIO * layout.LINE_HEIGHT <= left


def test_a_han_caption_does_not_change_the_row_height(sample, browser):
    latin = strip.measure(spec_for(sample, signature=GOLDEN / "ink-mark.png"), browser=browser)
    sample.location = "京都伏見稲荷大社"
    han = strip.measure(
        spec_for(sample, signature=GOLDEN / "ink-mark.png", fonts=(HAN,)), browser=browser
    )
    assert han["row2"]["height"] == pytest.approx(latin["row2"]["height"], abs=0.01)


# 4. Width is arithmetic, because every CJK face is drawn on an em square.


def test_a_han_caption_measures_at_its_arithmetic_width(sample, browser):
    """One character advances by its em plus the line's tracking, always.

    Every CJK face is drawn on an em square, which is what lets the budget be
    stated in the README as a number of characters rather than measured per
    font. The lens is dropped here because the two share a column: the date
    line is a block and stretches to whichever of them is wider.
    """
    per_character = layout.SIZE_DATE * layout.CJK_SIZE_RATIO * (1 + layout.TRACK_DATE)
    sample.lens = sample.lens_brand = ""
    sample.date = ""
    sample.location = "京都伏見稲荷大社臺北國永"
    room = strip.caption_room(
        spec_for(sample, ratio=(9, 16), signature=GOLDEN / "ink-mark.png", fonts=(HAN,)),
        browser=browser,
    )
    # Two pixels across twelve characters, because the measurement takes the
    # larger of a fractional rect and an integer scrollWidth and the two round
    # differently per platform. A wrong ratio would be out by more than ten.
    assert room.needed == pytest.approx(len(sample.location) * per_character, abs=2.0)


def test_a_han_caption_beyond_the_budget_fails_the_photo(sample, browser):
    sample.location = "京都伏見稲荷大社臺北國永" * 4
    with pytest.raises(ValueError, match="the location does not fit"):
        strip.fit(
            spec_for(sample, ratio=(9, 16), signature=GOLDEN / "ink-mark.png", fonts=(HAN,)),
            browser=browser,
        )


# 5. Fonts: the user's order, reported when it takes more than one.


def test_registered_fonts_come_last_in_the_stack(sample):
    markup = strip.build_html(spec_for(sample, fonts=(HAN, HANGUL)))
    timeline = markup[markup.find('id="timeline"') :]
    stack = re.search(r"font-family:([^;]+);", timeline).group(1)
    families = [name.strip("'") for name in stack.split(",")]
    assert families.index(layout.FONT_READOUT) < families.index(strip.user_family(HAN))
    assert families.index(strip.user_family(HAN)) < families.index(strip.user_family(HANGUL))


def test_a_caption_spanning_two_fonts_is_reported():
    spread = glyphs.spread("臺北 서울", fonts=(HAN, HANGUL))
    assert spread == {"han-sample": "臺北", "hangul-sample": "서울"}
    assert "2 fonts" in glyphs.describe_spread(spread)


def test_one_font_that_covers_it_all_says_nothing():
    assert glyphs.spread("京都伏見稲荷大社", fonts=(HAN, HANGUL)) == {}


def test_latin_beside_han_is_not_a_spread():
    """Latin always comes from the bundled faces, so counting it means nothing.

    Every mixed caption would report otherwise, and a warning that fires on
    everything says nothing about anything.
    """
    assert glyphs.spread("京都 Kyoto", fonts=(HAN,)) == {}


def test_the_order_registered_is_the_order_used():
    """Never the language: 京都 is the same code points in Chinese and Japanese."""
    assert glyphs.spread("臺北 서울", fonts=(HANGUL, HAN)) == {
        "hangul-sample": "서울",
        "han-sample": "臺北",
    }


def test_characters_no_registered_font_covers_are_still_reported():
    assert glyphs.missing("서울", fonts=(HAN,)) == ["서", "울"]
    assert glyphs.missing("서울", fonts=(HAN, HANGUL)) == []


# 6. A font that does not load must not be rendered around.


def test_a_font_that_fails_to_load_stops_the_render(sample, browser):
    """document.fonts.ready resolves either way, so nothing else would notice.

    The page would lay out in a system substitute, be measured as if that were
    the design, and be photographed the same way.
    """
    sample.location = "京都"
    missing_font = HAN.parent / "no-such-font.ttf"
    with pytest.raises(RuntimeError, match="did not load"):
        strip.render(spec_for(sample, fonts=(missing_font,)), browser=browser)
