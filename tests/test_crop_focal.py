"""A Lightroom crop narrows the angle of view, so the 35mm equivalent follows it.

The crop values below are the develop settings of real exports from a Sony
full-frame body (3:2), copied as numbers only: the photos themselves carry GPS
and are not committed.
"""

from __future__ import annotations

import math

import pytest
from PIL import Image

from exifcard import metadata

CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"

# DSC00091: 200mm, cropped about 12% and straightened by 1.36 degrees.
DSC00091 = {"left": 0.043, "top": 0.0448, "right": 0.9128, "bottom": 0.9601, "angle": 1.36}
DSC00091_SIZE = (6196, 4131)


def _xmp(*, prefix="crs", elements=False, **settings) -> bytes:
    """An XMP packet holding Camera Raw settings, written the way Lightroom does."""
    pairs = {k: str(v) for k, v in settings.items()}
    if elements:
        body = "".join(f"<{prefix}:{k}>{v}</{prefix}:{k}>" for k, v in pairs.items())
        description = (
            f'<rdf:Description rdf:about="" xmlns:{prefix}="{CRS}">{body}</rdf:Description>'
        )
    else:
        attrs = " ".join(f'{prefix}:{k}="{v}"' for k, v in pairs.items())
        description = f'<rdf:Description rdf:about="" xmlns:{prefix}="{CRS}" {attrs}/>'
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        f"{description}"
        "</rdf:RDF></x:xmpmeta>"
        '<?xpacket end="w"?>'
    ).encode()


def _crop(left, top, right, bottom, angle=0.0, **extra) -> dict:
    return dict(
        HasCrop="True",
        CropLeft=left,
        CropTop=top,
        CropRight=right,
        CropBottom=bottom,
        CropAngle=angle,
        **extra,
    )


def _photo(
    tmp_path, size, *, xmp=None, physical=200.0, equivalent=200, orientation=None, name="DSC.jpg"
):
    path = tmp_path / name
    exif = Image.Exif()
    exif[0x010F] = "SONY"
    exif[0x0110] = "ILCE-7M5"
    if orientation:
        exif[0x0112] = orientation
    ifd = {0x920A: physical}
    if equivalent is not None:
        ifd[0xA405] = equivalent
    exif.get_ifd(0x8769).update(ifd)
    kwargs = {"exif": exif}
    if xmp is not None:
        kwargs["xmp"] = xmp
    Image.new("L", size).save(path, "JPEG", **kwargs)
    return path


def _focal(path) -> str:
    return metadata.read(path).exposure.split(" ")[0]


def _dsc00091(**extra) -> dict:
    d = DSC00091
    return _crop(d["left"], d["top"], d["right"], d["bottom"], d["angle"], **extra)


# --- the geometry ---------------------------------------------------------------


def test_crop_scale_is_the_kept_share_of_the_diagonal():
    d = DSC00091
    crop = metadata.LightroomCrop(d["left"], d["top"], d["right"], d["bottom"], d["angle"])
    scale = metadata.crop_scale(crop, *DSC00091_SIZE)
    assert scale == pytest.approx(0.8842, abs=0.0005)


def test_crop_scale_recovers_the_original_frame_from_the_angle():
    # The straightening angle is what makes the crop's own aspect differ from
    # the original's; with its sign reversed the same numbers imply a 1.66:1
    # sensor, which no Sony body has. Every sample resolves to 3:2 this way.
    d = DSC00091
    crop = metadata.LightroomCrop(d["left"], d["top"], d["right"], d["bottom"], d["angle"])
    assert metadata.original_aspect(crop, *DSC00091_SIZE) == pytest.approx(1.5, abs=0.001)


def test_crop_scale_ignores_export_resizing():
    # Only the output's aspect enters the formula, so a "long edge 2048"
    # export of the same crop gives the same answer.
    d = DSC00091
    crop = metadata.LightroomCrop(d["left"], d["top"], d["right"], d["bottom"], d["angle"])
    full = metadata.crop_scale(crop, 6196, 4131)
    small = metadata.crop_scale(crop, 2048, round(2048 * 4131 / 6196))
    assert small == pytest.approx(full, abs=0.001)


def test_an_uncropped_frame_keeps_its_whole_diagonal():
    crop = metadata.LightroomCrop(0.0, 0.0, 1.0, 1.0, 0.0)
    assert metadata.crop_scale(crop, 6000, 4000) == pytest.approx(1.0)


# --- through read() -------------------------------------------------------------


def test_read_prints_the_cropped_equivalent(tmp_path):
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**_dsc00091()))
    assert _focal(photo) == "226mm"
    assert metadata.read(photo).warnings == []


@pytest.mark.parametrize(
    "crop,size,camera,expected",
    [
        # DSC00098: straightened 1.13 degrees, sides trimmed.
        ((0.0208, 0.0, 0.9792, 1.0, 1.13), (6808, 4539), 146, "150mm"),
        # DSC02168: an axis-aligned crop of a quarter of the height.
        ((0.0, 0.076, 0.924, 1.0, 0.0), (6475, 4317), 127, "137mm"),
        # DSC02539: APS-C mode, so the camera already wrote 300mm for 200mm glass.
        ((0.0028, 0.0739, 0.9198, 1.0, 0.26), (4239, 2826), 300, "326mm"),
        # DSC02469: the 0.08-degree auto-straighten crop that barely trims.
        ((0.0006, 0.0021, 0.9994, 0.9979, -0.08), (6993, 4662), 105, "105mm"),
    ],
)
def test_read_applies_real_lightroom_crops(tmp_path, crop, size, camera, expected):
    photo = _photo(tmp_path, size, xmp=_xmp(**_crop(*crop)), equivalent=camera)
    assert _focal(photo) == expected


def test_settings_written_as_elements_read_the_same(tmp_path):
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(elements=True, **_dsc00091()))
    assert _focal(photo) == "226mm"


def test_the_namespace_matters_not_the_prefix(tmp_path):
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(prefix="cr", **_dsc00091()))
    assert _focal(photo) == "226mm"


def test_read_uses_the_already_open_image(tmp_path):
    # render() hands read() the image it opened; the crop must come from it.
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**_dsc00091()))
    with Image.open(photo) as image:
        image.load()
        assert metadata.read(photo, image=image).exposure.startswith("226mm")


# --- when the camera value stands -----------------------------------------------


def test_no_xmp_keeps_the_camera_value(tmp_path):
    assert _focal(_photo(tmp_path, DSC00091_SIZE)) == "200mm"


def test_has_crop_false_keeps_the_camera_value(tmp_path):
    settings = _dsc00091()
    settings["HasCrop"] = "False"
    assert _focal(_photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**settings))) == "200mm"


def test_only_the_equivalent_is_corrected(tmp_path):
    # Without an equivalent the card prints the physical length, which is a
    # property of the lens; a crop does not change it.
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**_dsc00091()), equivalent=None)
    assert _focal(photo) == "200mm"
    assert metadata.read(photo).warnings == []


@pytest.mark.parametrize(
    "warp",
    [
        {"PerspectiveUpright": 5},
        {"PerspectiveVertical": -12},
        {"PerspectiveHorizontal": 3},
        {"PerspectiveRotate": 0.4},
        {"PerspectiveAspect": 10},
        {"PerspectiveScale": 90},
        {"PerspectiveX": 2.5},
        {"PerspectiveY": -1},
        {"LensProfileDistortionScale": 60},
        {"LensManualDistortionAmount": 8},
    ],
)
def test_a_geometric_warp_keeps_the_camera_value_and_says_so(tmp_path, warp):
    # After a perspective or distortion warp the crop rectangle no longer sits
    # on the original frame, so its share of the diagonal is not the share of
    # the angle of view.
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**_dsc00091(**warp)))
    data = metadata.read(photo)
    assert data.exposure.startswith("200mm")
    assert any("crop" in w and "200mm" in w for w in data.warnings)


def test_default_warp_values_are_not_a_warp(tmp_path):
    # Exactly what Lightroom wrote on every sample, lens profile on.
    neutral = {
        "PerspectiveUpright": 0,
        "PerspectiveVertical": 0,
        "PerspectiveHorizontal": 0,
        "PerspectiveRotate": "0.0",
        "PerspectiveAspect": 0,
        "PerspectiveScale": 100,
        "PerspectiveX": "0.00",
        "PerspectiveY": "0.00",
        "LensProfileDistortionScale": 100,
        "LensProfileEnable": 1,
        "LensManualDistortionAmount": 0,
    }
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**_dsc00091(**neutral)))
    assert _focal(photo) == "226mm"


def test_upright_without_a_crop_says_nothing(tmp_path):
    # DSC00031: APS-C, Upright 5, no crop record. Nothing to correct, nothing to report.
    settings = {"HasCrop": "False", "PerspectiveUpright": 5}
    photo = _photo(tmp_path, (3072, 4608), xmp=_xmp(**settings), physical=82.0, equivalent=123)
    data = metadata.read(photo)
    assert data.exposure.startswith("123mm")
    assert data.warnings == []


@pytest.mark.parametrize(
    "crop",
    [
        (0.5, 0.1, 0.4, 0.9, 0.0),  # right before left
        (0.1, 0.6, 0.9, 0.5, 0.0),  # bottom before top
        (-0.2, 0.0, 0.9, 1.0, 0.0),  # outside the frame
        (0.1, 0.0, 1.3, 1.0, 0.0),
        (0.1, 0.1, 0.9, 0.9, 60.0),  # beyond Lightroom's +/-45 degrees
        (0.0, 0.0, 1.0, 0.001, 0.0),  # implies an absurd original aspect
    ],
)
def test_an_impossible_crop_counts_as_no_crop(tmp_path, crop):
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**_crop(*crop)))
    data = metadata.read(photo)
    assert data.exposure.startswith("200mm")
    assert data.warnings == []


def test_unreadable_crop_numbers_count_as_no_crop(tmp_path):
    settings = _dsc00091()
    settings["CropLeft"] = "left"
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=_xmp(**settings))
    assert _focal(photo) == "200mm"


def test_malformed_xmp_counts_as_no_crop(tmp_path):
    photo = _photo(tmp_path, DSC00091_SIZE, xmp=b"<x:xmpmeta><rdf:RDF crs:HasCrop=")
    assert _focal(photo) == "200mm"


# --- portrait ---------------------------------------------------------------------


def test_portrait_crop_keeping_the_frame_shape_is_applied(tmp_path):
    # Whether Lightroom states a portrait crop against the sensor or against
    # the turned frame is not settled by any sample. A crop that keeps the
    # frame's shape reads the same both ways, so it is safe to apply.
    photo = _photo(tmp_path, (4000, 6000), xmp=_xmp(**_crop(0.1, 0.1, 0.9, 0.9)), equivalent=100)
    assert _focal(photo) == "125mm"


def test_portrait_crop_the_two_readings_disagree_on_keeps_the_camera_value(tmp_path):
    photo = _photo(tmp_path, (4000, 4800), xmp=_xmp(**_crop(0.0, 0.0, 0.6667, 0.8)), equivalent=100)
    data = metadata.read(photo)
    assert data.exposure.startswith("100mm")
    assert any("portrait" in w for w in data.warnings)


def test_stored_landscape_pixels_turned_upright_are_portrait(tmp_path):
    # Orientation 6 stores a portrait photo as landscape pixels; the crop is
    # judged on the frame as shown, so the disagreeing crop is still refused.
    photo = _photo(
        tmp_path,
        (4800, 4000),
        xmp=_xmp(**_crop(0.0, 0.0, 0.6667, 0.8)),
        equivalent=100,
        orientation=6,
    )
    assert _focal(photo) == "100mm"


def test_expected_values_follow_from_the_formula():
    # Guards the hand-written expectations above against a typo.
    a = 1.5
    dx, dy = 0.9128 - 0.043, 0.9601 - 0.0448
    r = math.hypot(dx * a, dy) / math.hypot(a, 1)
    assert round(200 / r) == 226


@pytest.mark.parametrize("fmt", ["PNG", "HEIF"])
def test_other_input_formats_carry_the_crop_too(tmp_path, fmt):
    # exifcard reads JPEG, PNG and HEIC; Pillow files PNG's packet under its
    # iTXt keyword rather than under "xmp".
    path = tmp_path / f"DSC.{fmt.lower()}"
    exif = Image.Exif()
    exif[0x010F] = "SONY"
    exif[0x0110] = "ILCE-7M5"
    exif.get_ifd(0x8769).update({0x920A: 200.0, 0xA405: 200})
    kwargs = {"exif": exif}
    packet = _xmp(**_dsc00091())
    if fmt == "PNG":
        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_itxt("XML:com.adobe.xmp", packet.decode("utf-8"))
        kwargs["pnginfo"] = info
    else:
        import pillow_heif

        pillow_heif.register_heif_opener()
        kwargs["xmp"] = packet
    Image.new("RGB", DSC00091_SIZE).save(path, fmt, **kwargs)
    # As render() does: PNG's eXIf chunk is only read once the image is loaded.
    with Image.open(path) as image:
        image.load()
        assert metadata.read(path, image=image).exposure.startswith("226mm")
