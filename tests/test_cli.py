"""Batch behaviour: where cards land, and what a bad file costs."""

from __future__ import annotations

import re

from PIL import Image
from typer.testing import CliRunner

from exifcard.cli import app

runner = CliRunner()


def plain_output(result):
    return re.sub(r"\x1b\[[0-9;]*m", "", result.output)


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


def test_a_caption_too_long_to_fit_fails_only_its_own_photo(tmp_path):
    """The caption is held to the space the gear leaves it, and a photo whose
    caption overruns is reported rather than rendered with the text painted
    across the signature."""
    album = tmp_path / "album"
    photo(album / "fits.JPG")
    photo(album / "overruns.JPG")
    out = tmp_path / "out"

    captions = out / "album" / "locations.toml"
    captions.parent.mkdir(parents=True, exist_ok=True)
    captions.write_text(
        '"fits.JPG" = "Kyoto"\n"overruns.JPG" = "' + "A" * 200 + '"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["render", str(album), "--out", str(out), "--force"])

    assert (out / "album" / "fits.jpg").exists()
    assert not (out / "album" / "overruns.jpg").exists()
    assert result.exit_code == 1
    assert "overruns.JPG" in result.output
    assert "locations.toml" in result.output


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


def test_output_file_writes_to_exact_path_and_uses_target_format(tmp_path):
    source = photo(tmp_path / "source.jpg")
    target = tmp_path / "cards" / "original_exifcard.png"

    result = runner.invoke(app, ["render", str(source), "--output-file", str(target), "--force"])

    assert result.exit_code == 0, result.output
    assert target.is_file()
    with Image.open(target) as card:
        assert card.format == "PNG"
    assert not (tmp_path / "outputs").exists()


def test_output_file_rejects_multiple_photos(tmp_path):
    first = photo(tmp_path / "first.jpg")
    second = photo(tmp_path / "second.jpg")
    target = tmp_path / "cards" / "one-card.jpg"

    result = runner.invoke(
        app,
        ["render", str(first), str(second), "--output-file", str(target), "--force"],
    )

    assert result.exit_code != 0
    assert "--output-file requires exactly one photo" in plain_output(result)
    assert not target.exists()


def test_output_file_cannot_be_combined_with_output_root(tmp_path):
    source = photo(tmp_path / "source.jpg")
    target = tmp_path / "cards" / "card.jpg"

    result = runner.invoke(
        app,
        ["render", str(source), "--out", str(tmp_path / "out"), "--output-file", str(target)],
    )

    assert result.exit_code != 0
    assert "--out and --output-file cannot be used together" in plain_output(result)
    assert not target.exists()


def test_output_file_cannot_overwrite_source_even_with_force(tmp_path):
    source = photo(tmp_path / "source.jpg")
    original = source.read_bytes()

    result = runner.invoke(app, ["render", str(source), "--output-file", str(source), "--force"])

    assert result.exit_code != 0
    assert "must not overwrite the source photo" in result.output
    assert source.read_bytes() == original


def test_output_file_format_must_match_explicit_format(tmp_path):
    source = photo(tmp_path / "source.jpg")
    target = tmp_path / "cards" / "card.png"

    result = runner.invoke(
        app,
        ["render", str(source), "--output-file", str(target), "--format", "jpg", "--force"],
    )

    assert result.exit_code != 0
    assert "does not match the --output-file extension" in plain_output(result)
    assert not target.exists()


def test_output_file_dry_run_reports_exact_destination_without_writing(tmp_path):
    source = photo(tmp_path / "source.jpg")
    target = tmp_path / "cards" / "renamed.jpg"

    result = runner.invoke(app, ["render", str(source), "--output-file", str(target), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "".join(str(target).split()) in "".join(plain_output(result).split())
    assert not target.exists()


class _ok:
    returncode = 0
