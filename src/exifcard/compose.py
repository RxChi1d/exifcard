"""Place the photo and the rendered strip onto one canvas.

The photo is copied, never resampled, unless an explicit output width forces a
resize. That is the whole reason the browser only renders the strip: at default
settings the photo's pixels reach the output file exactly as they left the
camera.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from . import layout

# EXIF orientation -> the transform that puts the photo the right way up.
_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def apply_orientation(photo: Image.Image, orientation: int) -> Image.Image:
    """Bake the EXIF rotation into the pixels.

    The output card carries Orientation=1, so this has to happen here: leaving
    the flag on and the pixels unrotated would make viewers rotate the whole
    card, text included.
    """
    transform = _TRANSPOSE.get(orientation)
    return photo.transpose(transform) if transform else photo


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def compose(
    photo: Image.Image,
    strip: Image.Image,
    frame: str,
    paper: str,
    card_width: int,
) -> Image.Image:
    """Assemble the card: paper, photo, strip.

    The strip arrives already rendered at the card's real width, so the only
    work here is deciding where the photo sits and drawing the hairline that
    keeps pale photos from dissolving into the paper in equal mode.
    """
    mode = layout.FRAMES[frame]
    scale = layout.scale_for(card_width)
    inset = round(mode.card_pad_side * scale)
    top = round(mode.card_pad_top * scale)

    photo_width = card_width - 2 * inset
    if photo.width != photo_width:
        photo = photo.resize((photo_width, round(photo.height * photo_width / photo.width)))

    if strip.width != card_width:
        strip = strip.resize((card_width, round(strip.height * card_width / strip.width)))

    card_height = top + photo.height + strip.height
    card = Image.new("RGB", (card_width, card_height), _hex_to_rgb(layout.PAPER[paper]))
    card.paste(photo, (inset, top))
    card.paste(strip, (0, top + photo.height))

    if mode.photo_hairline:
        _draw_hairline(card, inset, top, photo.width, photo.height, scale)
    return card


def _draw_hairline(
    card: Image.Image, x: int, y: int, width: int, height: int, scale: float
) -> None:
    """A one-pixel inset edge on the photo, at the spec's 9% ink over paper.

    Drawn by blending rather than stroking so it stays faithful to the CSS
    `inset 0 0 0 1px rgba(40,34,26,.09)` the design specifies.
    """
    thickness = max(1, round(scale))
    ink = np.array((40, 34, 26), dtype=np.float32)
    alpha = 0.09
    pixels = np.asarray(card).astype(np.float32)

    edges = (
        (slice(y, y + thickness), slice(x, x + width)),
        (slice(y + height - thickness, y + height), slice(x, x + width)),
        (slice(y, y + height), slice(x, x + thickness)),
        (slice(y, y + height), slice(x + width - thickness, x + width)),
    )
    for rows, cols in edges:
        pixels[rows, cols] = pixels[rows, cols] * (1 - alpha) + ink * alpha

    card.paste(Image.fromarray(pixels.round().clip(0, 255).astype(np.uint8)), (0, 0))
