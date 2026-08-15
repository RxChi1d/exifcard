---
name: exifcard
description: Use the exifcard CLI to turn local photos into flat EXIF metadata cards with the photo above a strip showing camera, lens, exposure, date, an optional location caption and signature. Trigger when the user wants metadata or info cards for one photo or an album, camera details rendered beneath photos, or per-photo location captions, even when they do not name exifcard; also trigger for exifcard installation, configuration or troubleshooting. Do not use for general photo editing, EXIF inspection or removal alone, or arbitrary graphic layouts.
license: MIT
---

# exifcard

`exifcard` is a local command-line tool. It reads a photo's EXIF and writes one flat image: the photo on top, a metadata strip below with camera, lens, exposure, date, an optional location caption, and a signature. It is built for personal album archiving.

It works only on local files. It uploads nothing, and it never writes to the source folder.

## Check it is installed

```sh
command -v exifcard
```

If the command is missing, install it with [uv](https://docs.astral.sh/uv/) (Python 3.12 or newer):

```sh
uv tool install git+https://github.com/RxChi1d/exifcard
```

Ask the user before you install anything. `--lossless` also needs `jpegtran`: `brew install jpeg-turbo` on macOS, or `apt install libjpeg-turbo-progs` on Debian and Ubuntu. No other feature needs it.

Inside a clone of the repository, run `uv run exifcard ...` instead.

## Commands

```sh
exifcard render <paths>...   # photos or directories -> cards
exifcard locations <dir>     # scaffold a locations.toml for per-photo captions
exifcard config-example      # print a starter config to redirect into a file
```

Run `exifcard <subcommand> --help` after you choose a subcommand. The installed help is the authority on flags, defaults, and units. Do not guess flags from this file.

## Render workflow

```sh
exifcard render ./kyoto/ --dry-run          # show what would be written
exifcard render ./kyoto/ --location "Kyoto" # one caption for the whole batch
```

exifcard writes cards to `outputs/<source folder name>/` and mirrors the source layout. Without `--out`, that output root is relative to the current working directory, not to the photos.

`--dry-run` previews four things: routing, destinations, which files already exist, and the caption each photo would get. It opens no photo and renders nothing. It cannot detect an unreadable image, a missing glyph, a caption overrun, or a file that `--lossless` cannot process.

To give each photo its own caption, scaffold the file, ask the user to fill it in, then render:

```sh
exifcard locations ./kyoto/                             # writes outputs/kyoto/locations.toml
exifcard render ./kyoto/ --locations outputs/kyoto/locations.toml
```

Re-running `locations` appends only new files. It does not change existing captions, comments, or ordering.

## Warnings

Capture stdout, stderr, and the exit status. An exit status of zero can still carry per-file warnings, printed after the card was written. Read those warnings and report them. Do not report a clean success.

`no available font can draw ...` means those characters printed as empty boxes. exifcard bundles no CJK font and never uses a system font, so this does not fix itself. Offer to register a font, then render again. The config key is `fonts`, and its value is a top-level array of font file paths that the user chose. Do not guess a path. exifcard tries the files in order, character by character, after the bundled fonts. The order decides which regional form a shared code point takes, so let the user choose it.

## Rules

- **Never invent a location caption.** One coordinate has several true names: a road, a ward, a city. Which one the photograph is about is the user's decision. Leave the entry empty or ask. An empty caption is supported, and the date line then stands alone. This holds even when the EXIF carries GPS.
- **A caption has a width budget.** An overrun fails that photo and reports the measured geometry, not a character count. Do not shorten or rewrite the user's words. Report the overrun and ask for a shorter caption.
- **The card keeps the source EXIF by default.** `--exif all` is the default, and it includes GPS and serial numbers. When the cards are for sharing or upload, ask the user whether to use `--exif safe`, which drops GPS and serial numbers, or `--exif none`, which writes no metadata. Never change this silently.
- **An existing card is an error in a non-interactive shell.** exifcard does not overwrite it silently. Choose `--force` or `--skip-existing` before you run unattended.
- **`--lossless` raises an error instead of falling back.** It needs `jpegtran` and a JPEG whose dimensions are multiples of 16. Report the error. Do not re-encode to work around it.
- **A failed photo does not stop the batch.** The run finishes, lists what failed, and exits non-zero. Read that list before you report success.
- **Missing EXIF fields are omitted on purpose.** Do not report an omission as a render failure, and do not infer a replacement value.
- **Photos are personal and carry GPS.** Do not copy a photo, its path, or its metadata off the user's machine.
- **RAW is out of scope.** exifcard reads and writes JPEG, PNG, and HEIC.

## Configuration

The config file is optional. It holds what stays the same across albums: a signature image, camera and lens display names, and extra fonts.

```sh
exifcard config-example > ~/.config/exifcard/config.toml
```

That redirect truncates the target. Generate the file only when it does not exist. Otherwise edit the existing file and keep every entry in it.

`[gear.body]` and `[gear.lens]` map a raw EXIF string to the product's real name, such as `ILCE-7CM2` to `α7C II`. Use them when the user asks how a name reads or asks to rename one. They are an override list, not an allow list, so an unregistered camera still renders correctly. Never use them to shorten a name, and never flag an unmapped name on your own. A raw EXIF name is valid output.

## More information

- Flags: `exifcard <subcommand> --help`
- What the tool does: https://github.com/RxChi1d/exifcard
- Why a behaviour is the way it is: https://github.com/RxChi1d/exifcard/blob/main/docs/design.md
