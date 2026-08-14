**English** | [繁體中文](README.zh-TW.md)

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
```

`uv sync` installs the exact dependency versions in `uv.lock` — the ones this tool is tested against. That matters more here than it usually does: HEIC encoding, JPEG quantization table passthrough and the lossless composite all rest on behaviour its dependencies do not document, so a drifted version can break a format rather than merely change a number.

Optionally install `jpegtran` (macOS `brew install jpeg-turbo`, Debian/Ubuntu `apt install libjpeg-turbo-progs`) if you want `--lossless`.

### As a global command

If you would rather have `exifcard` on your PATH everywhere:

```sh
uv tool install git+https://github.com/RxChi1d/exifcard
```

The trade-off is that a tool install resolves dependencies afresh instead of reading `uv.lock`, so you get whatever satisfies the version ranges on the day you install rather than the combination the tests ran against.

## Use

From a clone, prefix the commands below with `uv run`, or add `--project /path/to/exifcard` to run them from wherever your photos are. A tool install skips the prefix.

```sh
uv run exifcard render photo.jpg                     # one photo
uv run exifcard render ./kyoto/ --location "Kyoto"   # a whole folder, one caption
uv run exifcard render ./kyoto/ --dry-run            # show what would be written
```

You will not have a signature file to hand on a first run, so one is included to try the feature with:

```sh
uv run exifcard render photo.jpg --signature examples/signature.png
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

A caption has a width budget, because the card's type size is settled by the photo's proportions and the gear names — a caption is never allowed to shrink the rest of the card to make room for itself. What is left for the date and location line:

| card | the whole line | after the `YYYY.MM.DD · ` prefix | Han characters |
|---|---|---|---|
| 3:2 landscape, with a signature | 592 | 510 | 58 |
| 3:2 landscape, no signature | 720 | 638 | 73 |
| 9:16 portrait, with a signature | 282 | 200 | 22 |

Design pixels, not output pixels — the numbers hold at any card size. It is a width rather than a character count, because Latin has no stable one: `Fushimi Inari, Kyoto` takes 208 of the tightest column's 282, leaving room for one more short word, where twenty `i`s would leave room for forty. Han does have one, in the last column, because every CJK face is drawn on an em square. Those counts are rounded down and one or two short of what will actually pass, on purpose: a number you can write to the end of without thinking is worth more than the last character. A caption that overruns fails that photo and says by how much, so the run tells you which line to shorten rather than printing it across the signature.

### Chinese, Japanese and Korean

Nothing CJK is bundled: those fonts run from 9 to 17MB, most users never need one, and which one is right depends on where you photograph. Register the fonts you want in the config instead — any file on your machine:

```toml
fonts = ["~/Library/Fonts/NotoSansTC-Regular.otf", "~/Library/Fonts/NotoSansJP-Regular.otf"]
```

They are tried in the order you list them, character by character, after the bundled faces — so the gear names and the readout keep the design's own typography, and only what those cannot draw falls through. exifcard never picks a font by language: `京都` is the same two code points in Chinese and Japanese, so which of the two forms is right is yours to decide by ordering the list. When one caption ends up drawn from more than one file, the run says which characters came from which, since letterforms then differ within a line.

Han is set at 88% of the date's size, which is where its ink and the digits' reach the same height. Without that a place name overpowers the date beside it — the wrong way round for the quietest line on the card.

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

**Focal length is the 35mm equivalent**, not the number on the lens barrel — so an X-E5 at 17mm prints `26mm`, and an iPhone prints `23mm` rather than `2mm`. Cameras that do not record an equivalent, mostly older DSLRs, fall back to the physical value; a photo carrying neither simply has no focal length on it. ([Why](docs/design.md#focal-length).)

Anything EXIF does not supply is left out — a manual lens reports no aperture, so the readout simply has one fewer value. Nothing is ever replaced with `Unknown` or a dash, and the strip keeps its height either way.

Bundled marks cover cameras — Canon, Fujifilm, Hasselblad, Leica, LUMIX, Nikon, Olympus, OM System, Pentax, Ricoh, Sigma, Sony — and phones, since a phone is the camera that took the photo: Apple, ASUS, Google, HONOR, Huawei, Motorola, OnePlus, OPPO, Samsung, vivo, Xiaomi. Wordmarks where one exists in the public domain, the maker's square emblem where it does not.

Anything else falls back to the maker's name set in type, which the design specifies as a first-class state rather than a failure.

## Output

Format follows the input (`jpg`, `png`, `heic`) unless `--format` says otherwise, which keeps each file on the encoder that suits it.

Defaults are lossy, because a card is a derivative made for looking at while the original stays in your library. On a 33MP camera file the default produces 6.8MB from an 18.8MB original, at a deviation invisible at any viewing size, and carries over the camera's chroma sampling so a body that shot 4:2:2 is not quietly halved to 4:2:0. ([The measurements](docs/design.md#encoding-defaults).)

`--quality` is passed straight to the encoder, so its scale differs per format and the numbers are not comparable — `heic 70` is roughly `jpg 95`.

`--lossless` composites at the DCT level with `jpegtran`, so the photo's coefficients are copied into the card untouched and the photo area is bit-for-bit identical to the source. It needs a JPEG whose dimensions are multiples of 16, and fails with an explanation rather than quietly falling back. ([Why an external binary](docs/design.md#lossless-compositing).)

Output is the photo's native resolution by default. Compression discards what you cannot see; resolution is visible and irreversible, so shrinking is left to an explicit `--width`.

## How it works

The photo and the info strip never overlap, so they are made separately and joined:

```
Typst renders only the strip           Pillow assembles the card
┌──────────────────┐                   ┌──────────────────┐
│                  │                   │  photo bytes,    │
│   (no photo)     │                   │  untouched       │
├──────────────────┤                   ├──────────────────┤
│  7008 × 590      │  ───────────────> │  strip           │
└──────────────────┘                   └──────────────────┘
```

The typesetter is there for text — tracking and the font's own kerning at exactly the design's values. Where each element sits is worked out first, in design units; the engine only sets the type and rasterizes it. Because it only ever sees the strip, the photo is never re-sampled or colour-converted. Type size is compensated for portrait proportions, so a tall card is not a card with small lettering.

Fonts and brand marks ship with the package and no system font is ever consulted, so a card renders identically on any machine and the tool works offline. The test suite holds that to the letter: its reference images are compared byte for byte on macOS, Linux and Windows.

**[Design notes](docs/design.md)** explains each of those choices, with the measurements behind them.

## Requirements and limits

Python 3.12 or newer. Linux, macOS and Windows all run in CI on every push.

Reads and writes JPEG, PNG and HEIC. RAW is out of scope — the card is made after a picture has been chosen and graded. Compositing is 8-bit, so a 10-bit HEIF is narrowed on the way in and says so.

## Development

```sh
uv sync
uv run pytest                  # full suite
uv run pytest -m "not golden"  # what CI runs; golden tests compare pixels and are local-only
uv build --wheel               # check the package still builds
```

## License

MIT. Free to use, modify, and sell, including commercially; keep the copyright and license notice with any substantial portion you redistribute. See [LICENSE](LICENSE).

Bundled fonts are SIL Open Font License 1.1 (see `src/exifcard/assets/fonts/`). Bundled brand wordmarks are public domain (`PD-textlogo`) with their sources recorded in `src/exifcard/assets/logos/logos.toml`; they remain trademarks of their owners and are used here only to identify the camera a photo was taken with.
