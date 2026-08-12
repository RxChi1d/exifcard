"""End to end: a photo goes in, a card comes out."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from exifcard import compose, encode, layout, render

pytest.importorskip("playwright.sync_api")


@pytest.fixture
def photo(tmp_path):
    """A 3:2 photo written the way a camera writes one: fine tables, 4:2:2."""
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
    # Camera-like encoding: near-flat quantization tables and 4:2:2, which is
    # what makes reusing them for output such an expensive mistake.
    image.save(path, exif=exif, qtables=[[1] * 64, [1] * 64], subsampling=1)
    return path


def test_card_is_the_photo_plus_a_strip(photo, tmp_path):
    destination = tmp_path / "out" / "card.jpg"
    outcome = render.render(photo, destination, render.Options())

    assert destination.exists()
    width, height = outcome.card_size
    assert width == 1200  # bleed mode: the card is exactly as wide as the photo
    assert height > 800  # and taller by the strip


def test_the_default_does_not_inherit_the_camera_quantization_tables(photo, tmp_path):
    """A card is a derivative for looking at, so it should be compressed.

    Reusing the source's tables made a card of a 33MP camera file come out at
    104% of the original's size -- no compression at all. Nothing else here
    would have caught it: every other check only asks whether the picture
    still looks right, and by that measure the uncompressed version looked
    better.
    """
    with Image.open(photo) as source:
        source.load()
        camera_tables = encode.source_jpeg_params(photo)

    default = tmp_path / "default.jpg"
    render.render(photo, default, render.Options())

    as_camera_wrote_it = tmp_path / "camera-tables.jpg"
    with Image.open(default) as card:
        card.load()
        card.save(as_camera_wrote_it, format="JPEG", **camera_tables)

    assert default.stat().st_size < as_camera_wrote_it.stat().st_size * 0.75


def test_the_default_stays_visually_faithful(photo, tmp_path):
    """Lossy, but not visibly so."""
    destination = tmp_path / "card.jpg"
    render.render(photo, destination, render.Options())

    original = np.asarray(Image.open(photo).convert("RGB")).astype(np.int16)
    card = np.asarray(Image.open(destination).convert("RGB")).astype(np.int16)
    difference = np.abs(card[: original.shape[0], : original.shape[1]] - original)

    assert difference.mean() < 2.0


def test_the_camera_chroma_sampling_is_carried_over(photo, tmp_path):
    """A camera that shot 4:2:2 keeps it, rather than being halved to 4:2:0."""
    from PIL import JpegImagePlugin

    destination = tmp_path / "card.jpg"
    render.render(photo, destination, render.Options())

    with Image.open(photo) as source, Image.open(destination) as card:
        source.load()
        card.load()
        assert JpegImagePlugin.get_sampling(card) == JpegImagePlugin.get_sampling(source)


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
