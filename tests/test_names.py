"""Display names for bodies and lenses."""

from __future__ import annotations

from exifcard import names


def test_unregistered_gear_is_shown_verbatim():
    # The tables are an override list, not an allow list: a camera nobody has
    # registered still produces a correct card.
    assert names.display_name("X-H2S", names.BODY_NAMES) == "X-H2S"
    assert names.display_name("", names.BODY_NAMES) == ""


def test_registered_gear_uses_the_short_name():
    assert names.display_name("ILCE-7CM2", names.BODY_NAMES) == "α7C II"


def test_third_party_lens_brand_is_shown():
    brand, model = names.resolve_lens(
        "TAMRON 25-200mm F2.8-5.6 A075 E", "SONY", names.LENS_NAMES
    )
    assert brand == "TAMRON"
    assert model == "25-200mm F2.8-5.6 Di III RXD"


def test_own_brand_lens_is_not_labelled():
    # Printing "Canon" next to a Canon body's own logo is noise.
    brand, model = names.resolve_lens("EF-S18-55mm f/3.5-5.6 IS STM", "Canon", {})
    assert brand == ""
    assert model == "EF-S18-55mm f/3.5-5.6 IS STM"


def test_declared_brand_covers_lenses_that_omit_their_maker():
    # Tamron's Fuji-mount lenses report no maker at all in LensModel.
    brand, model = names.resolve_lens(
        "17-70mm F/2.8 DiIII-A VC RXD B070X", "FUJIFILM", names.LENS_NAMES
    )
    assert brand == "TAMRON"
    assert model == "17-70mm F2.8 Di III-A VC RXD"


def test_brand_prefix_is_peeled_when_there_is_no_table_entry():
    brand, model = names.resolve_lens("SIGMA 56mm F1.4 DC DN", "FUJIFILM", {})
    assert brand == "SIGMA"
    assert model == "56mm F1.4 DC DN"


def test_missing_lens_yields_nothing_rather_than_a_placeholder():
    assert names.resolve_lens(None, "NIKON", {}) == ("", "")
    assert names.resolve_lens("", "NIKON", {}) == ("", "")


def test_brand_label_prefers_the_name_on_the_camera():
    assert names.brand_label("NIKON", "NIKON CORPORATION") == "Nikon"
    assert names.brand_label("OM DIGITAL SOLUTIONS", "OM Digital Solutions") == "OM SYSTEM"
    # Anything unlisted keeps whatever the camera wrote.
    assert names.brand_label("HASSELBLAD", "Hasselblad") == "Hasselblad"
    assert names.brand_label("", "") == ""


def test_body_name_is_not_repeated_in_the_lens_name():
    # Phones write the whole device into LensModel; the card has already
    # printed the body one line above.
    brand, model = names.resolve_lens(
        "iPhone 16 Pro back triple camera 6.765mm f/1.78",
        "Apple",
        {},
        body_model="iPhone 16 Pro",
    )
    assert brand == ""
    assert model == "back triple camera 6.765mm f/1.78"


def test_body_prefix_stripping_leaves_unrelated_names_alone():
    assert names.strip_body_prefix("XF 33mm F1.4 R LM WR", "X-T5") == "XF 33mm F1.4 R LM WR"
    assert names.strip_body_prefix("X-T5", "X-T5") == "X-T5"
    assert names.strip_body_prefix("56mm F1.4", "") == "56mm F1.4"


def test_a_phone_lens_reads_as_which_one_and_what_it_is():
    """The module description EXIF carries says neither.

    "back triple camera 6.765mm f/1.78" is a physical focal length nobody
    recognises next to an aperture the exposure line already prints, and the
    row exists to say which lens took the picture.
    """
    brand, lens = names.resolve_lens(
        "iPhone 16 Pro back triple camera 6.765mm f/1.78",
        "Apple",
        names.LENS_NAMES,
        body_model="iPhone 16 Pro",
    )
    assert (brand, lens) == ("", "Main 24mm F1.78")


def test_a_phone_lens_with_no_entry_still_prints_something_sensible():
    """An unregistered one falls back to the raw string, minus the body name.

    The tables are an override list, so a phone nobody has registered yet has
    to keep working -- and the body model is already on the line above.
    """
    brand, lens = names.resolve_lens(
        "iPhone 17 Pro back triple camera 4.2mm f/2.0",
        "Apple",
        names.LENS_NAMES,
        body_model="iPhone 17 Pro",
    )
    assert (brand, lens) == ("", "back triple camera 4.2mm f/2.0")
