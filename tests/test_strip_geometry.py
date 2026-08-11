"""Geometry assertions against the spec's own numbers.

These read the layout back out of the browser rather than comparing pixels, so
they check the thing that actually matters -- where every element sits -- while
staying immune to the sub-pixel differences that make image comparison brittle.
"""

from __future__ import annotations

import pytest

from exifcard import layout, strip
from exifcard.metadata import CardData

pytest.importorskip("playwright.sync_api")


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


def measure(data, browser, **kwargs):
    spec = strip.StripSpec(data=data, card_width=layout.BASELINE_WIDTH, **kwargs)
    return strip.measure(spec, browser=browser)


def test_bleed_padding_matches_the_spec(sample, browser):
    boxes = measure(sample, browser)
    mode = layout.FRAMES["bleed"]

    assert boxes["row1"]["x"] == pytest.approx(mode.info_pad_side)
    assert boxes["row1"]["y"] == pytest.approx(mode.info_pad_top)
    assert boxes["row1"]["width"] == pytest.approx(layout.BASELINE_WIDTH - 2 * mode.info_pad_side)


def test_exposure_readout_is_flush_with_the_right_edge(sample, browser):
    boxes = measure(sample, browser)
    right_edge = boxes["exposure"]["x"] + boxes["exposure"]["width"]
    assert right_edge == pytest.approx(layout.BASELINE_WIDTH - layout.FRAMES["bleed"].info_pad_side)


def test_rows_are_separated_by_the_specified_gap(sample, browser):
    boxes = measure(sample, browser)
    gap = boxes["row2"]["y"] - (boxes["row1"]["y"] + boxes["row1"]["height"])
    assert gap == pytest.approx(layout.ROW_GAP)


def test_equal_frame_insets_the_whole_strip(sample, browser):
    boxes = measure(sample, browser, frame="equal")
    mode = layout.FRAMES["equal"]
    assert boxes["row1"]["x"] == pytest.approx(mode.card_pad_side + mode.info_pad_side)


def test_strip_height_does_not_depend_on_how_much_metadata_there_is(sample, browser):
    """The chin is a fixed band so an album of cards stacks evenly.

    A photo shot on a manual lens carries no aperture and no lens name; its card
    must still be exactly as tall as one shot on a reporting lens.
    """
    full = measure(sample, browser)["strip"]["height"]
    sparse = measure(CardData(body="D90", exposure="26mm · ISO 200"), browser)["strip"]["height"]
    empty = measure(CardData(), browser)["strip"]["height"]

    assert full == sparse == empty


def test_signature_sits_at_the_right_edge(sample, browser, tmp_path):
    from PIL import Image

    signature = tmp_path / "signature.png"
    Image.new("RGBA", (1490, 371), (0, 0, 0, 0)).save(signature)

    boxes = measure(sample, browser, signature=signature)
    right_edge = boxes["signature"]["x"] + boxes["signature"]["width"]

    assert boxes["signature"]["width"] == pytest.approx(layout.SIGNATURE_WIDTH)
    assert right_edge == pytest.approx(layout.BASELINE_WIDTH - layout.FRAMES["bleed"].info_pad_side)
