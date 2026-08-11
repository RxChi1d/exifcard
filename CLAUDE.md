# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`exifcard` builds a **local CLI tool** that turns a photo plus its EXIF data into a finished card image: the photo on top, a metadata strip below, written out as a single flat image file for personal album archiving (Immich) and occasional sharing.

Scope boundary: a command-line tool, run locally, over local files. **Not** an API server, not a web service, not a GUI. Do not add HTTP endpoints, a daemon, or a browser UI. A headless browser is acceptable only as an internal rendering engine, never as a served interface.

Status: **implementation has not started.** There is no package manager, build step, test suite, or linter yet, and the stack is still open — Python/Pillow, Node/sharp, canvas, and headless-browser rendering are all on the table.

## Card layout

Two vertical sections, no other structure:

```
┌─────────────────────────────────────┐
│              PHOTO                  │  full card width
├─────────────────────────────────────┤
│ [logo]│Body        56mm · f/1.4 ... │  row 1
│ Lens brand  Lens model      [signature]  row 2
│ 2026.03.14 · Kyoto                  │
└─────────────────────────────────────┘
```

All values are defined at a **760px design baseline** and the whole card scales uniformly to the output width: multiply every length — type size, letter-spacing, padding, logo height, signature width — by the same factor. Default output width is the photo's native long edge. Info rows must never wrap; minimum usable card width is ~380px.

**Type and color at the 760px baseline**

| Element | Font | Size | Tracking | Color |
|---|---|---|---|---|
| Body model | Archivo 500 | 13.5px | .04em | `#26241f` |
| Exposure readout | JetBrains Mono 400 | 12.5px | .1em | `#33302b` |
| Lens model | Archivo 400 | 12.5px | .03em | `#6d665e` |
| Lens brand | Archivo 400 | 12.5px | .1em | `#8a8279` |
| Date / location | JetBrains Mono 400 | 9px | .1em | `#b3ada4` |

Paper is `#faf8f4` (warm, default) or `#ffffff`. The logo divider rule is `#dcd7ce`, 1px wide and 12px tall. Spacing: 22px above and below the info strip, 20px at its sides and between columns, 14px between the two rows, 11px between logo and body model, 9px between the two lines of row 2's left column. Logo height 11px at opacity .88; signature width 108px (adjustable 70–180) at opacity .7, bottom-aligned with the text on its left.

Two border modes: `bleed` (default, for screen — photo touches the top and both sides, paper only below) and `equal` (for print — 18px on all four sides, plus a `rgba(40,34,26,.09)` inset hairline on the photo so light images do not dissolve into the paper).

**Invariants.** These are settled design decisions, not defaults — changing one is a design change, not a refactor:

- The photo is the subject. The largest type in the info strip is 13.5px; nothing is promoted to a heading.
- Gear before exposure. Row 1: logo + body model left, exposure readout right. Row 2: lens details and date/location left, signature right.
- No dividers except the single 1px rule between logo and body model. Grouping comes from columns and line spacing alone.
- Only the camera body gets a graphic logo; lenses are always text. Two logos fight each other.
- The info strip height is fixed and does not vary with photo aspect ratio (3:2, 1:1, 4:5, 2:3 all share it), so an album stays uniform.
- No border-radius, no shadows, no gradients, no accent colors.

## Data rules

| Field | EXIF source | Rendered as |
|---|---|---|
| Brand logo | `Make` | local logo file |
| Body model | `Model` | mapped display name |
| Lens model | `LensModel` | mapped display name |
| Focal length | `FocalLength` | `56mm` (integer, no decimals) |
| Aperture | `FNumber` | `f/1.4` |
| Shutter | `ExposureTime` | `1/250s`; `2s` at or above one second |
| ISO | `ISOSpeedRatings` | `ISO 400` |
| Date | `DateTimeOriginal` | `2026.03.14` (zero-padded) |
| Location | GPS reverse lookup or manual | always English, optional |

The exposure readout joins its parts with a space-padded middle dot: `56mm · f/1.4 · 1/250s · ISO 400`. Date and location use the same separator.

**Display names.** EXIF gear strings are often internal codes (`ILCE-7M4`) or bloated full names (`TAMRON 70-180mm F/2.8 Di III VC VXD G2`). The contract: display the raw string **as-is by default**, and keep separate user-editable override tables for bodies and lenses that rename only the entries explicitly registered in them. Never build a lookup that fails closed on unknown gear.

**Missing values** remove an element without changing any alignment or spacing:

- No location — the line keeps the date alone, same position and style.
- Lens shares the body's brand — the brand text is omitted, so it never repeats.
- No signature — the element is dropped; row 2's left column does not recenter or stretch.

## Assets

Brand logos and the signature are transparent PNGs cropped tight to the ink boundary — internal padding breaks alignment. Logos are aligned by `height`, never `width`. If no logo file matches the EXIF `Make`, fall back to text (Archivo 500, same size as the body model, `letter-spacing:.1em`, `#26241f`).

`signature.png` is a real handwritten signature scan: **private, never commit it**, and treat rendered cards as private too since the signature is burned into the image. `.gitignore` covers both.

## Conventions

Write code comments and config-file comments in English. Fonts are Archivo (proportional grotesk) and JetBrains Mono; no serifs. If a target environment lacks them, substitute a neutral grotesk — avoiding Inter/Roboto/Arial — and any monospace such as IBM Plex Mono.

Git is initialized on branch `main`.
