"""The locations file is written by hand; the tool only appends to it."""

from __future__ import annotations

from exifcard import locations


def test_scaffold_creates_a_file_with_empty_captions(tmp_path):
    target = tmp_path / locations.FILENAME
    added = locations.scaffold(target, [("a.jpg", "2026.03.14 X-T5"), ("b.jpg", "")])

    assert added == 2
    assert locations.load(target) == {"a.jpg": "", "b.jpg": ""}
    assert "# 2026.03.14 X-T5" in target.read_text(encoding="utf-8")


def test_scaffold_never_touches_what_is_already_there(tmp_path):
    target = tmp_path / locations.FILENAME
    target.write_text(
        '# my own note\n"a.jpg" = "Fushimi Inari, Kyoto"\n',
        encoding="utf-8",
    )

    added = locations.scaffold(target, [("a.jpg", ""), ("b.jpg", "")])

    assert added == 1
    text = target.read_text(encoding="utf-8")
    assert "# my own note" in text
    assert locations.load(target) == {"a.jpg": "Fushimi Inari, Kyoto", "b.jpg": ""}


def test_scaffold_is_idempotent(tmp_path):
    target = tmp_path / locations.FILENAME
    locations.scaffold(target, [("a.jpg", "")])
    assert locations.scaffold(target, [("a.jpg", "")]) == 0


def test_missing_file_reads_as_no_captions(tmp_path):
    assert locations.load(tmp_path / "nothing.toml") == {}
