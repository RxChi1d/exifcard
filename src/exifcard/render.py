"""Turn one photo into one card."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pillow_heif
from PIL import Image

from . import compose, encode, glyphs, layout, logos, metadata, strip

pillow_heif.register_heif_opener()


@dataclass
class Options:
    frame: str = "bleed"
    paper: str = "warm"
    width: int | None = None
    fmt: str | None = None
    quality: int | None = None
    lossless: bool = False
    exif_mode: str = "all"
    signature: Path | None = None
    signature_width: float = layout.SIGNATURE_WIDTH
    gear: metadata.GearTables | None = None
    location: str = ""


@dataclass
class Outcome:
    destination: Path
    card_size: tuple[int, int]
    lossless: bool
    notes: list[str]


# EXIF tags stripped in "safe" mode: where the photo was taken, and which
# individual camera took it.
_GPS_IFD = 0x8825
_SERIAL_TAGS = (0xA431, 0xA435, 0xA430)


def _exif_bytes(photo_path: Path, mode: str) -> bytes | None:
    """The EXIF block to attach to the card, with orientation neutralized."""
    if mode == "none":
        return None
    with Image.open(photo_path) as im:
        exif = im.getexif()
        if not exif:
            return None
        exif[0x0112] = 1  # rotation is baked into the pixels now
        if mode == "safe":
            exif.pop(_GPS_IFD, None)
            for tag in _SERIAL_TAGS:
                exif.get_ifd(0x8769).pop(tag, None)
    return exif.tobytes()


def plan_destination(photo: Path, out_dir: Path, fmt: str) -> Path:
    return out_dir / f"{photo.stem}.{fmt}"


def resolve_format(photo: Path, requested: str | None) -> str:
    """Output format follows the input unless asked otherwise.

    Staying in the source format keeps each file on the encoder that suits it:
    converting an already-compressed JPEG to HEIC costs ten times the encoding
    time to save a few percent, because the new encoder spends its bits
    faithfully reproducing the old encoder's artefacts.
    """
    if requested:
        return requested
    return encode.format_for(photo) or "jpg"


def render(photo_path: Path, destination: Path, options: Options, browser=None) -> Outcome:
    notes: list[str] = []
    fmt = resolve_format(photo_path, options.fmt)

    with Image.open(photo_path) as source:
        source.load()
        data = metadata.read(photo_path, image=source, gear=options.gear)
        data.location = options.location
        notes.extend(data.warnings)

        photo = compose.apply_orientation(source, data.orientation)
        photo.format = source.format
        icc = source.info.get("icc_profile")

        card_width = (
            float(options.width)
            if options.width
            else layout.card_width_for_photo(photo.width, options.frame)
        )
        card_width_px = round(card_width)

        aspect = photo.width / photo.height
        if aspect > 3 or aspect < 1 / 3:
            notes.append(
                f"extreme aspect ratio {aspect:.2f}:1 -- the info strip scales with card "
                "width, so it will look proportionally large"
            )

        if encode.source_bit_depth(photo_path) > 8:
            notes.append(
                "the source carries more than 8 bits per channel; the card is composited "
                "in 8 bits, so tonal precision is reduced"
            )

        absent = glyphs.missing(
            data.brand_label, data.body, data.lens_brand, data.lens, data.exposure, data.timeline
        )
        if absent:
            notes.append(glyphs.describe(absent))

        logo = logos.find(data.make_key, data.body)
        spec = strip.StripSpec(
            data=data,
            card_width=card_width,
            frame=options.frame,
            paper=options.paper,
            logo=logo,
            signature=options.signature,
            signature_width=options.signature_width,
            canvas_width=layout.canvas_width_for(photo.width, photo.height),
        )
        spec = strip.fit(spec, browser=browser)
        strip_image = strip.render(spec, browser=browser)

        lossless = False
        if options.lossless:
            ok, reason = encode.can_composite_losslessly(photo)
            if not ok:
                raise RuntimeError(f"--lossless is not possible here: {reason}")
            if fmt != "jpg":
                raise RuntimeError("--lossless only applies to JPEG output")
            if options.width:
                raise RuntimeError("--lossless cannot resize the photo; drop --width")

        card = compose.compose(photo, strip_image, options.frame, options.paper, card_width_px)
        exif = _exif_bytes(photo_path, options.exif_mode)

        destination.parent.mkdir(parents=True, exist_ok=True)

        if options.lossless:
            mode = layout.FRAMES[options.frame]
            scale = layout.scale_for(card_width_px)
            offset = (round(mode.card_pad_side * scale), round(mode.card_pad_top * scale))
            if offset[0] % encode.MCU or offset[1] % encode.MCU:
                raise RuntimeError(
                    f"--lossless needs the photo to start on a {encode.MCU}px boundary; "
                    f"it starts at {offset} in {options.frame} mode"
                )
            encode.write_lossless_jpeg(
                card, photo_path, offset, destination, encode.source_jpeg_params(photo_path)
            )
            lossless = True
        else:
            encode.save(
                card,
                destination,
                fmt,
                quality=options.quality,
                subsampling=encode.source_subsampling(photo_path) if fmt == "jpg" else None,
                exif=exif,
                icc_profile=icc,
            )

        return Outcome(destination, card.size, lossless, notes)
