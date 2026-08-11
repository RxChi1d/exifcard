"""A small set of reference renders.

Geometry tests say every element is in the right place; these say the strip
still *looks* like itself. Kept deliberately small and tolerant, because pixel
comparison is sensitive to Chromium and font versions in a way that has nothing
to do with whether the design is correct. A failure here is a prompt to look at
the image, not proof of a bug.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from exifcard import layout, logos, strip
from exifcard.metadata import CardData

pytest.importorskip("playwright.sync_api")

GOLDEN = Path(__file__).parent / "golden"

# Anti-aliasing moves edge pixels around between browser builds; the design
# being wrong moves whole words.
MAX_MEAN_DIFFERENCE = 4.0


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
    "name,overrides",
    [
        ("bleed", {}),
        ("equal", {"frame": "equal"}),
        ("no-signature", {"signature": None}),
    ],
)
def test_strip_matches_its_reference(name, overrides, sample, browser):
    signature = overrides.pop("signature", GOLDEN / "ink-mark.png")
    spec = strip.StripSpec(
        data=sample,
        card_width=layout.BASELINE_WIDTH,
        logo=logos.find("FUJIFILM", "X-T5"),
        signature=signature,
        **overrides,
    )
    rendered = strip.render(spec, browser=browser)
    reference = Image.open(GOLDEN / f"{name}.png").convert("RGB")

    assert rendered.size == reference.size
    difference = np.abs(
        np.asarray(rendered).astype(np.int16) - np.asarray(reference).astype(np.int16)
    )
    assert difference.mean() < MAX_MEAN_DIFFERENCE
