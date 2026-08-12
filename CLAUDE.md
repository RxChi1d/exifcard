# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`exifcard` is a **local CLI tool** that turns a photo plus its EXIF data into a finished card image: the photo on top, a metadata strip below, written out as one flat image file for personal album archiving (Immich) and occasional sharing.

Scope boundary: a command-line tool, run locally, over local files. **Not** an API server, not a web service, not a GUI. Do not add HTTP endpoints, a daemon, or a browser UI. Chromium is present strictly as an internal text renderer.

## Commands

```sh
uv sync                                  # install, including dev group
uv run playwright install chromium       # once, before anything renders
uv run pytest                            # full suite, ~4s
uv run pytest tests/test_names.py -k brand   # one file / one test
uv run exifcard render <path> --dry-run  # see what a run would write
```

Tests that need a browser call `pytest.importorskip("playwright.sync_api")`, so the pure-logic tests still run without it.

## Architecture

The photo and the info strip never overlap, which is the hinge the whole design turns on: they are produced by different engines and joined at the end.

```
metadata.py  EXIF -> display strings        names.py   gear display-name tables
     |                                      logos.py   Make/Model -> bundled wordmark
     v
strip.py     Chromium renders ONLY the strip, at the card's real pixel width
     |
     v
compose.py   photo pasted at native size + strip below   (numpy/Pillow)
     |
     v
encode.py    per-format encoders, including the jpegtran lossless path
```

`render.py` sequences those for one photo; `cli.py` handles batching, prompts and progress. `layout.py` holds every design constant at the 760px baseline.

Two consequences worth keeping in mind before changing anything here:

- **The photo never enters the browser.** That is what keeps its pixels, ICC profile and bit depth intact, and what keeps a 40MP card from hitting Chromium's surface limits. Rendering the whole card in the browser would be simpler and would silently degrade every photo.
- **Scaling happens through `device_scale_factor`, not by pre-multiplying lengths.** Every value in `layout.py` and in the generated HTML stays at its baseline number.

## Design rules

These are settled decisions, not defaults. Changing one is a design change.

- The photo is the subject: largest type in the strip is 13.5px at the 760px baseline. Nothing is promoted to a heading.
- Gear before exposure. Row 1: logo + body model left, exposure readout right. Row 2: lens details and date/location left, signature right.
- No dividers except the single 1px rule between logo and body model. Grouping comes from columns and line spacing alone.
- Only the camera body gets a graphic logo; lenses are always text. Lens brand appears only when it differs from the body's.
- **The strip height is fixed** — independent of the photo's aspect ratio *and* of how much metadata a photo carries. `layout.ROW1_HEIGHT`, `ROW2_HEIGHT` and `LINE_HEIGHT` exist for this reason: leaving line boxes to font metrics made the strip a fraction of a pixel taller when a lens name was present, and an album stopped stacking evenly.
- No border-radius, no shadows, no gradients, no accent colors.
- **Missing values are omitted, never replaced.** No `Unknown`, no dash, no `N/A`. The layout does not collapse to fill the gap.
- Any aspect ratio is accepted and the photo is never cropped. The four ratios in the demo images are validated examples, not a supported list.

## Data handling

- **EXIF strings are NUL-padded by cameras.** `metadata.clean()` strips them; `.strip()` alone does not, and every table lookup silently misses. Fujifilm pads `LensModel` with 29 NUL bytes.
- Gear tables are an override list, never an allow list: unregistered gear is displayed exactly as EXIF wrote it.
- `Make` is normalized by stripping legal-entity noise (`NIKON CORPORATION` → `NIKON`). Ricoh ships both RICOH- and PENTAX-branded bodies under one `Make`, so `logos.toml` also matches on a `Model` prefix.
- Pillow reports Sony JPEGs as `MPO` because of the multi-picture block. Anything checking for JPEG must accept both.
- Output EXIF is copied wholesale by default, **except `Orientation`, which is forced to 1** — rotation is baked into the pixels, and leaving the flag would make viewers rotate the finished card.

## Output policy

- Format follows the input unless `--format` overrides it.
- JPEG re-encodes with the **source's own quantization tables and chroma subsampling**, not a quality number. Measured on a 33MP file: `quality=95` gives 6.06MB from an 18.76MB source (mean deviation 1.08); source tables give 18.94MB (mean deviation 0.23).
- HEIC needs `GRID_TILE_SIZE` set or libheif produces an undecodable file above roughly 28MP. Tiling costs about 1% in size.
- `--lossless` uses `jpegtran -drop` and requires photo dimensions that are multiples of 16. It raises rather than falling back: a promise that silently degrades is worse than an error.
- Default output width is the photo's native resolution. Compression is invisible, resolution loss is not.

## Assets

Everything the program reads at runtime lives in `src/exifcard/assets/` so it ships in the wheel. Anything only humans look at lives in `docs/`.

- `assets/fonts/` — Archivo, JetBrains Mono, Noto Sans, with their OFL texts. **Archivo has no Greek alpha**, and Sony bodies display as `α7C II`; Noto Sans is bundled as the fallback that covers it.
- `assets/logos/` — public-domain brand marks with provenance in `logos.toml`, covering camera and phone makers alike: a phone is the camera that took the photo. Mostly wordmarks; Nikon, Leica, OM System, Apple, Xiaomi and OnePlus have none in the public domain and use the maker's square emblem, which aligned by height comes out roughly a sixth as wide. A mark is only bundled if it survives 11px on warm paper — Nothing's white-on-black lettering does not, so it uses the text fallback.

`test-photos/` holds real camera files and is gitignored — they carry GPS and are not ours to publish.

## Conventions

Write code comments and config-file comments in English.

Git is on branch `feat/initial-implementation`; `main` holds only the initial docs commit.
