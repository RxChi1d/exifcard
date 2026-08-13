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


def _signature(path, width=1490, height=371, margin=0):
    """A mark of the given proportions, optionally floating in transparency."""
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle(
        (margin, margin, width - 1 - margin, height - 1 - margin),
        fill=(30, 28, 24, 255),
    )
    image.save(path)
    return path


def test_signature_sits_at_the_right_edge(sample, browser, tmp_path):
    signature = _signature(tmp_path / "signature.png")

    boxes = measure(sample, browser, signature=signature)
    right_edge = boxes["signature"]["x"] + boxes["signature"]["width"]

    assert boxes["signature"]["width"] == pytest.approx(layout.SIGNATURE_WIDTH)
    assert right_edge == pytest.approx(layout.BASELINE_WIDTH - layout.FRAMES["bleed"].info_pad_side)


@pytest.mark.parametrize("aspect", [6.0, 4.02, 3.09, 2.05, 1.0, 0.5])
def test_signature_stays_inside_its_row_at_any_aspect_ratio(sample, browser, tmp_path, aspect):
    """A signature squarer than the row cannot be allowed to grow upward.

    Row 2 has a fixed height and bottom-aligned contents, so an image sized by
    width alone leaves the exposure readout for it to collide with -- and the
    strip's fixed height means nothing gives way. Reported from a card where a
    2.05:1 signature was drawn across `ISO 1000`.
    """
    signature = _signature(tmp_path / f"sig{aspect}.png", height=int(1200 / aspect), width=1200)

    boxes = measure(sample, browser, signature=signature)
    mark, row2 = boxes["signature"], boxes["row2"]

    assert mark["height"] <= row2["height"] + 0.5
    assert mark["y"] >= row2["y"] - 0.5
    assert mark["width"] <= layout.SIGNATURE_WIDTH + 0.5
    # Shrinking to fit must not squash: the mark keeps the file's proportions.
    assert mark["width"] / mark["height"] == pytest.approx(aspect, rel=0.02)


def test_signature_is_cropped_to_its_ink(sample, browser, tmp_path):
    """Transparent margin must not be sized as though it were part of the mark."""
    tight = _signature(tmp_path / "tight.png", width=800, height=200)
    padded = _signature(tmp_path / "padded.png", width=1200, height=600, margin=200)

    assert measure(sample, browser, signature=padded)["signature"] == pytest.approx(
        measure(sample, browser, signature=tight)["signature"]
    )
