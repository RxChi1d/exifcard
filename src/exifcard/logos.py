"""Brand logo lookup.

A brand with no bundled wordmark falls back to its name set in type. That is a
designed state, not an error: the spec defines exactly how the text stand-in
should look, so an unknown camera still produces a correct card.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ASSETS = Path(__file__).parent / "assets" / "logos"


@dataclass(frozen=True)
class LogoRule:
    make: str
    file: str
    model_prefix: str | None = None


@cache
def _rules() -> tuple[LogoRule, ...]:
    manifest = tomllib.loads((ASSETS / "logos.toml").read_text(encoding="utf-8"))
    return tuple(
        LogoRule(
            make=entry["make"].upper(),
            file=entry["file"],
            model_prefix=(entry.get("model_prefix") or None),
        )
        for entry in manifest.get("logo", [])
    )


def find(make_key: str, model: str | None) -> Path | None:
    """Return the logo file for a normalized Make, or None to fall back to text."""
    if not make_key:
        return None
    model_upper = (model or "").strip().upper()
    for rule in _rules():
        if rule.make != make_key:
            continue
        if rule.model_prefix and not model_upper.startswith(rule.model_prefix):
            continue
        path = ASSETS / rule.file
        if path.exists():
            return path
    return None
