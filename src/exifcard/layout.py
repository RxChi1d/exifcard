"""Layout constants for the metadata card.

Every length here is expressed at the 760px design baseline. Rendering at any
other width multiplies all of them by the same scale factor, so the card is
always the same design, only larger or smaller.
"""

from __future__ import annotations

from dataclasses import dataclass

BASELINE_WIDTH = 760.0

# The info strip is laid out on its own canvas of width D and then scaled to
# the card, rather than scaling straight from the card's width. Deriving the
# scale from card width alone punishes portrait photos: their long edge is the
# height, so the card is narrower and the type shrinks with it -- a 9:16 phone
# shot ends up with lettering half the size of a landscape frame's.
#
#   a = photo height / photo width
#   D = clamp(PORTRAIT_REFERENCE / a, CANVAS_MIN, CANVAS_MAX)
#   info scale = card width / D
#
# A smaller D means larger type. CANVAS_MAX keeps landscape exactly as it was;
# PORTRAIT_REFERENCE is tuned so a portrait card viewed at the same height
# reads at the same size as a landscape one; CANVAS_MIN is the narrowest the
# info row itself fits in (exposure line ~271 + left group ~97 + column gap 20
# + side padding 40).
CANVAS_MAX = 760.0
CANVAS_MIN = 450.0
PORTRAIT_REFERENCE = 604.0

# Gear names widen the canvas without limit, because a cap would simply put the
# overrunning text back on top of the signature at whatever width the cap sat.
# This is where the card says so instead: past it the type is below 84% of
# baseline, which is a gear table entry waiting to be written, not a layout
# failure. A sensor, not a rule -- the card still renders.
CANVAS_WARN = 900.0

PAPER = {"warm": "#faf8f4", "white": "#ffffff"}

COLOR_BODY = "#26241f"
COLOR_EXPOSURE = "#33302b"
COLOR_LENS = "#6d665e"
COLOR_LENS_BRAND = "#8a8279"
COLOR_DATE = "#b3ada4"
COLOR_DIVIDER = "#dcd7ce"
COLOR_PHOTO_EDGE = "rgba(40,34,26,.09)"


@dataclass(frozen=True)
class FrameMode:
    """How much paper surrounds the photo."""

    card_pad_top: float
    card_pad_side: float
    info_pad_top: float
    info_pad_side: float
    info_pad_bottom: float
    photo_hairline: bool


# bleed: the photo runs to the top and both edges, paper only below it.
# equal: even paper on all four sides, plus a hairline so pale photos keep an
# edge on paper that is nearly the same tone.
FRAMES = {
    "bleed": FrameMode(0, 0, 22, 20, 22, False),
    "equal": FrameMode(18, 18, 20, 4, 20, True),
}

# Line boxes and row heights are stated outright rather than left to each
# font's own metrics. Otherwise the strip is a fraction of a pixel taller when
# a photo happens to carry a lens name, and an album of cards stops stacking
# evenly -- which is exactly what the fixed-height rule exists to prevent.
LINE_HEIGHT = 1.2
ROW1_HEIGHT = 18.0
ROW2_HEIGHT = 35.0

# Row 1: brand logo, divider, body model on the left; exposure readout right.
LOGO_HEIGHT = 11.0
LOGO_OPACITY = 0.88
DIVIDER_WIDTH = 1.0
DIVIDER_HEIGHT = 12.0
ROW1_LEFT_GAP = 11.0
ROW_GROUP_GAP = 20.0

SIZE_BODY = 13.5
TRACK_BODY = 0.04

SIZE_EXPOSURE = 12.5
TRACK_EXPOSURE = 0.1

# First response to an info row that will not fit: pull the exposure readout's
# tracking in and narrow the gap between the two column groups. Worth about
# 8-10% of the width, and it costs nothing in type size, so it is always tried
# before widening the canvas.
TRACK_EXPOSURE_TIGHT = 0.04
ROW_GROUP_GAP_TIGHT = 12.0

# Row 2: lens and timestamp stacked on the left, signature on the right.
ROW_GAP = 14.0
ROW2_LINE_GAP = 9.0

SIZE_LENS = 12.5
TRACK_LENS = 0.03
TRACK_LENS_BRAND = 0.1

SIZE_DATE = 9.0
TRACK_DATE = 0.1

# Han ink reaches 0.84em above the baseline where this row's monospace digits
# reach 0.74, so at one font-size a place name reads 13% taller than the date
# beside it -- the wrong way round for the quietest line on the card. Measured
# across ten faces (sans, serif and rounded, in TC, JP, KR and SC) the ratio
# that levels them spans 0.869 to 0.891, which is why this is one constant and
# not a per-font table: no font the user registers can fall far from it.
CJK_SIZE_RATIO = 0.88

SIGNATURE_WIDTH = 108.0
SIGNATURE_WIDTH_RANGE = (70.0, 180.0)
SIGNATURE_OPACITY = 0.7
SIGNATURE_BASELINE_NUDGE = -1.0

FONT_GEAR = "Archivo"
FONT_READOUT = "JetBrains Mono"
FONT_FALLBACK = "Noto Sans"

# The separator between exposure values, and between date and location.
SEPARATOR = " · "


def scale_for(card_width: float) -> float:
    """Scale factor that maps baseline lengths onto a card of this width."""
    return card_width / BASELINE_WIDTH


def canvas_width_for(photo_width: int, photo_height: int) -> float:
    """The info strip's design canvas width for a photo of these proportions.

    Landscape lands on CANVAS_MAX and is therefore untouched; the taller the
    photo, the narrower the canvas and the larger the type ends up once it is
    scaled to the card.
    """
    aspect = photo_height / photo_width
    return min(CANVAS_MAX, max(CANVAS_MIN, PORTRAIT_REFERENCE / aspect))


def card_width_for_photo(photo_width: int, frame: str) -> float:
    """Card width that lets the photo sit at its native pixel size.

    In bleed mode the photo spans the whole card. In equal mode it is inset by
    the frame padding on each side, so the card has to be correspondingly wider
    for the photo to avoid being resampled.
    """
    mode = FRAMES[frame]
    inset_fraction = 2 * mode.card_pad_side / BASELINE_WIDTH
    return photo_width / (1 - inset_fraction)
