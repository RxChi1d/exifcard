"""Place the photo and the rendered strip onto one canvas.

The photo is copied, never resampled, unless an explicit output width forces a
resize. That is the whole reason the renderer only draws the strip: at default
settings the photo's pixels reach the output file exactly as they left the
camera.

Which is also what makes the colour space the photo's to decide. The card is
tagged with the photo's profile, so the strip -- drawn in sRGB, because that is
what the design's hex values mean -- has to be carried into that profile before
the two are joined. See `strip_in_profile`.
"""

from __future__ import annotations

from functools import cache
from io import BytesIO

import numpy as np
from PIL import Image, ImageCms

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


@cache
def _to_profile(icc_profile: bytes):
    """A transform from sRGB into the card's profile, built once per profile."""
    return ImageCms.buildTransformFromOpenProfiles(
        ImageCms.createProfile("sRGB"),
        ImageCms.ImageCmsProfile(BytesIO(icc_profile)),
        "RGB",
        "RGB",
    )


def strip_in_profile(strip: Image.Image, icc_profile: bytes | None) -> Image.Image:
    """The strip carried into the profile the finished card will be tagged with.

    The design states its colours as hex, which means sRGB, and the renderer
    emits exactly those numbers with no profile of its own. The card then
    inherits the photo's profile -- so on a Display P3 or Adobe RGB source those
    same numbers get read in the wrong space and the paper and ink shift.

    It is small today: the palette is near-neutral greys and warm off-whites,
    which sit close together in every space, and the design forbids accent
    colours. Measured, the worst of it is six levels on the darkest ink against
    Adobe RGB and one against Display P3. It stays small only for as long as
    that palette holds, which is not something this function should assume.

    The photo is never touched. It already is in its own profile, and moving it
    is what the whole pipeline exists to avoid.
    """
    if not icc_profile:
        return strip
    try:
        return ImageCms.applyTransform(strip, _to_profile(icc_profile))
    except (ImageCms.PyCMSError, OSError):
        # An unreadable profile is the photo's problem, not a reason to fail the
        # card: the strip stays as it is, which is what it did before this
        # existed. The card is still tagged with the profile, so the photo -- the
        # subject -- remains correct.
        return strip


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
