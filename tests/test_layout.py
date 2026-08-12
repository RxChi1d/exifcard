"""Scale arithmetic: the whole card is one design at different sizes."""

from __future__ import annotations

import pytest

from exifcard import layout


def test_baseline_width_is_its_own_scale():
    assert layout.scale_for(760) == 1.0
    assert layout.scale_for(7008) == pytest.approx(9.221, abs=1e-3)


def test_bleed_card_is_exactly_as_wide_as_the_photo():
    assert layout.card_width_for_photo(7008, "bleed") == 7008


def test_equal_card_grows_so_the_photo_keeps_its_native_size():
    # The photo is inset by 18px a side at the baseline. Rather than shrink the
    # photo to fit, the card widens, which is what keeps the pixels untouched.
    width = layout.card_width_for_photo(7008, "equal")
    scale = layout.scale_for(width)
    photo_area = width - 2 * layout.FRAMES["equal"].card_pad_side * scale
    assert photo_area == pytest.approx(7008)
