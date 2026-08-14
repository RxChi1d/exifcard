"""Render the info strip with Typst.

Only the strip goes through the engine. The photo is never handed to it: that
keeps the photo's pixels, colour profile and bit depth untouched, and keeps the
renderer working on an image a few hundred pixels tall no matter how large the
photo is.

What the engine buys us is text: shaping with the font's own kerning, and
tracking at exactly the values the design specifies. The layout is resolved
here, in design units, before anything is drawn.

This replaced a headless Chromium. Four of that engine's behaviours had to be
either reproduced or deliberately dropped, and each is noted where it applies:

- Typst's default under horizontal overflow is to WRAP, which would silently
  produce two lines where the design guarantees one and change a height that
  has no relief mechanism. Every text leaf is therefore emitted inside a box
  fixed to its own measured natural width, which can only overflow.
- Nothing is left to the engine's own alignment. Every position is resolved
  here, which the design's fixed row heights and line boxes make possible, and
  which is where the template work is heading anyway: the layout belongs to the
  framework, the engine sets and rasterizes type.
- Line boxes and baselines follow the design's own numbers, NOT the browser's
  rounding. That is a deliberate break: the browser's arithmetic is what stops
  `tests/golden` running in CI. See `baseline_offset`.
- Typst has no opacity. A bundled SVG mark carries its own on the root element;
  a raster one has it folded into the alpha channel.
"""

from __future__ import annotations

import json
import re
import tempfile
from functools import cache
from io import BytesIO
from dataclasses import dataclass, replace
from pathlib import Path
from typing import NamedTuple

from PIL import Image

from . import layout
from .metadata import CardData

FONTS = Path(__file__).parent / "assets" / "fonts"

_FONT_FACES = [
    ("Archivo", "Archivo.ttf"),
    ("JetBrains Mono", "JetBrainsMono.ttf"),
    ("Noto Sans", "NotoSans.ttf"),
]

# Scripts written on an em square, whose ink runs taller than the Latin and
# monospace faces this card is set in. Halfwidth katakana (FF61-FF9F) is left
# out on purpose: it is not full-width, so it is not mis-sized to begin with.
_CJK = re.compile(
    r"[ᄀ-ᇿ　-〿぀-ヿ㐀-䶿一-鿿"
    r"가-힣豈-﫿！-｠￠-￦"
    r"\U00020000-\U0003134A]+"
)


@dataclass(frozen=True)
class StripSpec:
    """Everything that varies between one rendered strip and the next."""

    data: CardData
    card_width: float
    frame: str = "bleed"
    paper: str = "warm"
    logo: Path | None = None
    signature: Path | None = None
    signature_width: float = layout.SIGNATURE_WIDTH
    # Width of the design canvas the strip is laid out on before being scaled
    # to the card. See layout.canvas_width_for.
    canvas_width: float = layout.CANVAS_MAX
    # Whether the first-stage tightening is applied.
    tight: bool = False
    # Fonts the user registered, in their order, for what the bundled ones
    # cannot draw.
    fonts: tuple[Path, ...] = ()


class Demand(NamedTuple):
    """What a strip's rows require, against what its canvas offers them."""

    available: float
    loose: float
    tight: float


class Room(NamedTuple):
    """What the date and location line needs, against what is left for it."""

    available: float
    needed: float


@cache
def _family_name(path: Path) -> str:
    """The family the font file declares for itself.

    The browser path invented a family name and declared the file under it,
    because @font-face requires one. Typst indexes a directory and addresses a
    face by the name in its own `name` table, so the file is the authority and
    inventing a name here would simply fail to match.
    """
    from fontTools.ttLib import TTFont

    with TTFont(path, fontNumber=0, lazy=True) as font:
        for record in font["name"].names:
            if record.nameID == 16:
                return str(record)
        for record in font["name"].names:
            if record.nameID == 1:
                return str(record)
    return path.stem


# Typst lays out in points and rasterizes at a requested ppi. At 72 ppi one
# point is one pixel, so a design unit maps onto a point and the scale factor
# rides entirely on the ppi. Nothing in the design is ever pre-multiplied.
BASE_PPI = 72.0


class _Leaf(NamedTuple):
    """One text run, at the size and tracking it is actually set in."""

    key: str
    text: str
    font: str
    size: float
    track: float
    weight: int


def _face_of(family: str) -> Path:
    """The file behind a design font family."""
    return FONTS / dict(_FONT_FACES)[family]


def _faces(spec: StripSpec) -> tuple[Path, ...]:
    """Every font file in play, in the order the engine will try them."""
    return tuple(FONTS / filename for _, filename in _FONT_FACES) + tuple(spec.fonts)


def _check_fonts(spec: StripSpec) -> None:
    """A font the user asked for and did not get is an error, never a fallback."""
    for path in spec.fonts:
        if not path.is_file():
            raise RuntimeError(f"the registered font {path} did not load: no such file")


def _families(spec: StripSpec, primary: str) -> list[str]:
    """The font stack for a leaf: the design's face, then the user's.

    Same ordering rule as the CSS stack. A user font that covers Latin as well
    as Han would take over the gear names from anywhere earlier in the list.
    """
    return [primary, layout.FONT_FALLBACK] + [_family_name(path) for path in spec.fonts]


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _runs(text: str, size: float, track: float) -> list[tuple[str, float, float]]:
    """Split a string into runs, with CJK set at CJK_SIZE_RATIO.

    Mirrors `strip._typeset`. Han ink runs taller than the monospace digits
    beside it, so a mixed caption is levelled per run rather than per element.
    """
    out: list[tuple[str, float, float]] = []
    position = 0
    for run in _CJK.finditer(text):
        if run.start() > position:
            out.append((text[position : run.start()], size, track))
        out.append((run.group(), size * layout.CJK_SIZE_RATIO, track))
        position = run.end()
    if position < len(text):
        out.append((text[position:], size, track))
    return out


@cache
def _cmap(path: Path) -> frozenset[int]:
    from fontTools.ttLib import TTFont

    with TTFont(path, fontNumber=0, lazy=True) as font:
        return frozenset(font.getBestCmap())


def _shaping_runs(chunk: str, faces: tuple[Path, ...]) -> int:
    """How many runs the engine will shape this chunk in.

    A run ends wherever the covering font changes, which is what makes the
    tracking correction below a per-run quantity rather than a per-string one.
    """
    if not chunk:
        return 0
    runs = 1
    previous = None
    for character in chunk:
        chosen = next((face for face in faces if ord(character) in _cmap(face)), None)
        if previous is not None and chosen != previous:
            runs += 1
        previous = chosen
    return runs


def trailing_track(text: str, size: float, track: float, faces: tuple[Path, ...] = ()) -> float:
    """Tracking the engine drops where one shaping run meets the next.

    Tracking is space BETWEEN letters, so a run of n characters carries n-1
    units of it. Typst applies that per shaping run, and it starts a new run
    wherever the covering font changes -- `α7C II` is one string but two runs,
    the alpha from Noto Sans and the rest from Archivo. Each boundary therefore
    swallows one unit, and the string's width ends up depending on which font
    happens to cover which character. That is an inconsistency rather than a
    typographic choice, so the units are added back here.

    CSS goes further and applies letter-spacing after the last character too,
    so a tracked element in the browser carries one unit of empty space on its
    right edge. Typst's between-letters reading is the better typography, but
    the readout is flush right and the design's widths were settled against the
    browser, so dropping it would move the card by up to three design pixels.
    That is a separate question from the browser's platform-specific rounding,
    and unlike that rounding it behaves the same everywhere -- so it is kept,
    and changing it stays a design decision rather than a side effect.
    """
    total = 0.0
    for chunk, size_i, track_i in _runs(text, size, track):
        runs = _shaping_runs(chunk, faces) if faces else 1
        total += max(1, runs) * size_i * track_i
    return total


def _text_call(chunk: str, font_stack: list[str], size: float, track: float, weight: int) -> str:
    families = ", ".join(f'"{name}"' for name in font_stack)
    return (
        f'text(font: ({families},), size: {size:g}pt, weight: {weight}, '
        f'tracking: {track:g}em, top-edge: "ascender", bottom-edge: "descender", '
        f'"{_esc(chunk)}")'
    )


def _line(leaf: _Leaf, spec: StripSpec) -> str:
    """A single text leaf as one unbreakable line at its own natural width."""
    stack = _families(spec, leaf.font)
    parts = [
        _text_call(chunk, stack, size, track, leaf.weight)
        for chunk, size, track in _runs(leaf.text, leaf.size, leaf.track)
    ]
    joined = " + ".join(f"[#{p}]" for p in parts) if len(parts) > 1 else f"[#{parts[0]}]"
    height = line_box(leaf.size)
    # measure() first, then a box pinned to that width: the content can never be
    # given less room than it needs, so it overflows the parent instead of
    # reflowing into a second line.
    return (
        f"context {{ let c = {joined}; let w = measure(c).width; "
        f"box(width: w, height: {height:g}pt, align(horizon, c)) }}"
    )


def leaves(spec: StripSpec, tight: bool) -> list[_Leaf]:
    """Every text run the strip sets, in the order the rows place them."""
    d = spec.data
    exposure_track = layout.TRACK_EXPOSURE_TIGHT if tight else layout.TRACK_EXPOSURE
    out: list[_Leaf] = []
    if not spec.logo and d.brand_label:
        out.append(
            _Leaf("brand", d.brand_label, layout.FONT_GEAR, layout.SIZE_BODY,
                  layout.TRACK_EXPOSURE, 500)
        )
    if d.body:
        out.append(
            _Leaf("body", d.body, layout.FONT_GEAR, layout.SIZE_BODY, layout.TRACK_BODY, 500)
        )
    if d.exposure:
        out.append(
            _Leaf("exposure", d.exposure, layout.FONT_READOUT, layout.SIZE_EXPOSURE,
                  exposure_track, 400)
        )
    if d.lens_brand:
        out.append(
            _Leaf("lens_brand", d.lens_brand + " ", layout.FONT_GEAR, layout.SIZE_LENS,
                  layout.TRACK_LENS_BRAND, 400)
        )
    if d.lens:
        out.append(
            _Leaf("lens", d.lens, layout.FONT_GEAR, layout.SIZE_LENS, layout.TRACK_LENS, 400)
        )
    if d.timeline:
        out.append(
            _Leaf("timeline", d.timeline, layout.FONT_READOUT, layout.SIZE_DATE,
                  layout.TRACK_DATE, 400)
        )
    return out


def build_measure_source(spec: StripSpec) -> str:
    """A document that renders nothing and reports every leaf's natural width.

    Both tracking states are measured in one pass, so settling the canvas costs
    a single compile rather than one per state.
    """
    _check_fonts(spec)
    lines = [
        "#set page(width: 4000pt, height: auto, margin: 0pt)",
        "#set par(leading: 0pt, spacing: 0pt)",
    ]
    probes = []
    for tight in (False, True):
        for leaf in leaves(spec, tight):
            stack = _families(spec, leaf.font)
            parts = [
                _text_call(chunk, stack, size, track, leaf.weight)
                for chunk, size, track in _runs(leaf.text, leaf.size, leaf.track)
            ]
            joined = " + ".join(f"[#{p}]" for p in parts) if len(parts) > 1 else f"[#{parts[0]}]"
            probes.append((
                f"{'tight' if tight else 'loose'}:{leaf.key}",
                joined,
                trailing_track(leaf.text, leaf.size, leaf.track, _faces(spec)),
            ))
    body = "\n".join(
        f'#context [#metadata((k: "{key}", w: measure({content}).width.pt() + {pad:g})) <probe>]'
        for key, content, pad in probes
    )
    return "\n".join(lines) + "\n" + body + "\n"


def _fonts_argument(spec: StripSpec) -> list[str]:
    """Directories the engine indexes, having checked the files are really there.

    The engine takes directories, not files, so a registered font that does not
    exist would simply never be found and the caption would come out in whatever
    covered it next -- silently, and differently on every machine. A font the
    user asked for and did not get is an error.
    """
    _check_fonts(spec)
    return [str(FONTS)] + [str(path.parent) for path in spec.fonts]


def measure_leaves(spec: StripSpec) -> dict[str, float]:
    """Natural width, in design units, of every leaf in both tracking states."""
    import typst

    source = build_measure_source(spec)
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "measure.typ"
        doc.write_text(source, encoding="utf-8")
        found = json.loads(
            typst.query(
                str(doc),
                "<probe>",
                root=tmp,
                font_paths=_fonts_argument(spec),
                ignore_system_fonts=True,
            )
        )
    return {entry["value"]["k"]: entry["value"]["w"] for entry in found}


@cache
def _svg_aspect(path: Path) -> float:
    """Width over height for a bundled mark.

    The marks are SVG, so this comes off the document rather than out of a
    decoder: `viewBox` first, since a few of them carry only that, and the
    width and height attributes otherwise.
    """
    source = path.read_text(encoding="utf-8", errors="replace")
    box = re.search(r'viewBox="\s*([-\d.eE]+)[,\s]+([-\d.eE]+)[,\s]+([-\d.eE]+)[,\s]+([-\d.eE]+)', source)
    if box:
        return float(box.group(3)) / float(box.group(4))
    width = re.search(r'\bwidth="([\d.eE]+)', source)
    height = re.search(r'\bheight="([\d.eE]+)', source)
    if width and height:
        return float(width.group(1)) / float(height.group(1))
    raise ValueError(f"{path.name} states neither a viewBox nor a width and height")


def _logo_width(spec: StripSpec) -> float:
    """The logo's drawn width, which follows from its aspect at LOGO_HEIGHT."""
    if not spec.logo:
        return 0.0
    return layout.LOGO_HEIGHT * _svg_aspect(spec.logo)


def prepared_signature(path: Path) -> tuple[bytes, int, int]:
    """The signature cropped to its ink and faded, with the ink's own size.

    One mark serves a whole batch, and preparing it costs a decode, a crop and
    an alpha pass -- so it is done once per file rather than once per card, and
    per card it was being done four times over: the two fit measurements, the
    geometry, and the render.
    """
    stat = path.stat()
    return _prepared_signature(path, stat.st_mtime_ns, stat.st_size)


@cache
def _prepared_signature(path: Path, mtime: int, size: int) -> tuple[bytes, int, int]:
    with Image.open(path) as opened:
        mark = opened.convert("RGBA")
    # Scanned ink trails off into alpha values of 1 or 2, which would defeat a
    # bare getbbox() and leave the margin in place. The margin is what gets
    # sized, so leaving it renders the ink smaller than asked for and floating
    # above the baseline instead of sitting on it.
    box = mark.getchannel("A").point(lambda level: 255 if level > 8 else 0).getbbox()
    if box:
        mark = mark.crop(box)
    faded = mark.getchannel("A").point(lambda level: round(level * layout.SIGNATURE_OPACITY))
    mark.putalpha(faded)
    buffer = BytesIO()
    mark.save(buffer, format="PNG")
    return (buffer.getvalue(), mark.width, mark.height)


def _signature_box(spec: StripSpec) -> tuple[float, float]:
    """The signature's drawn size, bounded on both axes and cropped to its ink."""
    if not spec.signature:
        return (0.0, 0.0)
    _, width, height = prepared_signature(spec.signature)
    scale = min(spec.signature_width / width, layout.ROW2_HEIGHT / height)
    return (width * scale, height * scale)


def demand(spec: StripSpec) -> Demand:
    """What the rows require against what the canvas offers, in design units.

    Computed from the measured leaves by the same arithmetic the rows perform,
    rather than read back out of a rendered layout. Row width is the sum of its
    children plus its fixed gaps, which makes the requirement independent of
    the canvas width and lets the shortfall be closed in a single step.
    """
    widths = measure_leaves(spec)
    mode = layout.FRAMES[spec.frame]
    available = spec.canvas_width - 2 * mode.card_pad_side - 2 * mode.info_pad_side

    def row_widths(tight: bool) -> float:
        prefix = "tight" if tight else "loose"
        group_gap = layout.ROW_GROUP_GAP_TIGHT if tight else layout.ROW_GROUP_GAP

        left1: list[float] = []
        if spec.logo:
            left1.append(_logo_width(spec))
        elif f"{prefix}:brand" in widths:
            left1.append(widths[f"{prefix}:brand"])
        has_brand = bool(left1)
        if f"{prefix}:body" in widths:
            if has_brand:
                left1.append(layout.DIVIDER_WIDTH)
            left1.append(widths[f"{prefix}:body"])
        row1_left = sum(left1) + layout.ROW1_LEFT_GAP * max(0, len(left1) - 1)
        exposure = widths.get(f"{prefix}:exposure", 0.0)
        row1 = row1_left + (group_gap + exposure if exposure else 0.0)

        lens = widths.get(f"{prefix}:lens_brand", 0.0) + widths.get(f"{prefix}:lens", 0.0)
        timeline = widths.get(f"{prefix}:timeline", 0.0)
        row2_left = max(lens, timeline)
        signature = _signature_box(spec)[0]
        row2 = row2_left + (group_gap + signature if signature else 0.0)

        return max(row1, row2)

    return Demand(available=available, loose=row_widths(False), tight=row_widths(True))


def caption_room(spec: StripSpec) -> Room:
    """What the date and location line needs against the space beside the mark."""
    widths = measure_leaves(spec)
    prefix = "tight" if spec.tight else "loose"
    mode = layout.FRAMES[spec.frame]
    inner = spec.canvas_width - 2 * mode.card_pad_side - 2 * mode.info_pad_side
    group_gap = layout.ROW_GROUP_GAP_TIGHT if spec.tight else layout.ROW_GROUP_GAP
    signature = _signature_box(spec)[0]
    taken = signature + group_gap if signature else 0.0
    return Room(available=inner - taken, needed=widths.get(f"{prefix}:timeline", 0.0))


def fit(spec: StripSpec) -> StripSpec:
    """Settle the canvas on the gear, then hold the caption to what is left.

    Same two stages and the same two classes of content as the browser path:
    gear names are facts the card must print in full and may widen the canvas
    without limit; the caption is prose and may only tighten.
    """
    gear_only = replace(spec, data=replace(spec.data, location=""))
    need = demand(gear_only)

    if need.loose <= need.available:
        settled = replace(spec, tight=False)
    elif need.tight <= need.available:
        settled = replace(spec, tight=True)
    else:
        settled = replace(
            spec, tight=True, canvas_width=spec.canvas_width + (need.tight - need.available)
        )

    if not spec.data.location:
        return settled

    room = caption_room(settled)
    if room.needed <= room.available:
        return settled
    if not settled.tight:
        tightened = replace(settled, tight=True)
        room = caption_room(tightened)
        if room.needed <= room.available:
            return tightened

    raise ValueError(
        f"the location does not fit: it needs {room.needed:.0f} design px of the "
        f"{room.available:.0f} left beside the signature (canvas {settled.canvas_width:.0f}); "
        f"shorten it in locations.toml"
    )


def _faded(path: Path, opacity: float, destination: Path) -> Path:
    """The mark carrying its opacity itself, since Typst has no opacity property.

    The bundled marks are SVG, where the root element takes an `opacity`
    attribute and the renderer applies it to the whole tree -- the same thing
    the browser's `opacity` on the `<img>` does. Raster marks have it folded
    into the alpha channel instead, which composites identically because the
    paper behind is opaque.
    """
    destination.write_bytes(_faded_bytes(path, opacity, path.stat().st_mtime_ns))
    return destination


@cache
def _faded_bytes(path: Path, opacity: float, mtime: int) -> bytes:
    """Prepared once per mark, not once per card: a batch shares one body."""
    if path.suffix.lower() == ".svg":
        source = path.read_text(encoding="utf-8")
        return re.sub(r"<svg\b", f'<svg opacity="{opacity:g}"', source, count=1).encode("utf-8")
    with Image.open(path) as opened:
        mark = opened.convert("RGBA")
    mark.putalpha(mark.getchannel("A").point(lambda level: round(level * opacity)))
    buffer = BytesIO()
    mark.save(buffer, format="PNG")
    return buffer.getvalue()


def _signature_asset(spec: StripSpec, directory: Path) -> Path | None:
    """The prepared signature, written where the engine can read it."""
    if not spec.signature:
        return None
    target = directory / "signature.png"
    target.write_bytes(prepared_signature(spec.signature)[0])
    return target


class Boxes(dict):
    """Every element's box on the strip, in design units."""


def measure(spec: StripSpec) -> Boxes:
    """Where each element sits, computed rather than read back from an engine.

    The browser path asked the DOM where things had ended up. Here the layout is
    resolved in Python before anything is drawn, so the same arithmetic answers
    both this and `build_source` -- which means a geometry test cannot pass while
    the render disagrees with it.
    """
    d = spec.data
    mode = layout.FRAMES[spec.frame]
    widths = measure_leaves(spec)
    prefix = "tight" if spec.tight else "loose"
    side = mode.card_pad_side + mode.info_pad_side
    inner = spec.canvas_width - 2 * side

    row1_y = mode.info_pad_top
    row2_y = row1_y + layout.ROW1_HEIGHT + layout.ROW_GAP
    height = row2_y + layout.ROW2_HEIGHT + mode.info_pad_bottom

    band = line_box(layout.SIZE_BODY)
    left_y = row1_y + (layout.ROW1_HEIGHT - band) / 2
    exposure_width = widths.get(f"{prefix}:exposure", 0.0)
    exposure_y = row1_y + (layout.ROW1_HEIGHT - line_box(layout.SIZE_EXPOSURE)) / 2

    left_parts = []
    if spec.logo:
        left_parts.append(_logo_width(spec))
    elif f"{prefix}:brand" in widths:
        left_parts.append(widths[f"{prefix}:brand"])
    if f"{prefix}:body" in widths:
        if left_parts:
            left_parts.append(layout.DIVIDER_WIDTH)
        left_parts.append(widths[f"{prefix}:body"])
    left_width = sum(left_parts) + layout.ROW1_LEFT_GAP * max(0, len(left_parts) - 1)

    has_lens = bool(d.lens or d.lens_brand)
    lens_width = widths.get(f"{prefix}:lens_brand", 0.0) + widths.get(f"{prefix}:lens", 0.0)
    date_width = widths.get(f"{prefix}:timeline", 0.0)
    column_height = (
        (line_box(layout.SIZE_LENS) if has_lens else 0.0)
        + (line_box(layout.SIZE_DATE) if d.timeline else 0.0)
        + (layout.ROW2_LINE_GAP if has_lens and d.timeline else 0.0)
    )
    column_y = row2_y + layout.ROW2_HEIGHT - column_height

    signature_w, signature_h = _signature_box(spec)
    signature_y = row2_y + layout.ROW2_HEIGHT - signature_h - layout.SIGNATURE_BASELINE_NUDGE

    def box(x, y, w, h):
        return {"x": x, "y": y, "width": w, "height": h}

    boxes = Boxes(
        strip=box(0.0, 0.0, spec.canvas_width, height),
        info=box(mode.card_pad_side, 0.0, spec.canvas_width - 2 * mode.card_pad_side, height),
        row1=box(side, row1_y, inner, layout.ROW1_HEIGHT),
        row1left=box(side, left_y, left_width, band),
        row2=box(side, row2_y, inner, layout.ROW2_HEIGHT),
        row2left=box(side, column_y, max(lens_width, date_width), column_height),
        exposure=box(
            side + inner - exposure_width, exposure_y, exposure_width,
            line_box(layout.SIZE_EXPOSURE),
        ),
    )
    if spec.signature:
        boxes["signature"] = box(
            side + inner - signature_w, signature_y, signature_w, signature_h
        )
    return boxes


def build_source(spec: StripSpec, assets: dict[str, Path]) -> str:
    """The strip as a standalone Typst document on its design canvas.

    Every length stays at its design value; the output size rides on the ppi
    passed to the compiler, so nothing here is pre-multiplied.
    """
    d = spec.data
    mode = layout.FRAMES[spec.frame]
    paper = layout.PAPER[spec.paper]
    # The group gap is a minimum separation, not a drawn length: the left group
    # sits at the left edge and the readout at the right, and `fit` has already
    # guaranteed they clear each other by at least that much. So it settles the
    # canvas and never appears here.
    exposure_track = layout.TRACK_EXPOSURE_TIGHT if spec.tight else layout.TRACK_EXPOSURE
    side = mode.card_pad_side + mode.info_pad_side
    height = (
        mode.info_pad_top
        + layout.ROW1_HEIGHT
        + layout.ROW_GAP
        + layout.ROW2_HEIGHT
        + mode.info_pad_bottom
    )

    def line(key: str, text: str, font: str, size: float, track: float,
             weight: int, colour: str) -> str:
        return _line(_Leaf(key, text, font, size, track, weight), spec) + f".fill({colour})"

    # Every position is resolved here rather than delegated to the engine's own
    # alignment. The design already fixes each row's height and each line box,
    # so the numbers exist; and a grid cell sizes itself from its content, not
    # from a height declared on the box inside it, which left the exposure
    # readout half a pixel high. Placing outright also matches where this is
    # heading: the layout belongs to the framework, the engine sets and
    # rasterizes type.
    row1_y = mode.info_pad_top
    row2_y = row1_y + layout.ROW1_HEIGHT + layout.ROW_GAP

    # Row 1 is centred on the cross axis; the group's height is its tallest line.
    group_band = line_box(layout.SIZE_BODY)
    left_y = row1_y + (layout.ROW1_HEIGHT - group_band) / 2
    exposure_y = row1_y + (layout.ROW1_HEIGHT - line_box(layout.SIZE_EXPOSURE)) / 2

    # Row 2 is bottom-aligned, so the column's own height decides where it starts.
    has_lens = bool(d.lens or d.lens_brand)
    column_height = (
        (line_box(layout.SIZE_LENS) if has_lens else 0.0)
        + (line_box(layout.SIZE_DATE) if d.timeline else 0.0)
        + (layout.ROW2_LINE_GAP if has_lens and d.timeline else 0.0)
    )
    column_y = row2_y + layout.ROW2_HEIGHT - column_height
    date_y = column_y + (
        line_box(layout.SIZE_LENS) + layout.ROW2_LINE_GAP if has_lens else 0.0
    )
    signature_y = (
        row2_y + layout.ROW2_HEIGHT - _signature_box(spec)[1] - layout.SIGNATURE_BASELINE_NUDGE
    )

    row1_left: list[str] = []
    if spec.logo:
        # Centred in the group's line-box band, as align-items: center does.
        band = line_box(layout.SIZE_BODY)
        row1_left.append(
            f'box(width: {_logo_width(spec):g}pt, height: {band:g}pt, '
            f"place(top + left, dy: {(band - layout.LOGO_HEIGHT) / 2:g}pt, "
            f'image("{assets["logo"].name}", height: {layout.LOGO_HEIGHT:g}pt)))'
        )
    elif d.brand_label:
        row1_left.append(
            _emit(spec, "brand", d.brand_label, layout.FONT_GEAR, layout.SIZE_BODY,
                  layout.TRACK_EXPOSURE, 500, layout.COLOR_BODY, box_y=left_y)
        )
    if d.body:
        if row1_left:
            # Centred in a box the height of the row's line boxes, so the whole
            # left group is one height and nothing depends on the engine's own
            # cross-axis alignment.
            band = line_box(layout.SIZE_BODY)
            row1_left.append(
                f"box(width: {layout.DIVIDER_WIDTH:g}pt, height: {band:g}pt, "
                f"place(top + left, dy: {(band - layout.DIVIDER_HEIGHT) / 2:g}pt, "
                f"rect(width: {layout.DIVIDER_WIDTH:g}pt, height: {layout.DIVIDER_HEIGHT:g}pt, "
                f'fill: rgb("{layout.COLOR_DIVIDER}"), stroke: none)))'
            )
        row1_left.append(
            _emit(spec, "body", d.body, layout.FONT_GEAR, layout.SIZE_BODY,
                  layout.TRACK_BODY, 500, layout.COLOR_BODY, box_y=left_y)
        )

    exposure = (
        _emit(spec, "exposure", d.exposure, layout.FONT_READOUT, layout.SIZE_EXPOSURE,
              exposure_track, 400, layout.COLOR_EXPOSURE, box_y=exposure_y)
        if d.exposure
        else "[]"
    )

    lens_parts = []
    if d.lens_brand:
        lens_parts.append(
            _emit(spec, "lens_brand", d.lens_brand + " ", layout.FONT_GEAR, layout.SIZE_LENS,
                  layout.TRACK_LENS_BRAND, 400, layout.COLOR_LENS_BRAND, boxed=False)
        )
    if d.lens:
        lens_parts.append(
            _emit(spec, "lens", d.lens, layout.FONT_GEAR, layout.SIZE_LENS,
                  layout.TRACK_LENS, 400, layout.COLOR_LENS, boxed=False)
        )
    lens_pad = 0.0
    if d.lens_brand:
        lens_pad += trailing_track(
            d.lens_brand + " ", layout.SIZE_LENS, layout.TRACK_LENS_BRAND, _faces(spec)
        )
    if d.lens:
        lens_pad += trailing_track(d.lens, layout.SIZE_LENS, layout.TRACK_LENS, _faces(spec))
    lens = (
        _wrap_line(lens_parts, layout.SIZE_LENS, lens_pad, _face_of(layout.FONT_GEAR), column_y)
        if lens_parts
        else ""
    )

    timeline = (
        _emit(spec, "timeline", d.timeline, layout.FONT_READOUT, layout.SIZE_DATE,
              layout.TRACK_DATE, 400, layout.COLOR_DATE, box_y=date_y)
        if d.timeline
        else ""
    )

    column = [item for item in (lens, timeline) if item]
    row2_left = (
        f"stack(dir: ttb, spacing: {layout.ROW2_LINE_GAP:g}pt, " + ", ".join(column) + ")"
        if column
        else "[]"
    )

    signature = (
        f'box(image("{assets["signature"].name}", '
        f"width: {_signature_box(spec)[0]:g}pt, height: {_signature_box(spec)[1]:g}pt))"
        if "signature" in assets
        else "[]"
    )

    left_group = (
        f"stack(dir: ltr, spacing: {layout.ROW1_LEFT_GAP:g}pt, " + ", ".join(row1_left) + ")"
        if row1_left
        else "[]"
    )

    placements = [
        f"#place(top + left, dx: {side:g}pt, dy: {left_y:g}pt, {left_group})",
        f"#place(top + right, dx: {-side:g}pt, dy: {exposure_y:g}pt, {exposure})",
        f"#place(top + left, dx: {side:g}pt, dy: {column_y:g}pt, {row2_left})",
    ]
    if "signature" in assets:
        placements.append(
            f"#place(top + right, dx: {-side:g}pt, dy: {signature_y:g}pt, {signature})"
        )

    return f"""#set page(width: {spec.canvas_width:g}pt, height: {height:g}pt, margin: 0pt, \
fill: rgb("{paper}"))
#set par(leading: 0pt, spacing: 0pt)
#set text(fallback: true)

""" + "\n".join(placements) + "\n"


def _emit(spec: StripSpec, key: str, text: str, font: str, size: float, track: float,
          weight: int, colour: str, boxed: bool = True, box_y: float = 0.0) -> str:
    """One coloured, unbreakable text leaf."""
    stack = _families(spec, font)
    parts = [
        f"text(font: ({', '.join(f'\"{n}\"' for n in stack)},), size: {s:g}pt, "
        f"weight: {weight}, tracking: {t:g}em, fill: rgb(\"{colour}\"), "
        f'top-edge: "ascender", bottom-edge: "descender", "{_esc(chunk)}")'
        for chunk, s, t in _runs(text, size, track)
    ]
    joined = " + ".join(f"[#{p}]" for p in parts) if len(parts) > 1 else f"[#{parts[0]}]"
    if not boxed:
        return joined
    return _wrap_line(
        [joined], size, trailing_track(text, size, track, _faces(spec)), _face_of(font), box_y
    )


@cache
def _vertical_metrics(path: Path) -> tuple[float, float]:
    """The font's ascent and descent in em.

    All three bundled faces set USE_TYPO_METRICS, which is the flag that tells
    a layout engine to prefer the OS/2 typographic pair over the hhea one, so
    that is the pair read here.
    """
    from fontTools.ttLib import TTFont

    with TTFont(path, fontNumber=0, lazy=True) as font:
        upm = font["head"].unitsPerEm
        os2 = font["OS/2"]
        return (os2.sTypoAscender / upm, -os2.sTypoDescender / upm)


def line_box(size: float) -> float:
    """The line box height: exactly what the design asks for.

    The browser quantizes this to 1/64 of a pixel and a 13.5px line at 1.2 comes
    out 16.1875 rather than 16.2. That is Blink's layout unit showing through,
    not something the design asked for, and it is left behind here -- see the
    note on `baseline_offset`.
    """
    return size * layout.LINE_HEIGHT


def baseline_offset(path: Path, size: float) -> float:
    """Where the baseline sits, measured down from the line box's top.

    Half the leading, then the ascent. The leading goes NEGATIVE whenever the
    font's ascent plus descent exceeds the line box, as JetBrains Mono's 1.32em
    does against a 1.2 line, and the glyphs then overflow the box evenly at both
    ends rather than being pinned to one.

    The browser does not compute it this way. Blink rounds the ascent and the
    descent to whole pixels, floors the half-leading, and then snaps the painted
    baseline to a whole pixel again, which is why the exposure readout resolves
    to 35.5 and is drawn at 36. Reproducing that was tried and it matched to
    0.0000, but all of it is a browser's arithmetic on one platform rather than
    anything the design specifies -- and it is the reason `tests/golden` cannot
    run in CI, since the same rounding differs on Linux. Carrying it into a new
    renderer would carry that limitation with it, so the design's own numbers
    are used instead. The cost is that the card moves by up to half a design
    pixel from what the browser drew, which at the scale a card is rendered is
    a few pixels along a glyph edge.
    """
    ascent, descent = _vertical_metrics(path)
    return size * ((layout.LINE_HEIGHT - (ascent + descent)) / 2 + ascent)


def _wrap_line(parts: list[str], size: float, pad: float, face: Path, box_y: float = 0.0) -> str:
    """Pin content to its own natural width so it can only overflow, never wrap.

    `box_y` is unused now that the baseline is not snapped to the pixel grid;
    it stays because the placement reads more clearly with the box's position
    in hand, and because the snapping is the one thing a reader is most likely
    to come here looking for. See `baseline_offset`.
    """
    content = " + ".join(parts)
    height = line_box(size)
    ascent, _ = _vertical_metrics(face)
    top = baseline_offset(face, size) - ascent * size
    return (
        f"context {{ let c = {content}; "
        f"box(width: measure(c).width + {pad:g}pt, height: {height:g}pt, "
        f"place(top + left, dy: {top:g}pt, c)) }}"
    )


def render(spec: StripSpec) -> Image.Image:
    """Rasterize the strip at the card's real pixel width."""
    import typst

    _check_fonts(spec)

    scale = spec.card_width / spec.canvas_width
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        assets: dict[str, Path] = {}
        if spec.logo:
            assets["logo"] = _faded(
                spec.logo, layout.LOGO_OPACITY, directory / f"logo{spec.logo.suffix}"
            )
        signature = _signature_asset(spec, directory)
        if signature:
            assets["signature"] = signature
        doc = directory / "strip.typ"
        doc.write_text(build_source(spec, assets), encoding="utf-8")
        png = typst.compile(
            str(doc),
            format="png",
            ppi=BASE_PPI * scale,
            root=str(directory),
            font_paths=_fonts_argument(spec),
            ignore_system_fonts=True,
        )
    import io

    data = png if isinstance(png, bytes) else png[0]
    return Image.open(io.BytesIO(data)).convert("RGB")
