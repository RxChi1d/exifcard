"""Warn when a character has no glyph in any bundled font.

A missing glyph does not raise: the browser silently draws a fallback or a
tofu box, and the card looks subtly wrong in a way nobody notices until much
later. Archivo has no Greek alpha, for instance, which matters the moment a
Sony body is written the way Sony writes it -- α7C II.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

FONTS = Path(__file__).parent / "assets" / "fonts"

# Whitespace and control characters have no glyph anywhere and never need one.
_IGNORED = set(" \t\n\r ")


@cache
def _coverage() -> frozenset[int]:
    """Every code point the bundled fonts can draw between them."""
    from fontTools.ttLib import TTFont

    covered: set[int] = set()
    for path in sorted(FONTS.glob("*.ttf")):
        with TTFont(path, fontNumber=0, lazy=True) as font:
            covered.update(font.getBestCmap())
    return frozenset(covered)


def missing(*texts: str) -> list[str]:
    """Characters in these strings that no bundled font can draw."""
    coverage = _coverage()
    absent = {
        char
        for text in texts
        for char in text
        if char not in _IGNORED and ord(char) not in coverage
    }
    return sorted(absent)


def describe(absent: list[str]) -> str:
    listing = ", ".join(f"{char!r} (U+{ord(char):04X})" for char in absent)
    return f"no bundled font can draw {listing}; it will render as a fallback or a blank box"
