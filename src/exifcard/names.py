"""Display names for camera bodies and lenses.

EXIF reports internal model codes and bloated marketing names. The contract is
that whatever EXIF says is shown verbatim unless an entry explicitly overrides
it, so an unregistered camera still produces a correct card.
"""

from __future__ import annotations

# Seeded with the gear that has been through this tool; extend via the
# [gear.body] and [gear.lens] tables in the user config rather than here.
BODY_NAMES = {
    "ILCE-7CM2": "α7C II",
    "ILCE-7M4": "α7 IV",
    "ILCE-6700": "α6700",
    "NIKON D90": "D90",
    "NIKON D800E": "D800E",
    "Canon EOS R6m2": "EOS R6 Mark II",
    "Canon EOS 700D": "EOS 700D",
}

# How a maker's name is set when no wordmark is bundled for it. Without this,
# the card would print the legal entity from the EXIF Make field -- "NIKON
# CORPORATION" -- where the camera itself says Nikon.
BRAND_LABELS = {
    "NIKON": "Nikon",
    "LEICA": "Leica",
    "OM DIGITAL SOLUTIONS": "OM SYSTEM",
    "APPLE": "Apple",
    "GOOGLE": "Google",
    "SAMSUNG": "Samsung",
    "DJI": "DJI",
    "GOPRO": "GoPro",
    "PHASE ONE": "Phase One",
}


def brand_label(make_key: str, raw_make: str) -> str:
    """The maker's name as it should be set in type."""
    if not make_key:
        return ""
    return BRAND_LABELS.get(make_key, raw_make)


LENS_NAMES = {
    "TAMRON 25-200mm F2.8-5.6 A075 E": "25-200mm F2.8-5.6",
    "17-70mm F/2.8 DiIII-A VC RXD B070X": "17-70mm F2.8 Di III-A",
    "TAMRON 70-180mm F/2.8 Di III VC VXD G2": "70-180mm F2.8 G2",
    "XF33mmF1.4 R LM WR": "XF 33mm F1.4 R LM WR",
    "XF16-55mmF2.8 R LM WR": "XF 16-55mm F2.8",
}

# Some third-party lenses omit the maker from LensModel entirely -- Tamron's
# Fuji X mount lenses report only "17-70mm F/2.8 DiIII-A VC RXD B070X". Prefix
# detection cannot recover a name that is not in the string, so these are
# declared, keyed by the raw EXIF value.
LENS_BRANDS = {
    "17-70mm F/2.8 DiIII-A VC RXD B070X": "TAMRON",
}

# Third-party lens makers, matched against the start of the lens model string.
# The brand is only printed when it differs from the camera maker, so a Canon
# lens on a Canon body stays unlabelled.
LENS_BRAND_PREFIXES = (
    "TAMRON",
    "SIGMA",
    "TOKINA",
    "SAMYANG",
    "ROKINON",
    "ZEISS",
    "VOIGTLANDER",
    "LAOWA",
    "VILTROX",
    "TTARTISAN",
    "7ARTISANS",
)


def display_name(raw: str | None, table: dict[str, str]) -> str:
    """Look up a display name, falling back to the raw EXIF string."""
    key = (raw or "").strip()
    if not key:
        return ""
    return table.get(key, key)


def lens_brand_of(
    lens_model: str,
    camera_make: str,
    brand_table: dict[str, str] | None = None,
) -> str:
    """The lens maker, or empty when it is the camera's own.

    Repeating the camera maker's name on its own lens is noise, so that case
    reads as "no brand" and the card prints the model alone.
    """
    make = camera_make.strip().upper()

    declared = {**LENS_BRANDS, **(brand_table or {})}.get(lens_model)
    if declared:
        return "" if declared.upper() == make else declared.upper()

    upper = lens_model.upper()
    for prefix in LENS_BRAND_PREFIXES:
        if upper.startswith(prefix) and prefix != make:
            return prefix
    return ""


def strip_body_prefix(lens_model: str, body_model: str) -> str:
    """Drop the camera's own name from the front of its lens name.

    Phones write the whole device into LensModel -- "iPhone 16 Pro back triple
    camera 6.765mm f/1.78" -- and the card has already printed the body model
    one line above. Repeating it says nothing and crowds the row.
    """
    body = (body_model or "").strip()
    if not body or len(body) >= len(lens_model):
        return lens_model
    if lens_model.upper().startswith(body.upper()):
        return lens_model[len(body) :].strip(" -") or lens_model
    return lens_model


def resolve_lens(
    lens_model: str | None,
    camera_make: str,
    name_table: dict[str, str],
    brand_table: dict[str, str] | None = None,
    body_model: str = "",
) -> tuple[str, str]:
    """Turn a raw LensModel into the (brand, model) pair the card prints.

    Name tables are keyed on the raw EXIF string, so the lookup happens before
    anything is peeled off; peeling is only the fallback for lenses that have
    no table entry.
    """
    raw = (lens_model or "").strip()
    if not raw:
        return "", ""

    brand = lens_brand_of(raw, camera_make, brand_table)

    if raw in name_table:
        return brand, name_table[raw]

    if brand and raw.upper().startswith(brand):
        return brand, raw[len(brand) :].strip() or raw
    return brand, strip_body_prefix(raw, body_model)
