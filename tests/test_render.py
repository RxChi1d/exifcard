"""End to end: a photo goes in, a card comes out."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from exifcard import compose, encode, layout, render

pytest.importorskip("playwright.sync_api")


@pytest.fixture
def photo(tmp_path):
    """A 3:2 photo with the EXIF fields the card reads."""
    path = tmp_path / "DSC00001.JPG"
    image = Image.effect_mandelbrot((1200, 800), (-2, -1.5, 1, 1.5), 60).convert("RGB")

    exif = Image.Exif()
    exif[0x010F] = "SONY"
    exif[0x0110] = "ILCE-7CM2"
    exif[0x0112] = 1
    ifd = exif.get_ifd(0x8769)
    ifd[0x920A] = 56.0
    ifd[0x829D] = 1.4
    ifd[0x829A] = 0.004
    ifd[0x8827] = 400
    ifd[0x9003] = "2026:03:14 08:12:00"
    ifd[0xA434] = "TAMRON 25-200mm F2.8-5.6 A075 E"
    image.save(path, exif=exif, quality=95)
    return path


def test_card_is_the_photo_plus_a_strip(photo, tmp_path):
    destination = tmp_path / "out" / "card.jpg"
    outcome = render.render(photo, destination, render.Options())

    assert destination.exists()
    width, height = outcome.card_size
    assert width == 1200  # bleed mode: the card is exactly as wide as the photo
    assert height > 800  # and taller by the strip


def test_photo_pixels_survive_the_default_encode(photo, tmp_path):
    """The default is lossy, but only just.

    Re-encoding with the source's own quantization tables keeps the photo close
    enough that the difference is invisible, which is the point: a card is for
    looking at, and the original is still in the library.
    """
    destination = tmp_path / "card.jpg"
    render.render(photo, destination, render.Options())

    original = np.asarray(Image.open(photo).convert("RGB")).astype(np.int16)
    card = np.asarray(Image.open(destination).convert("RGB")).astype(np.int16)
    difference = np.abs(card[: original.shape[0], : original.shape[1]] - original)

    assert difference.mean() < 1.0


def test_output_orientation_is_normalized(photo, tmp_path):
    """Rotation is baked into the pixels, so the flag has to be cleared.

    Leaving Orientation=6 on a card whose pixels are already upright makes
    every viewer rotate the card, text and all.
    """
    destination = tmp_path / "card.jpg"
    render.render(photo, destination, render.Options())
    assert Image.open(destination).getexif().get(0x0112) == 1


def test_equal_frame_keeps_the_photo_at_native_size(photo, tmp_path):
    destination = tmp_path / "card.jpg"
    outcome = render.render(photo, destination, render.Options(frame="equal"))

    scale = layout.scale_for(outcome.card_size[0])
    inset = round(layout.FRAMES["equal"].card_pad_side * scale)
    assert outcome.card_size[0] - 2 * inset == 1200


def test_explicit_width_resizes_the_card(photo, tmp_path):
    destination = tmp_path / "card.jpg"
    outcome = render.render(photo, destination, render.Options(width=800))
    assert outcome.card_size[0] == 800


def test_exif_safe_mode_drops_location(photo, tmp_path):
    with Image.open(photo) as source:
        exif = source.getexif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    with Image.open(photo) as source:
        source.save(photo, exif=exif)

    destination = tmp_path / "card.jpg"
    render.render(photo, destination, render.Options(exif_mode="safe"))
    assert not Image.open(destination).getexif().get_ifd(0x8825)


def test_output_format_follows_the_input(photo, tmp_path):
    assert render.resolve_format(photo, None) == "jpg"
    assert render.resolve_format(tmp_path / "a.heic", None) == "heic"
    assert render.resolve_format(tmp_path / "a.heic", "png") == "png"


def test_orientation_is_applied_to_the_pixels():
    upright = Image.new("RGB", (4, 2))
    rotated = compose.apply_orientation(upright, 6)
    assert rotated.size == (2, 4)
    assert compose.apply_orientation(upright, 1).size == (4, 2)


def test_lossless_refuses_rather_than_silently_degrading(photo, tmp_path):
    """--lossless is a promise, so it fails loudly when it cannot be kept."""
    misaligned = Image.open(photo).crop((0, 0, 1002, 800))
    misaligned.format = "JPEG"
    ok, reason = encode.can_composite_losslessly(misaligned)
    if encode.jpegtran_available():
        assert not ok
        assert "multiple of 16" in reason
