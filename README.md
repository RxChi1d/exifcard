**English** | [繁體中文](README.zh-TW.md)

# exifcard

exifcard is a local CLI tool. It turns a photo and its EXIF data into a finished card image: the photo on top, a quiet metadata strip below, written out as a single flat image file.

It is built for personal album archiving and the occasional share, not for social platforms. The output is an image, not a web page. It has no buttons, no device frames, and no interactive elements.

## Demo

These are the same layout across five aspect ratios and both border modes. The photos are stand-ins, and the signature is a sample rather than a real one.

| `bleed`: for screens | `equal`: for print, with a faint inset hairline |
|---|---|
| ![bleed mode](docs/images/demo-bleed.png) | ![equal mode](docs/images/demo-equal.png) |

| 1:1 | 4:5 | 2:3 | 9:16 |
|---|---|---|---|
| ![1:1](docs/images/demo-square-1x1.png) | ![4:5](docs/images/demo-portrait-4x5.png) | ![2:3](docs/images/demo-portrait-2x3.png) | ![9:16](docs/images/demo-9x16.png) |

Every card uses the same proportions and the same alignment. Portrait gets no separate treatment. Only the type size is compensated, so a portrait card read at the same height as a landscape one has lettering of the same apparent size.

## Install

```sh
git clone https://github.com/RxChi1d/exifcard && cd exifcard
uv sync
```

`uv sync` installs the exact dependency versions in `uv.lock`, which are the versions this tool is tested against. That matters more here than it usually does. HEIC encoding, JPEG quantization table passthrough, and the lossless composite all rest on behaviour that the dependencies do not document, so a drifted version can break a format rather than merely change a number.

To use `--lossless`, also install `jpegtran`: `brew install jpeg-turbo` on macOS, or `apt install libjpeg-turbo-progs` on Debian and Ubuntu.

### As a global command

To put `exifcard` on your PATH everywhere:

```sh
uv tool install git+https://github.com/RxChi1d/exifcard
```

The trade-off is that a tool install resolves dependencies afresh instead of reading `uv.lock`. You get whatever satisfies the version ranges on the day you install, not the combination the tests ran against.

### Agent skill

If you work through a coding agent, this repository also ships an [Agent Skill](https://agentskills.io):

```sh
npx skills add RxChi1d/exifcard
```

The installer asks which agent to install into. It installs into the current project; `--global` installs it for your user account instead, so it is there whichever folder your photos are in. Which of the two you want is your call.

The skill tells the agent what the tool is for, which command does what, and the few rules that matter before it runs anything: it never invents a location caption for you, `--lossless` fails instead of quietly degrading, and an existing card is an error in a non-interactive shell. The skill is short on purpose, because `--help` remains the authority on flags.

For an agent the installer does not cover, ask the agent itself:

```
Install the Agent Skill at https://github.com/RxChi1d/exifcard/tree/main/skills/exifcard
into the skills directory you read. Ask me first whether to install it for this
project or for my user account.
```

## Use

From a clone, prefix the commands below with `uv run`. To run them from wherever your photos are, add `--project /path/to/exifcard`. A tool install needs no prefix.

```sh
uv run exifcard render photo.jpg                     # one photo
uv run exifcard render ./kyoto/ --location "Kyoto"   # a whole folder, one caption
uv run exifcard render ./kyoto/ --dry-run            # show what would be written
```

You will not have a signature file on a first run, so the repository includes one to try the feature with:

```sh
uv run exifcard render photo.jpg --signature examples/signature.png
```

exifcard never writes to the source folder, so you can point it at a backup or a photo library and leave it untouched.

Cards go to `outputs/<source folder name>/` and mirror the source layout. Two albums passed in one run stay apart. `--recursive` keeps a nested folder nested instead of flattening subfolders from different albums into one directory.

Existing cards prompt before they are replaced (`y`/`N`/`a`ll/`s`kip/`q`uit). Pass `--force` or `--skip-existing` to answer in advance. In a non-interactive shell, an existing file is an error rather than a silent overwrite.

A file that cannot be read does not stop the run. The batch finishes, names what failed, and exits non-zero:

```
198 written, 0 skipped, 2 failed -> outputs/kyoto
failed:
  DSC00123.JPG  --lossless is not possible here: the photo is 3000x2002, not a multiple of 16
  DSC00456.JPG  cannot identify image file
```

### Per-photo captions

One coordinate has many true names at once: a road, a neighbourhood, a ward, a city. None of them is reliably the one the photograph is about. `Fushimi Inari` is a choice about what the picture shows, so you write captions by hand. The tool only saves you from typing filenames:

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

An empty value means no location. That is a designed state: the date line simply stands alone. Re-running appends only new files, and never touches your captions, comments, or ordering.

A caption has a width budget. The card's type size is settled by the photo's proportions and the gear names, and a caption is never allowed to shrink the rest of the card to make room for itself. This is what is left for the date and location line:

| card | the whole line | after the `YYYY.MM.DD · ` prefix | Han characters |
|---|---|---|---|
| 3:2 landscape, with a signature | 592 | 510 | 58 |
| 3:2 landscape, no signature | 720 | 638 | 73 |
| 9:16 portrait, with a signature | 282 | 200 | 22 |

Those are design pixels, not output pixels, so the numbers hold at any card size. The budget is a width rather than a character count, because Latin has no stable count: `Fushimi Inari, Kyoto` takes 208 of the tightest column's 282 and leaves room for one more short word, where twenty `i`s would leave room for forty. Han does have a stable count, shown in the last column, because every CJK face is drawn on an em square. Those counts are rounded down, one or two short of what will actually pass, on purpose. A number you can write to the end of without thinking is worth more than the last character. A caption that overruns fails that photo and reports by how much, so the run tells you which line to shorten instead of printing it across the signature.

### Chinese, Japanese and Korean

exifcard bundles no CJK font. Those fonts run from 9 to 17MB, most users never need one, and which one is right depends on where you photograph. Register the fonts you want in the config instead. Any file on your machine works:

```toml
fonts = ["~/Library/Fonts/NotoSansTC-Regular.otf", "~/Library/Fonts/NotoSansJP-Regular.otf"]
```

exifcard tries them in the order you list them, character by character, after the bundled faces. The gear names and the readout therefore keep the design's own typography, and only what those cannot draw falls through. exifcard never picks a font by language: `京都` is the same two code points in Chinese and Japanese, so you decide which of the two forms is right by ordering the list. When one caption ends up drawn from more than one file, the run reports which characters came from which, because letterforms then differ within a line.

Han is set at 88% of the date's size, which is where its ink and the digits' ink reach the same height. Without that compensation, a place name overpowers the date beside it, which is the wrong way round for the quietest line on the card.

### Configuration

```sh
uv run exifcard config-example > ~/.config/exifcard/config.toml
```

The config file holds what stays the same across every album: the path to your signature, and the display-name tables.

```toml
signature = "~/Pictures/private/signature.png"

[gear.body]
"ILCE-7CM2" = "α7C II"

[gear.lens]
"TAMRON 25-200mm F2.8-5.6 A075 E" = "25-200mm F2.8-5.6 Di III RXD"
```

Gear names appear exactly as EXIF reports them unless a table renames them, so an unregistered camera still produces a correct card.

## What the card shows

The card shows the camera brand logo, body model, lens brand (only when it differs from the body's), lens model, focal length, aperture, shutter speed, ISO, date, an optional location, and an optional handwritten signature.

**Focal length is the 35mm equivalent**, not the number on the lens barrel. An X-E5 at 17mm prints `26mm`, and an iPhone prints `23mm` rather than `2mm`. Cameras that do not record an equivalent, mostly older DSLRs, fall back to the physical value. A photo that carries neither simply has no focal length on it. ([Why](docs/design.md#focal-length).)

Anything EXIF does not supply is left out. A manual lens reports no aperture, so the readout has one fewer value. Nothing is ever replaced with `Unknown` or a dash, and the strip keeps its height either way.

Bundled marks cover cameras: Canon, Fujifilm, Hasselblad, Leica, LUMIX, Nikon, Olympus, OM System, Pentax, Ricoh, Sigma, Sony. They also cover phones, since a phone is the camera that took the photo: Apple, ASUS, Google, HONOR, Huawei, Motorola, OnePlus, OPPO, Samsung, vivo, Xiaomi. Each mark is a wordmark where one exists in the public domain, and the maker's square emblem where one does not.

Any other maker falls back to its name set in type. The design specifies that as a first-class state rather than a failure.

## Output

The format follows the input (`jpg`, `png`, `heic`) unless `--format` says otherwise, which keeps each file on the encoder that suits it.

Defaults are lossy, because a card is a derivative made for looking at while the original stays in your library. On a 33MP camera file, the default produces 6.8MB from an 18.8MB original, at a deviation invisible at any viewing size. It also carries over the camera's chroma sampling, so a body that shot 4:2:2 is not quietly halved to 4:2:0. ([The measurements](docs/design.md#encoding-defaults).)

`--quality` is passed straight to the encoder, so its scale differs per format and the numbers are not comparable. `heic 70` is roughly `jpg 95`.

`--lossless` composites at the DCT level with `jpegtran`. The photo's coefficients are copied into the card untouched, so the photo area is bit-for-bit identical to the source. It needs a JPEG whose dimensions are multiples of 16, and it fails with an explanation rather than quietly falling back. ([Why an external binary](docs/design.md#lossless-compositing).)

Output is the photo's native resolution by default. Compression discards what you cannot see, but resolution is visible and irreversible, so shrinking is left to an explicit `--width`.

## How it works

The photo and the info strip never overlap, so exifcard makes them separately and joins them:

```
Typst renders only the strip           Pillow assembles the card
┌──────────────────┐                   ┌──────────────────┐
│                  │                   │  photo bytes,    │
│   (no photo)     │                   │  untouched       │
├──────────────────┤                   ├──────────────────┤
│  7008 × 590      │  ───────────────> │  strip           │
└──────────────────┘                   └──────────────────┘
```

The typesetter is there for text, with tracking and the font's own kerning at exactly the design's values. exifcard works out where each element sits first, in design units, and the engine only sets the type and rasterizes it. Because the engine only ever sees the strip, the photo is never re-sampled or colour-converted. Type size is compensated for portrait proportions, so a tall card is not a card with small lettering.

Fonts and brand marks ship with the package, and no system font is ever consulted. A card therefore renders identically on any machine, and the tool works offline. The test suite holds that to the letter: it compares its reference images byte for byte on macOS, Linux, and Windows.

**[Design notes](docs/design.md)** explains each of those choices, with the measurements behind them.

## Requirements and limits

exifcard needs Python 3.12 or newer. Linux, macOS, and Windows all run in CI on every push.

It reads and writes JPEG, PNG, and HEIC. RAW is out of scope, because the card is made after a picture has been chosen and graded. Compositing is 8-bit, so a 10-bit HEIF is narrowed on the way in, and the run says so.

## Development

```sh
uv sync
uv run pytest                  # full suite
uv run pytest -m "not golden"  # what CI runs; golden tests compare pixels and are local-only
uv build --wheel               # check the package still builds
```

## License

MIT. You may use, modify, and sell it, including commercially. Keep the copyright and license notice with any substantial portion you redistribute. See [LICENSE](LICENSE).

Bundled fonts are SIL Open Font License 1.1 (see `src/exifcard/assets/fonts/`). Bundled brand wordmarks are public domain (`PD-textlogo`), and their sources are recorded in `src/exifcard/assets/logos/logos.toml`. They remain trademarks of their owners, and are used here only to identify the camera a photo was taken with.
