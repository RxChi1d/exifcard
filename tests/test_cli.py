"""Batch behaviour: where cards land, and what a bad file costs."""

from __future__ import annotations

import sys

import pytest
from PIL import Image
from typer.testing import CliRunner

from exifcard.cli import app

pytest.importorskip("playwright.sync_api")

runner = CliRunner()


def photo(path, size=(600, 400)):
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    exif[0x010F] = "SONY"
    exif[0x0110] = "ILCE-7CM2"
    Image.effect_mandelbrot(size, (-2, -1.5, 1, 1.5), 40).convert("RGB").save(
        path, exif=exif, quality=90
    )
    return path


def test_each_album_lands_in_a_folder_named_after_itself(tmp_path):
    """Two albums in one run must not funnel into one another's folder.

    They routinely share file numbers, so collapsing them would also mean
    same-named cards silently colliding.
    """
    photo(tmp_path / "kyoto" / "DSC00001.JPG")
    photo(tmp_path / "osaka" / "DSC00001.JPG")
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        ["render", str(tmp_path / "kyoto"), str(tmp_path / "osaka"), "--out", str(out), "--force"],
    )

    assert result.exit_code == 0, result.output
    assert (out / "kyoto" / "DSC00001.jpg").exists()
    assert (out / "osaka" / "DSC00001.jpg").exists()


def test_one_bad_file_does_not_cost_the_rest_of_the_batch(tmp_path):
    album = tmp_path / "album"
    photo(album / "good-1.JPG")
    photo(album / "good-2.JPG")
    (album / "broken.jpg").write_text("not an image")
    out = tmp_path / "out"

    result = runner.invoke(app, ["render", str(album), "--out", str(out), "--force"])

    assert (out / "album" / "good-1.jpg").exists()
    assert (out / "album" / "good-2.jpg").exists()
    assert not (out / "album" / "broken.jpg").exists()
    # The run still reports the failure, and still fails, so a script notices.
    assert result.exit_code == 1
    assert "broken.jpg" in result.output


def test_a_clean_run_exits_zero(tmp_path):
    album = tmp_path / "album"
    photo(album / "good.JPG")
    result = runner.invoke(app, ["render", str(album), "--out", str(tmp_path / "out"), "--force"])
    assert result.exit_code == 0, result.output


def test_dry_run_writes_nothing(tmp_path):
    album = tmp_path / "album"
    photo(album / "good.JPG")
    out = tmp_path / "out"

    result = runner.invoke(app, ["render", str(album), "--out", str(out), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "good.JPG" in result.output
    assert not out.exists()


def test_recursive_keeps_nested_folders_nested(tmp_path):
    """Flattening would merge subfolders from different albums.

    Two albums each with their own `raw/` would land in one directory, where
    same-numbered files then collide.
    """
    photo(tmp_path / "kyoto" / "top.JPG")
    photo(tmp_path / "kyoto" / "sub" / "nested.JPG")
    out = tmp_path / "out"

    result = runner.invoke(
        app, ["render", str(tmp_path / "kyoto"), "--recursive", "--out", str(out), "--force"]
    )

    assert result.exit_code == 0, result.output
    assert (out / "kyoto" / "top.jpg").exists()
    assert (out / "kyoto" / "sub" / "nested.jpg").exists()


def test_captions_are_read_from_the_album_folder(tmp_path):
    album = tmp_path / "kyoto"
    photo(album / "DSC00001.JPG")
    out = tmp_path / "out"
    (out / "kyoto").mkdir(parents=True)
    (out / "kyoto" / "locations.toml").write_text(
        '"DSC00001.JPG" = "Fushimi Inari, Kyoto"\n', encoding="utf-8"
    )

    result = runner.invoke(
        app, ["render", str(album), "--out", str(out), "--force", "--dry-run"]
    )

    # The console wraps long lines, so compare on collapsed whitespace.
    assert "Fushimi Inari, Kyoto" in " ".join(result.output.split())


def test_install_browser_passes_with_deps_through(monkeypatch):
    """CI runs this exact command, so its arguments have to be right.

    Without --with-deps on Linux the browser downloads but will not start,
    which is a failure a user meets long after the install appeared to work.
    """
    calls = []
    monkeypatch.setattr(
        "subprocess.run", lambda command, *a, **k: calls.append(command) or _ok()
    )

    runner.invoke(app, ["install-browser"])
    runner.invoke(app, ["install-browser", "--with-deps"])

    assert calls[0] == [sys.executable, "-m", "playwright", "install", "chromium"]
    assert calls[1] == [sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"]


class _ok:
    returncode = 0
