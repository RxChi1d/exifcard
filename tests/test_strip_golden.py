"""Byte-exact reference renders, on every platform.

The renderer this replaced could not hold this: its output depended on the
platform's own text rounding, so pixel comparison had to stay a local check and
CI never saw it. That was the reason for moving off it, which makes this the
test that has to be able to fail.

Hence `array_equal` rather than a tolerance. A tolerant comparison would pass
whether or not the guarantee holds, and would be worthless for the one thing it
exists to decide.

The references are recorded on macOS. A failure elsewhere is the finding.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from exifcard import layout, logos, strip
from exifcard.metadata import CardData

GOLDEN = Path(__file__).parent / "golden"


def _card(**overrides) -> CardData:
    fields = dict(
        make="FUJIFILM",
        make_key="FUJIFILM",
        brand_label="FUJIFILM",
        body="X-T5",
        lens_brand="SIGMA",
        lens="56mm F1.4 DC DN",
        exposure="56mm · f/1.4 · 1/250s · ISO 400",
        date="2026.03.14",
        location="",
    )
    fields.update(overrides)
    return CardData(**fields)


CASES = {
    # The bundled mark is an SVG carrying its own opacity, so this covers the
    # vector path as well as both text faces.
    "strip-bleed": dict(
        data=_card(),
        frame="bleed",
        logo=logos.find("FUJIFILM", "X-T5"),
        signature=GOLDEN / "ink-mark.png",
    ),
    # Different padding, and the text stand-in instead of a mark.
    "strip-equal": dict(data=_card(brand_label="NIKON", body="D90"), frame="equal"),
    # The narrowest canvas: the largest scale factor, so any rounding that is
    # not scale-invariant shows up here first.
    "strip-narrow": dict(data=_card(), canvas_width=layout.CANVAS_MIN),
    # A registered font, a fallback boundary mid-string, and the CJK size ratio.
    "strip-han": dict(
        data=_card(location="京都"),
        fonts=(GOLDEN / "han-sample.ttf",),
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_render_is_identical_on_every_platform(name):
    spec = strip.StripSpec(card_width=layout.BASELINE_WIDTH, **CASES[name])
    rendered = np.asarray(strip.render(spec).convert("RGB"))
    reference = np.asarray(Image.open(GOLDEN / f"{name}.png").convert("RGB"))

    assert rendered.shape == reference.shape, (
        f"{name}: rendered {rendered.shape} against reference {reference.shape}"
    )
    if not np.array_equal(rendered, reference):
        difference = np.abs(rendered.astype(np.int16) - reference.astype(np.int16))
        pytest.fail(
            f"{name}: the render differs from the reference recorded on macOS -- "
            f"mean {difference.mean():.3f}, max {difference.max()}, "
            f"{(difference.max(axis=2) > 0).mean() * 100:.2f}% of pixels. "
            "The output is still platform-bound."
        )
