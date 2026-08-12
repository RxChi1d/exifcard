"""The package has to be installable, which no other test would notice.

A duplicate asset entry once made the wheel fail to build at all, while every
behavioural test kept passing: they all run from the source tree, where the
files are simply there.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    out = tmp_path_factory.mktemp("wheel")
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"wheel build failed:\n{result.stderr}")
    return next(out.glob("*.whl"))


def test_runtime_assets_ship_with_the_package(wheel):
    names = zipfile.ZipFile(wheel).namelist()

    assert "exifcard/assets/fonts/Archivo.ttf" in names
    assert "exifcard/assets/fonts/NotoSans.ttf" in names
    assert "exifcard/assets/logos/logos.toml" in names
    assert "exifcard/assets/logos/sony.svg" in names
    # The font licences travel with the fonts, as the OFL requires.
    assert any(name.endswith("OFL-archivo.txt") for name in names)


def test_the_entry_point_is_declared(wheel):
    entry_points = zipfile.ZipFile(wheel).read(
        next(n for n in zipfile.ZipFile(wheel).namelist() if n.endswith("entry_points.txt"))
    )
    assert b"exifcard = exifcard.cli:app" in entry_points
