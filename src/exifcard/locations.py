"""Per-photo location captions.

A coordinate has many true names at once -- a road, a neighbourhood, a ward, a
city -- and reverse geocoding cannot know which one the photograph is about.
"Fushimi Inari" is a choice about what the picture shows, so captions are
written by a person; the tool only saves them the typing of filenames.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

FILENAME = "locations.toml"

_HEADER = """\
# Location captions, one per photo. Written by you; exifcard only ever appends
# new filenames to the end of this file and never edits lines that are here.
#
# Leave a value empty to print no location: the date line simply stands alone,
# which is a designed state rather than a gap.
"""


def load(path: Path) -> dict[str, str]:
    """Read a locations file, returning an empty map when there is none."""
    if not path.exists():
        return {}
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}


def scaffold(path: Path, entries: list[tuple[str, str]]) -> int:
    """Append photos that are not in the file yet, and report how many were added.

    Append-only on purpose: your captions, your comments and your ordering all
    survive re-runs, so shooting twenty more frames and running this again is
    always safe.
    """
    existing = load(path)
    new = [(name, note) for name, note in entries if name not in existing]
    if not new:
        return 0

    lines: list[str] = []
    if not path.exists():
        lines.append(_HEADER)
    elif path.read_text(encoding="utf-8") and not path.read_text(encoding="utf-8").endswith("\n"):
        lines.append("")

    for name, note in new:
        if note:
            lines.append(f"# {note}")
        lines.append(f'"{name}" = ""')

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return len(new)
