"""The info strip's design canvas, and how it adapts.

Scale used to come straight from the card's width, which punished portrait
photos: their long edge is the height, so the card is narrower and the type
shrank with it. The strip now has its own canvas width D, derived from the
photo's proportions and from the text's own measured demands, and is scaled
from there.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from exifcard import layout, logos, strip
from exifcard.metadata import CardData

pytest.importorskip("playwright.sync_api")

GOLDEN = __import__("pathlib").Path(__file__).parent / "golden"


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
        location="Fushimi Inari, Kyoto",
    )


@pytest.mark.parametrize(
    "width,height,expected",
    [
        (3, 2, 760.0),  # landscape: untouched
        (1, 1, 604.0),
        (4, 5, 483.2),
        (2, 3, 450.0),  # clamped
        (9, 16, 450.0),  # clamped
    ],
)
def test_canvas_width_follows_the_photo_proportions(width, height, expected):
    assert layout.canvas_width_for(width, height) == pytest.approx(expected, abs=0.1)


def test_a_narrower_canvas_means_larger_type_on_the_same_card():
    landscape = layout.SIZE_EXPOSURE * (1000 / layout.canvas_width_for(3, 2))
    portrait = layout.SIZE_EXPOSURE * (1000 / layout.canvas_width_for(9, 16))
    assert portrait > landscape * 1.6


def fitted(data, browser, ratio=(3, 2), **kwargs):
    spec = strip.StripSpec(
        data=data,
        card_width=1000,
        canvas_width=layout.canvas_width_for(*ratio),
        logo=logos.find("FUJIFILM", "X-T5"),
        **kwargs,
    )
    return strip.fit(spec, browser=browser)


def demanded(data, browser, ratio=(3, 2), **kwargs):
    spec = strip.StripSpec(
        data=data,
        card_width=1000,
        canvas_width=layout.canvas_width_for(*ratio),
        logo=logos.find("FUJIFILM", "X-T5"),
        signature=GOLDEN / "ink-mark.png",
        **kwargs,
    )
    return strip.demand(spec, browser=browser)


# The three tests below assert the measurement rather than the appearance.
# This defect survived because every existing check asked whether the card
# looked right, and a card whose caption is painted over its signature looks
# right everywhere except the one place nothing was looking.


def test_content_that_fits_is_measured_as_fitting(sample, browser):
    need = demanded(sample, browser)
    assert need.loose < need.available


def test_a_caption_wider_than_its_box_is_measured_at_its_full_width(sample, browser):
    """#row2left is compressible, so a long caption stops the box, not the text.

    Summing border boxes therefore returned the clamp itself and reported a
    comfortable fit while the caption painted across the signature.
    """
    long_caption = CardData(**{**sample.__dict__, "location": "A" * 40})

    modest = demanded(sample, browser, ratio=(9, 16))
    excessive = demanded(long_caption, browser, ratio=(9, 16))

    assert excessive.loose > modest.loose
    assert excessive.tight > excessive.available


def test_a_lens_name_wider_than_its_box_is_measured_at_its_full_width(sample, browser):
    """The same clamp, reached by the row's other line.

    With no caption to share the row, the old measurement returned exactly the
    available width -- the arithmetic signature of a clamped box, and the
    reason the second stage of the adaptation had never run for this row.
    """
    long_lens = CardData(**{**sample.__dict__, "lens": "L" * 91, "location": ""})

    need = demanded(long_lens, browser)

    assert need.tight > need.available


def test_landscape_with_short_names_is_left_alone(sample, browser):
    result = fitted(sample, browser)
    assert result.canvas_width == layout.CANVAS_MAX
    assert result.tight is False


def test_a_narrow_card_tightens_before_it_gives_up_type_size(sample, browser):
    result = fitted(sample, browser, ratio=(9, 16))
    assert result.tight is True
    assert result.canvas_width == layout.CANVAS_MIN  # no size lost


def test_names_that_still_will_not_fit_widen_the_canvas(sample, browser):
    long_names = CardData(
        **{
            **sample.__dict__,
            "body": "EOS R5 Mark II",
            "lens_brand": "TAMRON",
            "lens": "70-180mm F2.8 Di III VC VXD G2",
        }
    )
    result = fitted(long_names, browser, ratio=(9, 16))
    assert result.tight is True
    assert result.canvas_width > layout.CANVAS_MIN


def test_fitting_depends_only_on_the_photo_at_hand(sample, browser):
    """Adaptation has to run both ways.

    A one-way ratchet would leave a card shrunken because the previous photo
    in the batch had a long lens name.
    """
    long_names = CardData(**{**sample.__dict__, "body": "EOS R5 Mark II"})
    fitted(long_names, browser, ratio=(9, 16))
    after = fitted(sample, browser, ratio=(9, 16))
    assert after.canvas_width == layout.CANVAS_MIN


@pytest.mark.golden
def test_landscape_output_is_unchanged_from_before_the_canvas_existed(sample, browser):
    """The compensation must not touch landscape at all."""
    spec = strip.StripSpec(
        data=sample,
        card_width=layout.BASELINE_WIDTH,
        canvas_width=layout.canvas_width_for(3, 2),
        logo=logos.find("FUJIFILM", "X-T5"),
        signature=GOLDEN / "ink-mark.png",
    )
    rendered = np.asarray(strip.render(spec, browser=browser))
    reference = np.asarray(Image.open(GOLDEN / "bleed.png").convert("RGB"))
    assert np.array_equal(rendered, reference)
