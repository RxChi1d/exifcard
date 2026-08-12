"""Read EXIF and turn it into the strings the card prints.

Anything EXIF does not supply is left out of the card. Nothing is ever replaced
with a placeholder: an empty line reads as deliberate restraint, "Unknown Lens"
reads as a bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from PIL import ExifTags, Image

from . import names
from .layout import SEPARATOR

_TAG = {name: tag for tag, name in ExifTags.TAGS.items()}

# EXIF orientation values that mean the stored pixels are rotated.
TRANSPOSED_ORIENTATIONS = {5, 6, 7, 8}

# Corporate suffixes that appear in the Make field but never on the camera.
_MAKE_NOISE = re.compile(
    r"\b(CORPORATION|CORP|COMPANY|CO|LTD|INC|IMAGING|GROUP|HOLDINGS|AG|KK|K\.K)\b\.?",
    re.IGNORECASE,
)


@dataclass
class CardData:
    """Everything the strip renderer needs about one photo."""

    make: str = ""
    make_key: str = ""
    brand_label: str = ""
    body: str = ""
    lens_brand: str = ""
    lens: str = ""
    exposure: str = ""
    date: str = ""
    location: str = ""
    orientation: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def timeline(self) -> str:
        """The date and location line, either part of which may be absent."""
        return SEPARATOR.join(p for p in (self.date, self.location) if p)


def clean(value) -> str:
    """Trim an EXIF string.

    Cameras pad these fields to a fixed length with NUL bytes -- Fujifilm's
    LensModel arrives with 29 of them -- and those survive an ordinary strip(),
    so every table lookup silently misses until they are removed.
    """
    if value is None:
        return ""
    return str(value).replace("\x00", "").strip()


def normalize_make(make: str | None) -> str:
    """Reduce an EXIF Make field to a brand key for logo lookup."""
    text = clean(make).replace(",", " ")
    text = _MAKE_NOISE.sub(" ", text)
    return " ".join(text.split()).upper()


def format_focal_length(value, equivalent=None) -> str:
    """Focal length as an angle of view, not as a lens barrel measurement.

    The 35mm-equivalent value is preferred because the physical one cannot
    record what was actually framed: an iPhone shoots 6.765mm at both 30mm and
    48mm equivalent depending on the sensor crop, so two different framings
    would otherwise print the same number. Bodies that omit the tag -- mostly
    older DSLRs -- keep the physical value, which is what the card has always
    shown, so nothing reads worse than before, and a photo carrying neither
    prints nothing at all.

    Zero counts as absent at both steps. Some bodies write it instead of
    leaving the tag out, which says the same thing, and no lens is 0mm.
    """
    for candidate in (equivalent, value):
        if candidate is not None and float(candidate) > 0:
            return f"{round(float(candidate))}mm"
    return ""


def format_aperture(value) -> str:
    if value is None:
        return ""
    f = float(value)
    # f/1.4 keeps its decimal, f/8 does not gain a redundant ".0".
    return f"f/{f:g}"


def format_shutter(value) -> str:
    """Shutter speed as a photographer writes it, not as EXIF stores it."""
    if value is None:
        return ""
    seconds = float(value)
    if seconds <= 0:
        return ""
    if seconds >= 1:
        return f"{seconds:g}s"
    denominator = Fraction(seconds).limit_denominator(8000).denominator
    return f"1/{denominator}s"


def format_iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return ""
    return f"ISO {int(value)}"


def format_date(value: str | None) -> str:
    """EXIF timestamps are "YYYY:MM:DD HH:MM:SS"; the card shows YYYY.MM.DD."""
    if not value:
        return ""
    date_part = str(value).split(" ")[0]
    parts = date_part.split(":")
    if len(parts) != 3:
        return ""
    year, month, day = parts
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return ""
    return f"{year}.{int(month):02d}.{int(day):02d}"


@dataclass(frozen=True)
class GearTables:
    """User-supplied display-name overrides, layered on top of the built-ins."""

    body: dict[str, str] = field(default_factory=dict)
    lens: dict[str, str] = field(default_factory=dict)
    lens_brand: dict[str, str] = field(default_factory=dict)


def read(path: Path, image: Image.Image | None = None, gear: GearTables | None = None) -> CardData:
    """Extract card data from a photo."""
    gear = gear or GearTables()
    own_image = image is None
    img = image or Image.open(path)
    try:
        exif = img.getexif()
        ifd = exif.get_ifd(ExifTags.IFD.Exif)
    finally:
        if own_image:
            img.close()

    data = CardData()
    data.orientation = int(exif.get(_TAG["Orientation"], 1) or 1)

    raw_make = clean(exif.get(_TAG["Make"]))
    data.make = raw_make
    data.make_key = normalize_make(raw_make)
    data.brand_label = names.brand_label(data.make_key, raw_make)
    data.body = names.display_name(clean(exif.get(_TAG["Model"])), {**names.BODY_NAMES, **gear.body})

    data.lens_brand, data.lens = names.resolve_lens(
        clean(ifd.get(_TAG["LensModel"])),
        data.make,
        {**names.LENS_NAMES, **gear.lens},
        gear.lens_brand,
        body_model=clean(exif.get(_TAG["Model"])),
    )

    data.exposure = SEPARATOR.join(
        part
        for part in (
            format_focal_length(
                ifd.get(_TAG["FocalLength"]),
                ifd.get(_TAG["FocalLengthIn35mmFilm"]),
            ),
            format_aperture(ifd.get(_TAG["FNumber"])),
            format_shutter(ifd.get(_TAG["ExposureTime"])),
            format_iso(ifd.get(_TAG["ISOSpeedRatings"])),
        )
        if part
    )
    data.date = format_date(clean(ifd.get(_TAG["DateTimeOriginal"])))

    if not any((data.body, data.lens, data.exposure, data.date)):
        data.warnings.append("no EXIF metadata found; the info strip will be nearly empty")

    return data
