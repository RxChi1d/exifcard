"""Warn when the card's text needs a glyph no font has, or more than one font.

Neither raises: the browser silently draws a fallback or a tofu box, and the
card looks subtly wrong in a way nobody notices until much later. Archivo has
no Greek alpha, for instance, which matters the moment a Sony body is written
the way Sony writes it -- α7C II.

Coverage here is read from the font files, which says what each one could draw,
not which one the browser chose. That is the same information CSS resolves the
stack with, in the same order, but it is not a record of what happened.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

FONTS = Path(__file__).parent / "assets" / "fonts"

# Whitespace and control characters have no glyph anywhere and never need one.
_IGNORED = set(" \t\n\r ")


@cache
def _cmap(path: Path, stamp: tuple[int, int]) -> frozenset[int]:
    """The code points one font file can draw.

    Keyed on size and mtime as well as path, so that editing the fonts a run
    was told to use cannot leave a stale answer behind.
    """
    from fontTools.ttLib import TTFont

    with TTFont(path, fontNumber=0, lazy=True) as font:
        return frozenset(font.getBestCmap())


def _stamped(path: Path) -> frozenset[int]:
    stat = path.stat()
    return _cmap(path, (stat.st_size, stat.st_mtime_ns))


@cache
def _bundled() -> tuple[tuple[Path, frozenset[int]], ...]:
    return tuple((path, _stamped(path)) for path in sorted(FONTS.glob("*.ttf")))


def _ordered(fonts: tuple[Path, ...] = ()) -> tuple[tuple[Path, frozenset[int]], ...]:
    """Every font in play, in the order CSS will try them."""
    return _bundled() + tuple((path, _stamped(path)) for path in fonts)


def missing(*texts: str, fonts: tuple[Path, ...] = ()) -> list[str]:
    """Characters in these strings that no available font can draw."""
    coverage: set[int] = set()
    for _, covered in _ordered(fonts):
        coverage |= covered
    absent = {
        char
        for text in texts
        for char in text
        if char not in _IGNORED and ord(char) not in coverage
    }
    return sorted(absent)


def describe(absent: list[str]) -> str:
    listing = ", ".join(f"{char!r} (U+{ord(char):04X})" for char in absent)
    return f"no available font can draw {listing}; it will render as a fallback or a blank box"


def spread(text: str, fonts: tuple[Path, ...] = ()) -> dict[str, str]:
    """Which registered font each part of this text falls to, past the first.

    Text that reaches past one registered font is set in two designs at once
    and nothing on the card says so. Which one wins is the user's to arrange --
    the same code points serve Chinese and Japanese, so the order they wrote is
    the only honest answer -- but they can only arrange it if they are told.

    What this is looking for is one script drawn by more than one font -- Han
    from two files, say, whose characters were designed to different
    conventions. It is not "characters the bundled fonts do not cover", even
    though the two coincide today: Noto Sans has no Han, so skipping what the
    bundled faces cover happens to leave exactly the CJK behind. Bundle
    anything with Han in it and that reading would silence this warning for
    good, with nothing to show it had stopped firing.

    Latin is excluded because it always comes from the bundled faces, so
    counting it would report every mixed caption ever written.
    """
    bundled = set()
    for _, covered in _bundled():
        bundled |= covered

    used: dict[str, list[str]] = {}
    for char in text:
        if char in _IGNORED or ord(char) in bundled:
            continue
        for path in fonts:
            if ord(char) in _stamped(path):
                run = used.setdefault(path.stem, [])
                if char not in run:
                    run.append(char)
                break
    return {name: "".join(chars) for name, chars in used.items()} if len(used) > 1 else {}


def describe_spread(spread_by_font: dict[str, str]) -> str:
    parts = " / ".join(f"{name} -> {chars}" for name, chars in spread_by_font.items())
    return (
        f"the caption is set in {len(spread_by_font)} fonts, so letterforms differ "
        f"within one line: {parts}"
    )
