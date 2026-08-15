# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `exifcard render` turns a photo and its EXIF into a card: the photo at its native resolution on top, a metadata strip below, written as one flat image. Typst sets only the strip and Pillow joins the two, so the photo is never re-sampled or colour-converted.
- The card shows the camera brand mark, body model, lens brand (only when it differs from the body's), lens model, focal length, aperture, shutter speed, ISO, date, an optional location and an optional signature. Values EXIF does not supply are left out rather than replaced, and the strip keeps its height either way.
- Focal length is printed as the 35mm equivalent where the camera records one, falling back to the physical value.
- Bundled brand marks for twelve camera makers and eleven phone makers. Anything else falls back to the maker's name set in type.
- Long gear names are never wrapped, truncated or abbreviated: the fit solver tightens the type first, then widens the canvas.
- Type size is compensated for portrait proportions. The layout is otherwise identical at every aspect ratio, and no photo is cropped.
- Batch rendering over folders, with `--recursive`, output grouped by source album, and a run that continues past a file it cannot read, then exits non-zero naming what failed.
- An overwrite prompt (`y`/`N`/`a`ll/`s`kip/`q`uit), with `--force` and `--skip-existing` to answer in advance. In a non-interactive shell an existing file is an error rather than a silent overwrite.
- `exifcard locations` writes a `locations.toml` listing every photo in a folder, for captions written by hand. Re-running only appends new files.
- A caption is held to a width budget so that one line of prose can never shrink the rest of the card, and a caption that overruns fails that photo with the geometry.
- Chinese, Japanese and Korean captions are set at 88% of the date's size, from fonts registered in the config. Fonts fall back character by character in the order listed, never by detected language, and a line drawn from more than one file is reported.
- `exifcard config-example` writes a config holding the signature path and the gear display-name tables. Unregistered gear still prints correctly, straight from EXIF.
- JPEG, PNG and HEIC read and written, with `--format`, `--quality` and `--width`. Lossy defaults carry over the camera's chroma sampling.
- `--lossless` composites at the DCT level with `jpegtran`, leaving the photo area bit-for-bit identical to the source. It requires a JPEG whose dimensions are multiples of 16 and raises rather than falling back.
- Warnings when a source carries more than 8 bits per channel, and when a character has no glyph in any bundled font.
- Fonts and brand marks ship with the package and no system font is consulted, so a card renders identically on macOS, Linux and Windows. All three run in CI.

[Unreleased]: https://github.com/RxChi1d/exifcard/commits/main
