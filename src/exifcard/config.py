"""User configuration.

One file, at a fixed location, holding the things that are stable across every
album: where the signature lives, and the gear name tables that grow over time.
Anything that varies per run is a command-line flag instead.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .metadata import GearTables


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "exifcard" / "config.toml"


@dataclass
class Config:
    signature: Path | None = None
    signature_width: float | None = None
    frame: str = "bleed"
    paper: str = "warm"
    out: str = "outputs"
    gear: GearTables = field(default_factory=GearTables)

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or default_config_path()
        if not path.exists():
            return cls()

        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        signature = raw.get("signature")
        gear = raw.get("gear", {})
        return cls(
            signature=Path(signature).expanduser() if signature else None,
            signature_width=raw.get("signature_width"),
            frame=raw.get("frame", "bleed"),
            paper=raw.get("paper", "warm"),
            out=raw.get("out", "outputs"),
            gear=GearTables(
                body=dict(gear.get("body", {})),
                lens=dict(gear.get("lens", {})),
                lens_brand=dict(gear.get("lens_brand", {})),
            ),
        )


EXAMPLE = """\
# exifcard configuration.
# Location: ~/.config/exifcard/config.toml (or $XDG_CONFIG_HOME/exifcard/config.toml)

# Path to your signature: a transparent PNG cropped tight to the ink.
# The file stays where it is; exifcard only reads it.
signature = "~/Pictures/private/signature.png"
signature_width = 108        # baseline px, 70-180

frame = "bleed"              # bleed for screen, equal for print
paper = "warm"               # warm or white
out = "outputs"              # default output root, relative to where you run the command

# Display names. Keys are the raw EXIF strings; anything not listed is shown
# exactly as the camera wrote it.
[gear.body]
"ILCE-7CM2" = "α7C II"

[gear.lens]
"TAMRON 25-200mm F2.8-5.6 A075 E" = "25-200mm F2.8-5.6"

# For third-party lenses whose LensModel omits the maker's name.
[gear.lens_brand]
"17-70mm F/2.8 DiIII-A VC RXD B070X" = "TAMRON"
"""
