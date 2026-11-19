"""HEIC in and HEIC out, through the same pillow-heif the card ships with.

These pin the behaviour a pillow-heif upgrade could move: a HEIC source opens
with its EXIF, a 10-bit source is noticed, a HEIC card is written as a tiled
grid and reads back at the size the renderer reported.
"""

from __future__ import annotations

import numpy as np
import pillow_heif
import pytest
from PIL import Image

from exifcard import encode, metadata, render

pillow_heif.register_heif_opener()


def _exif() -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0110] = "iPhone 16 Pro"
    ifd = exif.get_ifd(0x8769)
    ifd[0x920A] = 6.765
    ifd[0xA405] = 24
    ifd[0x829D] = 1.78
    ifd[0x829A] = 0.01
    ifd[0x8827] = 80
    ifd[0x9003] = "2026:03:14 08:12:00"
    return exif


@pytest.fixture
def heic(tmp_path):
    """An 8-bit HEIC photo carrying EXIF, as a phone writes one."""
    path = tmp_path / "IMG_0001.HEIC"
    image = Image.effect_mandelbrot((1200, 800), (-2, -1.5, 1, 1.5), 60).convert("RGB")
    image.save(path, format="HEIF", quality=90, exif=_exif().tobytes())
    return path


def test_a_heic_source_opens_with_its_exif(heic):
    with Image.open(heic) as image:
        image.load()
        assert image.size == (1200, 800)
        data = metadata.read(heic, image=image)
    assert data.body
    assert data.exposure.startswith("24mm")
    assert data.date == "2026.03.14"


def test_an_8_bit_heic_is_reported_as_8_bit(heic):
    assert encode.source_bit_depth(heic) == 8


def test_a_10_bit_heic_is_reported_as_wider_than_8_bit(tmp_path):
    path = tmp_path / "IMG_0002.HEIC"
    pixels = (np.random.default_rng(0).integers(0, 1024, (64, 96, 3)) << 6).astype(np.uint16)
    heif = pillow_heif.from_bytes(mode="RGB;16", size=(96, 64), data=pixels.tobytes())
    heif.save(str(path), quality=-1, save_to_12bit=False)
    assert encode.source_bit_depth(path) > 8


def test_a_heic_photo_renders_to_a_heic_card_that_reads_back(heic, tmp_path):
    destination = tmp_path / "out" / "card.heic"
    outcome = render.render(heic, destination, render.Options())

    assert destination.exists()
    with Image.open(destination) as card:
        card.load()
        assert card.format == "HEIF"
        assert card.size == outcome.card_size
        # The strip sits under the photo, so the card is taller than the photo.
        assert card.height > 800
        assert card.getexif().get(0x010F) == "Apple"


def test_a_heic_card_is_written_as_tiles(heic, tmp_path):
    # Tiling is what keeps a large card readable by libheif itself; a card
    # wider than one tile has to come back as a grid.
    destination = tmp_path / "out" / "card.heic"
    render.render(heic, destination, render.Options())
    heif = pillow_heif.open_heif(str(destination))
    assert heif.info.get("tiling"), "expected a tiled (grid) HEIC"
    assert heif.info["tiling"]["tile_width"] == encode.HEIC_TILE_SIZE


def test_a_jpeg_photo_can_be_written_as_a_heic_card(tmp_path):
    source = tmp_path / "DSC00001.JPG"
    Image.effect_mandelbrot((900, 600), (-2, -1.5, 1, 1.5), 40).convert("RGB").save(
        source, exif=_exif()
    )
    destination = tmp_path / "out" / "card.heic"
    outcome = render.render(source, destination, render.Options(fmt="heic"))
    with Image.open(destination) as card:
        card.load()
        assert card.size == outcome.card_size
