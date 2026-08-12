# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

It records what the code cannot tell you: decisions, their constraints, and the traps whose cost is paid before you would think to look. How to install and use the tool is in `README.md`; why each decision was reached, with the measurements, is in `docs/design.md`.

## Project

`exifcard` turns a photo and its EXIF data into a finished card image: the photo on top, a metadata strip below — camera, lens, exposure, date, an optional location and signature — written out as one flat image file for personal album archiving and occasional sharing.

## Scope

A command-line tool, run locally, over local files. **Not** an API server, not a web service, not a GUI. Do not add HTTP endpoints, a daemon, or a browser UI. Chromium is present strictly as an internal text renderer.

## Commands

```sh
uv run exifcard install-browser   # once; nothing renders without it
uv run pytest                     # full suite
uv run pytest -m "not golden"     # what CI runs
```

`golden` tests compare rendered pixels and are local-only: text rasterizes differently on Linux. Anything that guards behaviour must therefore live outside that marker.

## Architecture

The photo and the info strip never overlap. That is the hinge the whole implementation turns on: they are produced by different engines and joined at the end.

```
metadata.py  EXIF -> display strings        names.py   gear display-name tables
     |                                      logos.py   Make/Model -> bundled mark
     v
strip.py     Chromium renders ONLY the strip, on its own design canvas
     |
     v
compose.py   photo pasted at native size + strip below   (numpy/Pillow)
     |
     v
encode.py    per-format encoders, including the jpegtran lossless path
```

`render.py` sequences those for one photo; `cli.py` handles batching, prompts and progress. `layout.py` holds every design constant at the 760px baseline.

- **The photo never enters the browser**, which is what keeps its pixels, ICC profile and bit depth intact and a 40MP card within Chromium's surface limits.
- **The browser is not replaceable by Pillow.** Pillow has no letter-spacing API and its default layout ignores the font's kerning; the design depends on both. Measurements in `docs/design.md`.
- **Scaling happens through `device_scale_factor`**, never by pre-multiplying lengths. Every value in `layout.py` and in the generated HTML stays at its baseline number.

## Design rules

Settled decisions from a specification that is not in this repository, so they cannot be recovered by reading the code. Changing one is a design change.

- The photo is the subject. Nothing in the strip is promoted to a heading, and grouping comes from columns and line spacing — no dividers beyond the single rule beside the logo, no border-radius, shadows, gradients or accent colours.
- Gear before exposure: the body and lens belong together and precede the readings.
- Only the camera body gets a graphic mark; lenses are always text, and the lens brand appears only when it differs from the body's.
- **Strip height is fixed in design units**, independent of how much metadata a photo carries — an album has to stack evenly. This is why `ROW1_HEIGHT`, `ROW2_HEIGHT` and `LINE_HEIGHT` are stated outright instead of left to font metrics.
- **Type size is compensated for portrait; layout is not.** Crowding comes from a card being narrow, not from its orientation, so there is no separate portrait layout. Landscape must stay pixel-identical — `tests/test_canvas.py` asserts it.
- **Long names never wrap, truncate or abbreviate.** `strip.fit` tightens first, then widens the canvas. It must stay bidirectional: a one-way ratchet would leave a card shrunken because the previous photo in the batch had a long lens name.
- **Missing values are omitted, never replaced.** No `Unknown`, no dash, no `N/A`, and the layout does not collapse to fill the gap.
- Gear tables map an internal code onto the product's real name. They are an override list, never an allow list, and **never a place to shorten anything** — length is `strip.fit`'s problem.
- Any aspect ratio is accepted and the photo is never cropped.

## Traps

Each of these is silent, or costs more than the fix. The code says so where it happens; this is the list of places to be careful before you get there.

- **Do not encode output with the source's quantization tables.** They belong solely to `--lossless`, where jpegtran needs the canvas quantized to match. Used as a default they make a card larger than the photo it came from, and every visual check still passes.
- **Do not add a `force-include` for the assets.** They already sit inside the package; declaring them twice makes the wheel fail to build, which nothing but an install attempt reveals.
- **`--lossless` must raise, never fall back.** A promise that silently degrades is worse than an error.
- **Bundled marks must survive 11px on warm paper**, which is the size they are actually used at. `logos.toml` records why each one is present or absent.
- `test-photos/` holds real camera files and is gitignored: they carry GPS and are not ours to publish.

## Conventions

Write code comments and config-file comments in English.

Work happens on branches: `main` requires a pull request and a passing `test` check.
