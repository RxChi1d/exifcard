"""Read EXIF and turn it into the strings the card prints.

Anything EXIF does not supply is left out of the card. Nothing is ever replaced
with a placeholder: an empty line reads as deliberate restraint, "Unknown Lens"
reads as a bug.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree

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

    ``equivalent`` arrives already corrected for a Lightroom crop when the
    photo records one (see ``cropped_equivalent``); this only chooses and
    rounds.

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


_CRS = "{http://ns.adobe.com/camera-raw-settings/1.0/}"

# Develop settings that warp the frame before the crop is laid on it, with the
# value each takes when untouched. Any other value means the crop rectangle is
# no longer a region of the original frame, so its share of the diagonal is not
# its share of the angle of view.
_WARP_DEFAULTS = {
    "PerspectiveUpright": 0.0,
    "PerspectiveVertical": 0.0,
    "PerspectiveHorizontal": 0.0,
    "PerspectiveRotate": 0.0,
    "PerspectiveAspect": 0.0,
    "PerspectiveScale": 100.0,
    "PerspectiveX": 0.0,
    "PerspectiveY": 0.0,
    "LensProfileDistortionScale": 100.0,
    "LensManualDistortionAmount": 0.0,
}

# Lightroom straightens by at most this much in either direction.
_MAX_CROP_ANGLE = 45.0

# Sensor proportions a crop may imply before it is treated as a bad record.
_ASPECT_RANGE = (1 / 3, 3.0)


@dataclass(frozen=True)
class LightroomCrop:
    """A Camera Raw crop: two opposite corners of the straightened rectangle,
    in coordinates normalised to the original frame, and the straightening
    angle in degrees."""

    left: float
    top: float
    right: float
    bottom: float
    angle: float = 0.0


def _camera_raw_settings(xmp) -> dict[str, str]:
    """Every Camera Raw setting in an XMP packet, keyed by local name.

    Lightroom writes them as attributes of rdf:Description, other tools as
    child elements; both are read. Matching is by namespace, not by the crs:
    prefix, which a packet is free to rename.
    """
    if not xmp:
        return {}
    if isinstance(xmp, bytes):
        xmp = xmp.decode("utf-8", "replace")
    try:
        root = ElementTree.fromstring(xmp.strip().strip("\x00"))
    except ElementTree.ParseError:
        return {}
    settings: dict[str, str] = {}
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.startswith(_CRS):
                settings[key.removeprefix(_CRS)] = value
        if element.tag.startswith(_CRS) and len(element) == 0:
            settings[element.tag.removeprefix(_CRS)] = (element.text or "").strip()
    return settings


def _number(settings: dict[str, str], key: str) -> float | None:
    try:
        value = float(settings[key])
    except (KeyError, ValueError):
        return None
    return value if math.isfinite(value) else None


def lightroom_crop(settings: dict[str, str]) -> LightroomCrop | None:
    """The crop recorded in Camera Raw settings, or None when there is no
    usable one. A record that cannot describe a real crop -- corners out of
    order or off the frame, an angle Lightroom cannot produce -- is the same
    as no record: there is nothing trustworthy to correct with."""
    if settings.get("HasCrop", "").strip().lower() != "true":
        return None
    values = [_number(settings, k) for k in ("CropLeft", "CropTop", "CropRight", "CropBottom")]
    if any(v is None for v in values):
        return None
    left, top, right, bottom = values
    angle = _number(settings, "CropAngle") if "CropAngle" in settings else 0.0
    if angle is None or abs(angle) > _MAX_CROP_ANGLE:
        return None
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        return None
    return LightroomCrop(left, top, right, bottom, angle)


def _warped(settings: dict[str, str]) -> bool:
    for key, default in _WARP_DEFAULTS.items():
        if key not in settings:
            continue
        value = _number(settings, key)
        if value is None or abs(value - default) > 1e-9:
            return True
    return False


def original_aspect(crop: LightroomCrop, width: int, height: int) -> float | None:
    """Width over height of the original frame, recovered from the crop.

    The corners are normalised separately on each axis, so the frame's
    proportions are not in the record -- but the exported image has the crop's
    own proportions, and the angle relates the two: the corner-to-corner
    vector runs at atan(height/width) + angle in original pixels. Measured on
    every straightened sample, this gives the sensor's 3:2 exactly; the
    opposite sign does not.
    """
    dx = crop.right - crop.left
    dy = crop.bottom - crop.top
    slope = math.tan(math.atan2(height, width) + math.radians(crop.angle))
    if slope <= 0:
        return None
    aspect = dy / (dx * slope)
    low, high = _ASPECT_RANGE
    return aspect if low <= aspect <= high else None


def crop_scale(crop: LightroomCrop, width: int, height: int) -> float | None:
    """The share of the original diagonal the crop keeps.

    The 35mm equivalent is defined on the diagonal, and straightening only
    turns the rectangle, so its diagonal is the distance between the two
    recorded corners whatever the angle. Only the output's proportions enter,
    never its size: a downscaled export gives the same answer.
    """
    aspect = original_aspect(crop, width, height)
    if aspect is None:
        return None
    dx = crop.right - crop.left
    dy = crop.bottom - crop.top
    scale = math.hypot(dx * aspect, dy) / math.hypot(aspect, 1.0)
    return scale if 0.0 < scale <= 1.0 + 1e-3 else None


def cropped_equivalent(equivalent, xmp, width: int, height: int) -> tuple[float | None, str | None]:
    """The 35mm equivalent after a Lightroom crop, and a warning if one was
    recorded but could not be applied.

    Only the equivalent is corrected. Without one the card prints the
    physical length, a property of the lens that no crop changes. ``width``
    and ``height`` are the photo as displayed, after its orientation.
    """
    if equivalent is None or float(equivalent) <= 0:
        return equivalent, None
    settings = _camera_raw_settings(xmp)
    crop = lightroom_crop(settings)
    if crop is None:
        return equivalent, None
    camera = format_focal_length(None, equivalent)
    if _warped(settings):
        return equivalent, (
            f"Lightroom crop not applied to the focal length: a perspective or distortion "
            f"correction moves the crop off the original frame, so the camera's {camera} is shown"
        )
    scale = crop_scale(crop, width, height)
    if scale is None:
        return equivalent, None
    readings = [scale]
    if height > width:
        # A portrait export may state its crop against the sensor rather than
        # the turned frame; no sample settles which. Apply only when every
        # reading that implies a possible sensor prints the same number.
        flipped = LightroomCrop(crop.left, crop.top, crop.right, crop.bottom, -crop.angle)
        for turned in (crop_scale(crop, height, width), crop_scale(flipped, height, width)):
            if turned is not None:
                readings.append(turned)
    printed = {round(float(equivalent) / r) for r in readings}
    if len(printed) > 1:
        return equivalent, (
            f"Lightroom crop not applied to the focal length: this portrait crop reads as "
            f"{' or '.join(f'{p}mm' for p in sorted(printed))} depending on how Lightroom "
            f"oriented it, so the camera's {camera} is shown"
        )
    return float(equivalent) / readings[0], None


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
        xmp = img.info.get("xmp")
        stored_size = img.size
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

    width, height = stored_size
    if data.orientation in TRANSPOSED_ORIENTATIONS:
        width, height = height, width
    equivalent, crop_warning = cropped_equivalent(
        ifd.get(_TAG["FocalLengthIn35mmFilm"]), xmp, width, height
    )
    if crop_warning:
        data.warnings.append(crop_warning)

    data.exposure = SEPARATOR.join(
        part
        for part in (
            format_focal_length(ifd.get(_TAG["FocalLength"]), equivalent),
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
