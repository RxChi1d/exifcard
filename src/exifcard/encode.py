"""Write the finished card.

Defaults are lossy, because a card is a derivative made for looking at and
sharing while the original stays in the library. What the defaults refuse to do
is throw away more than they have to: a JPEG is re-encoded with the quantization
tables and chroma sampling read off the source rather than a guessed quality
number, which on a 33MP camera file is the difference between a faithful copy
and losing two thirds of the data.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pillow_heif
from PIL import Image, JpegImagePlugin

pillow_heif.register_heif_opener()

# Formats we read and write, keyed by the extension we emit.
FORMATS = ("jpg", "png", "heic")

_SUFFIX_FORMAT = {
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".heic": "heic",
    ".heif": "heic",
}

DEFAULT_JPEG_QUALITY = 95
# HEIC quality is an x265 mapping, not a quantization scale: 70 lands at about
# the same fidelity as JPEG 95, measured on a real camera file.
DEFAULT_HEIC_QUALITY = 70
PNG_COMPRESS_LEVEL = 6

# libheif fails to produce a decodable image much above ~28MP unless the
# encoder splits the picture into a grid of tiles. Tiling costs about 1% in
# file size, so it is simply always on.
HEIC_TILE_SIZE = 1024

# JPEG minimum coded unit, which lossless DCT compositing has to land on.
MCU = 16


@dataclass
class EncodeResult:
    path: Path
    lossless: bool
    note: str = ""


def format_for(path: Path) -> str | None:
    """The output format implied by a file's extension."""
    return _SUFFIX_FORMAT.get(path.suffix.lower())


def source_jpeg_params(photo_path: Path) -> dict:
    """Quantization tables and chroma sampling as the camera wrote them.

    Only the lossless path wants these: jpegtran drops the source's DCT
    coefficients into the canvas, so the canvas has to be quantized the same
    way. Reusing them for ordinary output would make a card slightly larger
    than the photo it came from, which is not what a card is for.
    """
    with Image.open(photo_path) as im:
        if im.format not in ("JPEG", "MPO"):
            return {}
        im.load()
        return {
            "qtables": im.quantization,
            "subsampling": JpegImagePlugin.get_sampling(im),
        }


def source_subsampling(photo_path: Path) -> int | None:
    """The camera's chroma sampling, or None when it cannot be read.

    Worth carrying over even though the quantization tables are not: a camera
    that shot 4:2:2 keeps its colour resolution instead of being quietly
    halved to Pillow's 4:2:0 default, for about 8% more file size.
    """
    try:
        with Image.open(photo_path) as im:
            if im.format not in ("JPEG", "MPO"):
                return None
            im.load()
            return JpegImagePlugin.get_sampling(im)
    except (OSError, ValueError):
        return None


def jpegtran_available() -> bool:
    return shutil.which("jpegtran") is not None


def source_bit_depth(photo_path: Path) -> int:
    """Bits per channel in the source file.

    Pillow composites in 8 bits, so a 10-bit HEIF from a recent camera is
    narrowed on the way in. That is a real loss and the caller says so out
    loud rather than letting it pass unmentioned.
    """
    if photo_path.suffix.lower() not in (".heic", ".heif"):
        return 8
    try:
        frame = pillow_heif.open_heif(str(photo_path), convert_hdr_to_8bit=False)[0]
    except Exception:
        return 8
    return 16 if ";16" in frame.mode else 8


def can_composite_losslessly(photo: Image.Image) -> tuple[bool, str]:
    """Whether the photo can be dropped into the card without re-encoding.

    jpegtran copies DCT coefficients, which only works when the photo's edges
    land on a minimum coded unit boundary.
    """
    if not jpegtran_available():
        return False, "jpegtran is not installed (macOS: brew install jpeg-turbo)"
    # Sony and other makers attach a multi-picture block, which makes Pillow
    # report MPO. The primary image is an ordinary JPEG and jpegtran reads it
    # as one; -copy none leaves the extra block behind.
    if photo.format not in ("JPEG", "MPO"):
        return False, f"the source is {photo.format}, not JPEG"
    if photo.width % MCU or photo.height % MCU:
        return False, (
            f"the photo is {photo.width}x{photo.height}, "
            f"which is not a multiple of {MCU} in both axes"
        )
    return True, ""


def write_lossless_jpeg(
    canvas: Image.Image,
    photo_path: Path,
    offset: tuple[int, int],
    destination: Path,
    params: dict,
) -> None:
    """Composite at the DCT level so the photo's coefficients are copied verbatim.

    The canvas is encoded normally -- it is flat paper and text, which costs
    almost nothing -- and then the untouched source JPEG is dropped into place.
    """
    x, y = offset
    if x % MCU or y % MCU:
        raise ValueError(f"drop offset {offset} is not aligned to a {MCU}px boundary")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base.jpg"
        canvas.save(base, format="JPEG", **params)
        result = subprocess.run(
            ["jpegtran", "-copy", "none", "-drop", f"+{x}+{y}", str(photo_path), str(base)],
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", "replace").strip())
        destination.write_bytes(result.stdout)


def save(
    card: Image.Image,
    destination: Path,
    fmt: str,
    quality: int | None = None,
    subsampling: int | None = None,
    exif: bytes | None = None,
    icc_profile: bytes | None = None,
) -> None:
    """Encode the card in the requested format."""
    options: dict = {}
    if exif:
        options["exif"] = exif
    if icc_profile:
        options["icc_profile"] = icc_profile

    if fmt == "jpg":
        options["quality"] = DEFAULT_JPEG_QUALITY if quality is None else quality
        if subsampling is not None:
            options["subsampling"] = subsampling
        card.save(destination, format="JPEG", **options)

    elif fmt == "png":
        options.pop("exif", None)  # Pillow writes PNG EXIF only via a chunk we do not use
        card.save(destination, format="PNG", compress_level=PNG_COMPRESS_LEVEL, **options)

    elif fmt == "heic":
        pillow_heif.options.GRID_TILE_SIZE = HEIC_TILE_SIZE
        card.save(
            destination,
            format="HEIF",
            quality=DEFAULT_HEIC_QUALITY if quality is None else quality,
            chroma=444,
            **options,
        )

    else:
        raise ValueError(f"unsupported output format: {fmt}")
