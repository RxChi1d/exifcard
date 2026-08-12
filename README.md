# exifcard

A local CLI tool that turns a photo and its EXIF data into a finished card image: the photo on top, a quiet metadata strip below, written out as a single flat image file.

It is built for personal album archiving and the occasional share, not for social platforms. The output is an image, not a web page — no buttons, no device frames, no interactive elements.

## Demo

The same layout across five aspect ratios and both border modes. The photos are stand-ins and the signature is a sample, not a real one.

| `bleed` — for screens | `equal` — for print, with a faint inset hairline |
|---|---|
| ![bleed mode](docs/images/demo-bleed.png) | ![equal mode](docs/images/demo-equal.png) |

| 1:1 | 4:5 | 2:3 | 9:16 |
|---|---|---|---|
| ![1:1](docs/images/demo-square-1x1.png) | ![4:5](docs/images/demo-portrait-4x5.png) | ![2:3](docs/images/demo-portrait-2x3.png) | ![9:16](docs/images/demo-9x16.png) |

The layout is the same in every one — same proportions, same alignment, no separate treatment for portrait. Only the type size is compensated, so that a portrait card read at the same height as a landscape one has lettering of the same apparent size.

## Install

```sh
git clone https://github.com/RxChi1d/exifcard && cd exifcard
uv sync
uv run exifcard install-browser
```

`uv sync` installs the exact dependency versions in `uv.lock` — the ones this tool is tested against. That matters more here than it usually does: HEIC encoding, JPEG quantization table passthrough and the lossless composite all rest on behaviour its dependencies do not document, so a drifted version can break a format rather than merely change a number.

`install-browser` downloads the Chromium build that renders the info strip — see [How it works](#how-it-works).

Optionally install `jpegtran` (macOS `brew install jpeg-turbo`, Debian/Ubuntu `apt install libjpeg-turbo-progs`) if you want `--lossless`.

### As a global command

If you would rather have `exifcard` on your PATH everywhere:

```sh
uv tool install git+https://github.com/RxChi1d/exifcard
exifcard install-browser
```

The trade-off is that a tool install resolves dependencies afresh instead of reading `uv.lock`, so you get whatever satisfies the version ranges on the day you install rather than the combination the tests ran against.

## Use

From a clone, prefix the commands below with `uv run`, or add `--project /path/to/exifcard` to run them from wherever your photos are. A tool install skips the prefix.

```sh
uv run exifcard render photo.jpg                     # one photo
uv run exifcard render ./kyoto/ --location "Kyoto"   # a whole folder, one caption
uv run exifcard render ./kyoto/ --dry-run            # show what would be written
```

The source folder is never written to, so pointing the tool at a backup or a photo library leaves it untouched.

Cards land in `outputs/<source folder name>/`, mirroring the source layout. Two albums passed in one run stay apart, and `--recursive` keeps a nested folder nested rather than flattening subfolders from different albums into one directory.

Existing cards prompt before being replaced (`y`/`N`/`a`ll/`s`kip/`q`uit), or pass `--force` or `--skip-existing` to answer in advance. In a non-interactive shell an existing file is an error rather than a silent overwrite.

A file that cannot be read does not stop the run. The batch finishes, names what failed, and exits non-zero:

```
198 written, 0 skipped, 2 failed -> outputs/kyoto
failed:
  DSC00123.JPG  --lossless is not possible here: the photo is 3000x2002, not a multiple of 16
  DSC00456.JPG  cannot identify image file
```

### Per-photo captions

A coordinate has many true names at once — a road, a neighbourhood, a ward, a city — and none of them is reliably the one the photograph is about. `Fushimi Inari` is a choice about what the picture shows, so captions are written by hand. The tool only saves you from typing filenames:

```sh
uv run exifcard locations ./kyoto/     # append every photo to a locations.toml
```

```toml
# outputs/kyoto/locations.toml
# 2026.03.14 X-T5
"DSCF1234.JPG" = "Fushimi Inari, Kyoto"
# 2026.03.14 X-T5
"DSCF1240.JPG" = ""
```

Empty means no location, which is a designed state: the date line simply stands alone. Re-running only appends new files; your captions, comments and ordering are never touched.

### Configuration

```sh
uv run exifcard config-example > ~/.config/exifcard/config.toml
```

Holds the things that are stable across every album — the path to your signature, and the display-name tables:

```toml
signature = "~/Pictures/private/signature.png"

[gear.body]
"ILCE-7CM2" = "α7C II"

[gear.lens]
"TAMRON 25-200mm F2.8-5.6 A075 E" = "25-200mm F2.8-5.6 Di III RXD"
```

Gear names appear exactly as EXIF reports them unless a table renames them, so an unregistered camera still produces a correct card.

## What the card shows

Camera brand logo, body model, lens brand (only when it differs from the body's), lens model, focal length, aperture, shutter speed, ISO, date, an optional location, and an optional handwritten signature.

Anything EXIF does not supply is left out — a manual lens reports no aperture, so the readout simply has one fewer value. Nothing is ever replaced with `Unknown` or a dash, and the strip keeps its height either way.

Bundled marks cover cameras — Canon, Fujifilm, Hasselblad, Leica, LUMIX, Nikon, Olympus, OM System, Pentax, Ricoh, Sigma, Sony — and phones, since a phone is the camera that took the photo: Apple, ASUS, Google, HONOR, Huawei, Motorola, OnePlus, OPPO, Samsung, vivo, Xiaomi. Wordmarks where one exists in the public domain, the maker's square emblem where it does not.

Anything else falls back to the maker's name set in type, which the design specifies as a first-class state rather than a failure.

## Output

Format follows the input (`jpg`, `png`, `heic`) unless `--format` says otherwise, which keeps each file on the encoder that suits it.

Defaults are lossy, because a card is a derivative made for looking at while the original stays in your library. On a 33MP camera file, the default produces 6.8MB from an 18.8MB original, at a mean deviation of about 1 level in 255 — invisible at any viewing size.

What it does carry over is the camera's chroma sampling: a body that shot 4:2:2 keeps its colour resolution instead of being quietly halved to 4:2:0, for about 8% more file size.

`--quality` is passed straight to the encoder, so its scale differs per format and the numbers are not comparable — `heic 70` is roughly `jpg 95`.

`--lossless` composites at the DCT level with `jpegtran`, so the photo's coefficients are copied into the card untouched and the photo area is bit-for-bit identical to the source. It requires a JPEG whose dimensions are multiples of 16, and it fails with an explanation rather than quietly falling back.

Output is the photo's native resolution by default. Compression discards what you cannot see; resolution is visible and irreversible, so shrinking is left to an explicit `--width`.

## How it works

The photo and the info strip never overlap, so they are made separately and joined:

```
Chromium renders only the strip        Pillow assembles the card
┌──────────────────┐                   ┌──────────────────┐
│                  │                   │  photo bytes,    │
│   (no photo)     │                   │  untouched       │
├──────────────────┤                   ├──────────────────┤
│  7008 × 590      │  ───────────────> │  strip           │
└──────────────────┘                   └──────────────────┘
```

The browser is there for text: letter-spacing, baseline alignment and edge-to-edge distribution at exactly the values the design specifies, rather than reimplemented approximately in a drawing library. Because it only ever sees the strip, the photo is never re-sampled, never converted between colour spaces, and never limited by the browser's maximum surface size.

### Why portrait cards are not smaller

The strip is laid out on its own canvas of width `D` and then scaled to the card, rather than scaled from the card's width directly. Scaling from card width alone punishes portrait photos: their long edge is the height, so the card is narrower and the type shrinks with it — a 9:16 phone shot ended up with lettering half the size of a landscape frame's.

```
a = photo height / photo width
D = clamp(604 / a, 450, 760)      # narrower canvas → larger type
strip scale = card width / D
```

Landscape lands on 760 and is untouched, so its output is unchanged to the pixel.

A long body model next to a long lens name can overrun the row. Rather than wrap, truncate or abbreviate, the card gives ground in two steps: first it tightens — the exposure readout's tracking and the gap between the two column groups — which costs no type size at all; only if that is still not enough does the canvas widen, shrinking the block evenly. Both widths are measured in the browser from the real text, per photo, so nothing carries over from the previous card in a batch.

This is also why the display-name tables are not for shortening. They exist to turn an internal code into the product's actual name (`ILCE-7CM2` → `α7C II`); deciding which words of a name matter is not the tool's call.

Fonts (Archivo, JetBrains Mono, Noto Sans) ship with the package, so a card renders identically on any machine. Layout is defined once at a 760px baseline and scaled as a whole, so text never reflows between output sizes.

## License

MIT. Free to use, modify, and sell, including commercially; keep the copyright and license notice with any substantial portion you redistribute. See [LICENSE](LICENSE).

Bundled fonts are SIL Open Font License 1.1 (see `src/exifcard/assets/fonts/`). Bundled brand wordmarks are public domain (`PD-textlogo`) with their sources recorded in `src/exifcard/assets/logos/logos.toml`; they remain trademarks of their owners and are used here only to identify the camera a photo was taken with.
