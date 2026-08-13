**English** | [繁體中文](design.zh-TW.md)

# Design notes

The decisions behind exifcard and the constraints that produced them. The [README](../README.md) covers what it does and how to run it; this document is for anyone changing the code or evaluating the engineering.

Every number here was measured rather than estimated, on a 33MP Sony α7C II JPEG unless stated otherwise.

## Rendering pipeline

The photo and the info strip never overlap. That is not an observation about the design, it is the hinge the implementation turns on:

```
Chromium renders only the strip        Pillow assembles the card
┌──────────────────┐                   ┌──────────────────┐
│                  │                   │  photo bytes,    │
│   (no photo)     │                   │  untouched       │
├──────────────────┤                   ├──────────────────┤
│  7008 × 590      │  ───────────────> │  strip           │
└──────────────────┘                   └──────────────────┘
```

Handing the whole card to the browser would be simpler and would cost four things, none of them necessary: the photo gets re-sampled, converted into the screenshot's colour space, flattened to 8 bits, and bounded by Chromium's maximum surface size. Keeping it out means the photo's pixels reach the output file as they left the camera.

## Text rendering

The info strip is typeset by Chromium rather than drawn with Pillow. Shipping a 95MB Chromium to typeset one strip of text is a real cost, so it is worth stating what it buys.

The design specifies letter-spacing on every text element — `.1em` on the exposure readout, `.04em` on the body model, `.03em` on the lens name. **Pillow has no tracking API.** `ImageDraw.text` takes `spacing`, which is the gap between lines. Producing `.1em` means drawing character by character and advancing the pen by hand.

Doing that also gives up the font's own metrics. Measured on the bundled Archivo at 100px:

```
                        "AV" as a string   "A" + "V" separately
Chromium                     127.33 px            130.16 px      ← kerning applied
Pillow (basic layout)        138.00 px            138.00 px      ← identical, so none
```

Archivo carries a GPOS table. Pillow's default layout engine ignores it, and the optional Raqm engine is absent from the standard wheels — so a drawing-library implementation would set gear names without the kerning the typeface specifies *and* with hand-rolled tracking on top, on a card whose whole premise is that the typography is exact.

The strip this produces matches the design reference at a mean difference of 2.8 levels in 255, which is anti-aliasing noise.

## Lossless compositing

`--lossless` shells out to `jpegtran` rather than using Pillow, because bit-exactness rules out decoding. Any path through Pillow turns the file into pixels and encodes them again, and that round trip *is* the loss — no quality setting avoids it, only makes it smaller.

Staying exact means moving the stored DCT coefficients without ever expanding them. Pillow exposes no such API: it reads a JPEG's quantization tables but not its coefficients. The pure-Python alternatives were checked rather than assumed:

```
jpeglib        1.0.2    wheels: cp38 only
jpegtran-cffi  0.5.2    wheels: none, source only
```

So `jpegtran` is the honest dependency. It stays optional, and only `--lossless` needs it. The photo's dimensions must be multiples of 16 because that is the JPEG minimum coded unit; the flag raises rather than falling back, since a promise that silently degrades is worse than an error.

## Encoding defaults

JPEG output defaults to quality 95, carrying over the source's chroma sampling but not its quantization tables. A card is a derivative made for looking at, while the original stays in the library. An earlier version reused the source JPEG's quantization tables, which is the right answer to a different question — how to preserve an original — and produced a card *larger* than the photo it came from:

```
                                       size     vs source   photo-area deviation
source (α7C II, 4:2:2)                18.76 MB      100%     —
reusing the camera's tables           19.57 MB      104%     mean 0.12
quality 95 + the camera's sampling     6.87 MB       37%     mean 1.07
quality 95 + Pillow's default 4:2:0    6.35 MB       34%     mean 1.10
```

The default is the third row: quality 95, carrying over the camera's chroma sampling so a body that shot 4:2:2 is not quietly halved to 4:2:0. A mean deviation near one level in 255 is invisible at any viewing size.

Nothing caught the regression for a long time because every test asked whether the picture still looked right, and by that measure the uncompressed version looked better. There is now a test on the encoding itself.

HEIC quality is an x265 mapping, not a quantization scale, so the numbers are not comparable across formats — `heic 70` sits at roughly the fidelity of `jpg 95`. HEIC also needs tiled encoding above about 28MP or libheif produces a file it cannot decode; tiling costs about 1% in size.

## Type size and aspect ratio

Scale used to come straight from the card's width, which punished portrait photos: their long edge is the height, so the card is narrower and the type shrank with it. A 9:16 phone shot ended up with lettering half the size of a landscape frame's.

The strip now lays out on its own canvas of width `D` and is scaled from there:

```
a = photo height / photo width
D = clamp(604 / a, 450, 760)      # narrower canvas → larger type
strip scale = card width / D
```

| ratio | D | exposure line, cards at equal height |
|---|---|---|
| 3:2 | 760 | 14.2px |
| 1:1 | 604 | 12.6px |
| 4:5 | 483 | 13.9px |
| 2:3 | 450 | 11.8px |
| 9:16 | 450 | 10.1px |

Landscape lands on 760 and is unchanged to the pixel; a test asserts that against the reference image. 2:3 and 9:16 bottom out at the clamp — 450 is the narrowest the info row itself fits in — so they do not reach the landscape size, but they reach the largest size that still fits.

A long body model next to a long lens name can overrun the row. Rather than wrap, truncate or abbreviate, the card gives ground in two steps:

1. **Tighten** — the exposure readout's tracking (`.1em` → `.04em`) and the gap between the two column groups (`20` → `12`). Worth 8-10% of the width and no type size at all.
2. **Widen the canvas** — only if tightening was not enough, shrinking the whole block evenly.

Both widths are measured in the browser from the real text, per photo, starting from a clean state — a one-way ratchet would leave a card shrunken because the previous photo in the batch had a long lens name.

This is also why the display-name tables are not for shortening. They turn an internal code into the product's actual name (`ILCE-7CM2` → `α7C II`); deciding which words of a name matter is not the tool's call.

## Focal length

The focal length on the card is the **35mm equivalent**, not the physical length engraved on the lens. Three steps, in order:

1. `FocalLengthIn35mmFilm` if the camera recorded one.
2. `FocalLength` — the physical value — if it did not.
3. Nothing at all if neither is present. Zero counts as absent at both steps: some bodies write it rather than leaving the tag out, which says the same thing, and no lens is 0mm.

The physical number is what the lens barrel says, which argues for showing it, but it cannot record what was actually framed. Measured on one iPhone 16 Pro:

```
                    FocalLength   FocalLengthIn35mmFilm
IMG_4350.heic         6.765mm             48mm
IMG_4355.JPG          6.765mm             30mm
```

Two different framings, one number. The sensor crop is what changed, and only the equivalent value carries it. The same applies less dramatically to any crop-sensor body: an X-E5 at 17mm frames like 26mm.

Older DSLRs — a Canon EOS 700D, a Nikon D90 — omit the tag entirely, so those cards keep the physical value. That leaves two bases in use across a collection without the card saying which, and the alternative was rejected: marking the equivalent ones would put a symbol on modern bodies and not on old ones, drawing attention to a distinction most readers do not care about. The fallback is also what the card always showed, so no photo reads worse than it did before.

## Bundled assets

Fonts and brand marks ship inside the package, so a card renders identically on any machine and the tool works offline. All are freely licensed: fonts under the SIL Open Font License, brand marks in the public domain as `PD-textlogo`, with each mark's source recorded in `logos.toml`.

Fetching marks at runtime was considered and rejected. It would trade a copyright question that does not exist — plain lettering is below the threshold of originality — for network dependency, rate limits, non-reproducible output, and marks chosen by a database rather than by eye. Wikidata's logo property returns a square roundel for Leica and a group logo for Sony; both are wrong for a card that aligns marks by height.

A mark is only bundled if it survives 11px on warm paper. Nothing's is white lettering on a solid black field, which at that size reads as a black bar, so it uses the text fallback instead.

## Known limitations

- **8 bits per channel.** Compositing happens in 8-bit RGB, so a 10-bit HEIF is narrowed on the way in. The run says so rather than narrowing silently. A 16-bit pipeline is possible but would need format-specific encode paths.
- **No RAW.** The card is made at the end of a workflow, after the picture has been chosen and graded, where the file is already a JPEG or HEIF. Reading RAW would pull the tool into developing, which other software already does.
- **HEIC above ~28MP needs tiling**, which is applied automatically. Without it libheif writes a file it cannot read back.
- **`--lossless` needs `jpegtran` on PATH**, which has no standard package on Windows. The flag reports that rather than failing obscurely; everything else works there.
