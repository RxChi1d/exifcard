"""Turning EXIF values into the strings the card prints."""

from __future__ import annotations

import pytest

from exifcard import metadata
from exifcard.metadata import CardData


@pytest.mark.parametrize(
    "value,expected",
    [(56, "56mm"), (56.4, "56mm"), (200.0, "200mm"), (2.22, "2mm"), (None, "")],
)
def test_focal_length_is_a_whole_number(value, expected):
    assert metadata.format_focal_length(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(1.4, "f/1.4"), (5.6, "f/5.6"), (8, "f/8"), (8.0, "f/8"), (None, "")],
)
def test_aperture_keeps_meaningful_decimals_only(value, expected):
    assert metadata.format_aperture(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (0.004, "1/250s"),
        (0.005, "1/200s"),
        (1, "1s"),
        (2.5, "2.5s"),
        (30, "30s"),
        (0, ""),
        (None, ""),
    ],
)
def test_shutter_reads_the_way_photographers_write_it(value, expected):
    assert metadata.format_shutter(value) == expected


@pytest.mark.parametrize("value,expected", [(400, "ISO 400"), ((250, 0), "ISO 250"), (None, "")])
def test_iso(value, expected):
    assert metadata.format_iso(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026:03:14 08:12:00", "2026.03.14"),
        ("2026:3:4 08:12:00", "2026.03.04"),
        ("garbage", ""),
        (None, ""),
    ],
)
def test_date_is_dotted_and_zero_padded(value, expected):
    assert metadata.format_date(value) == expected


def test_clean_removes_the_nul_padding_cameras_write():
    # Fujifilm pads LensModel to a fixed width; strip() alone leaves the NULs
    # in place and every table lookup then misses.
    assert metadata.clean("17-70mm F/2.8\x00\x00\x00") == "17-70mm F/2.8"
    assert metadata.clean(None) == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("SONY", "SONY"),
        ("NIKON CORPORATION", "NIKON"),
        ("RICOH IMAGING COMPANY, LTD.", "RICOH"),
        ("OLYMPUS IMAGING CORP.", "OLYMPUS"),
        ("Canon", "CANON"),
        ("Leica Camera AG", "LEICA CAMERA"),
        (None, ""),
    ],
)
def test_make_normalization_strips_the_legal_entity(raw, expected):
    assert metadata.normalize_make(raw) == expected


def test_timeline_omits_what_is_missing_rather_than_padding_it():
    assert CardData(date="2026.03.14", location="Kyoto").timeline == "2026.03.14 · Kyoto"
    assert CardData(date="2026.03.14").timeline == "2026.03.14"
    assert CardData(location="Kyoto").timeline == "Kyoto"
    assert CardData().timeline == ""
