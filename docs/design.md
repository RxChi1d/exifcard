**English** | [繁體中文](design.zh-TW.md)

# Design notes

The decisions behind exifcard and the constraints that produced them. The [README](../README.md) covers what it does and how to run it; this document is for anyone changing the code or evaluating the engineering.

Every number here was measured rather than estimated, on a 33MP Sony α7C II JPEG unless stated otherwise.

## Rendering pipeline

The photo and the info strip never overlap. That is not an observation about the design, it is the hinge the implementation turns on:

```
Typst sets only the strip              Pillow assembles the card
┌──────────────────┐                   ┌──────────────────┐
│                  │                   │  photo bytes,    │
│   (no photo)     │                   │  untouched       │
├──────────────────┤                   ├──────────────────┤
│  7008 × 590      │  ───────────────> │  strip           │
└──────────────────┘                   └──────────────────┘
```

Handing the whole card to the renderer would be simpler and would cost three things, none of them necessary: the photo gets re-sampled, converted into the renderer's colour space, and flattened to 8 bits. This is not hypothetical. Passing a 3000×2002 JPEG through Typst at 1:1 with no scaling at all changes 22% of its pixels, by up to 5 levels, and takes 1.4 seconds; a headless browser did the same thing for the same reason. Keeping the photo out means its pixels reach the output file as they left the camera.

Where each element sits is worked out in Python, in design units, before anything is drawn. The renderer is handed absolute positions and asked only to set the type and rasterize it. That was forced at first — a Typst grid cell sizes itself from its content rather than from a height declared on the box inside it, which left the exposure readout half a pixel high — but it is the better division: `strip.measure` and `strip.render` then answer from the same arithmetic and cannot drift apart.

## Text rendering

The strip is typeset by Typst rather than drawn with Pillow. Shipping a typesetting engine to set one strip of text is a real cost, so it is worth stating what it buys.

The design specifies letter-spacing on every text element — `.1em` on the exposure readout, `.04em` on the body model, `.03em` on the lens name. **Pillow has no tracking API.** `ImageDraw.text` takes `spacing`, which is the gap between lines. Producing `.1em` means drawing character by character and advancing the pen by hand.

Doing that also gives up the font's own metrics. Measured on the bundled Archivo at 100pt:

```
                        "AV" as a string   "A" + "V" separately   difference
Typst                        130.20               133.00             2.80    ← kerning applied
Pillow (basic layout)        138.00               138.00             0.00    ← none
```

Archivo carries a GPOS table. Pillow's default layout engine ignores it, and the optional Raqm engine is absent from the standard wheels — this environment reports `HAVE_RAQM` false and falls back silently. So a drawing-library implementation would set gear names without the kerning the typeface specifies *and* with hand-rolled tracking on top, on a card whose whole premise is that the typography is exact.

Nor does it need the whole browser. Chromium measured the same pair at 130.141 and 132.969, a difference of 2.828 — the same GPOS table read by the same shaper, since both engines use HarfBuzz. Across the card's real strings the two agree to within 0.03 design px.

## Why not a browser

The strip was rendered by headless Chromium until the numbers stopped justifying it.

```
                        Chromium                     Typst
install       190MB browser, downloaded    62MB, an ordinary wheel
              by a separate command        installed by uv sync
one strip     89ms                         5.4ms
one 33MP card 656ms                        463ms
```

The install figure understates it: `playwright install chromium` fetches both the full browser and the headless shell, about 530MB, for a tool that only ever runs headless.

But the deciding factor was neither size nor speed. **A browser's text output depends on the platform.** Blink rounds the ascent and descent to whole pixels, floors the half-leading, quantizes the line box to 1/64 of a pixel, and then snaps the painted baseline to a whole pixel again — and does not do it identically everywhere. That is why the pixel comparisons had to be a local check that CI never saw, and why this repository's own claim that a card renders identically on any machine was not actually tested.

Typst's does not depend on the platform, and `tests/test_strip_golden.py` now holds it to that: four reference renders, recorded on macOS, compared with `array_equal` on macOS, Linux and Windows. A tolerance there would pass whether or not the guarantee held, which is why there is none.

Three of the browser's behaviours had to be reproduced rather than assumed, each found by measurement:

- **Letter-spacing is applied after every character, the last one included**, so a tracked element carries one unit of empty space on its right edge. Typst tracks between characters only. The same shortfall repeats at every font-fallback boundary, because Typst starts a new shaping run wherever the covering font changes — `α7C II` is one string but two runs, the alpha from Noto Sans and the rest from Archivo, and it came up exactly one unit short.
- **Typst wraps where the browser overflows.** Wrapping would silently turn one line into two and change a height that has no relief mechanism, which is worse than an overrun that is at least visible. Every text leaf is pinned to its own measured width so it can only overflow.
- **Typst has no opacity property.** A bundled SVG mark carries its own on the root element, which is what the browser's `opacity` on an `<img>` amounted to; a raster mark has it folded into the alpha channel, which composites identically because the paper behind is opaque.

Blink's rounding was deliberately *not* reproduced. Doing so matched Chromium to 0.0000 and was tried — but it is the platform binding itself, and carrying it into a new renderer would have carried the limitation with it. The design's own numbers are used instead, which moves the card by up to 0.875 design px from what the browser drew on macOS: a few pixels along a glyph edge at the scale a card is rendered.

Typst is pinned exactly, `typst==0.15.0`, not with a floor. It is pre-1.0 and has shipped layout-breaking changes between minor releases, so an upgrade is a full re-verification rather than a routine bump.

## Lossless compositing

`--lossless` shells out to `jpegtran` rather than using Pillow, because bit-exactness rules out decoding. Any path through Pillow turns the file into pixels and encodes them again, and that round trip *is* the loss — no quality setting avoids it, only makes it smaller.

Staying exact means moving the stored DCT coefficients without ever expanding them. Pillow exposes no such API: it reads a JPEG's quantization tables but not its coefficients. The pure-Python alternatives were checked rather than assumed:

```
jpeglib        1.0.2    wheels: cp38 only
jpegtran-cffi  0.5.2    wheels: none, source only
```

So `jpegtran` is the honest dependency. It stays optional, and only `--lossless` needs it. The photo's dimensions must be multiples of 16 because that is the JPEG minimum coded unit; the flag raises rather than falling back, since a promise that silently degrades is worse than an error.

It degraded silently anyway, for a long time, in a way none of that guarded against. `jpegtran -copy` governs which markers survive from the file it is *editing* — the canvas — and not from the photo dropped into it. The canvas was written with neither EXIF nor a colour profile, under `-copy none`, so `--lossless` returned a card carrying neither: every coefficient bit-exact, and a Display P3 or Adobe RGB photo then read as sRGB, so the subject of the card came out wrong. The markers are now written onto the canvas and copied through.

One difference does remain and cannot be removed. Decoded, the card's last row of photo pixels differs from the source's — 4288 pixels of a 4288×2848 frame, one row, at the seam. The stored coefficients are identical; what changes is that chroma upsampling at the bottom edge now has the strip below it instead of nothing. It is a property of compositing subsampled JPEG at the block level, not a loss in the file.

## Colour

The card is tagged with the photo's ICC profile, because the photo is the subject and its bytes are never touched. That makes the photo's profile the card's, and everything else has to move into it.

The strip does not arrive there by itself. The design states its colours as hex, which means sRGB, and the renderer emits exactly those numbers with no profile of its own — so on a wide-gamut source they were being read in the wrong space. Measured, by taking each colour through the profile the card is tagged with and back:

```
                    Display P3    Adobe RGB (1998)
paper, warm             0 levels        1 level
body ink                1 level         6 levels
date grey               1 level         4 levels
```

Small, and small for a reason worth naming: the palette is near-neutral greys and warm off-whites, which sit close together in every space, and the design forbids accent colours. It stays small only for as long as that holds, which is not something the code should assume. The strip is now carried into the card's profile before the two are joined; the photo is not, because it is already in it.

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

Both widths are measured from the real text, per photo, starting from a clean state — a one-way ratchet would leave a card shrunken because the previous photo in the batch had a long lens name.

This is also why the display-name tables are not for shortening. They turn an internal code into the product's actual name (`ILCE-7CM2` → `α7C II`); deciding which words of a name matter is not the tool's call.

Widening is uncapped on purpose. A ceiling would stop the canvas growing and put the overrunning text straight back on top of the signature at the ceiling's width — the same failure, reached by a different route. Past 900 the run says so instead, naming the gear table entry that would bring the card back to full size.

## What the caption may ask for

The two-step adaptation belongs to the gear names. It does not extend to the location caption, and the difference is not stylistic:

|  | gear name | caption |
|---|---|---|
| where it comes from | EXIF | the user typed it |
| length | bounded by what the product is called | unbounded |
| may be shortened | only by a gear table entry, which changes **every** card in the album carrying that lens | by editing one line |
| obligation to print in full | identification — a lens shortened past recognition is worthless | none; the design already allows no caption at all |

So the canvas is settled by the photo's proportions and the gear names alone, measured with the caption removed. The caption is then held to what is left beside the signature. It may have the first step, tightening, which costs no type size; it may not have the second. A caption that widened the canvas would set one card's type smaller than every other card in the album, with nothing on the card to say why, on the strength of a line its author could have shortened in a second.

When it does not fit, that photo fails and the run reports the geometry:

```
IMG_4821.HEIC  the location does not fit: it needs 334 design px of the 282 left
               beside the signature (canvas 450); shorten it in locations.toml
```

Geometry rather than a character limit, because there is no stable character limit: 80 dotted i's, 80 ideographs and 80 capitals are three different widths, and the date shares the line with all of them.

The budget, in design pixels:

| card | the whole line | after the `YYYY.MM.DD · ` prefix |
|---|---|---|
| 3:2 landscape, with a signature | 592 | 510 |
| 3:2 landscape, no signature | 720 | 638 |
| 9:16 portrait, with a signature | 282 | 200 |

The last row is what this rule costs: `Fushimi Inari, Kyoto` measures 208 against that column's 282, so one more short word fits and a second does not. For an album shot mostly in portrait that is the common case rather than the exception — accepted, because that line is the only thing on the card its author can shorten at no cost.

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

## The signature

The signature is bounded on both axes: it may be as wide as `signature_width` and as tall as the row it sits in, whichever binds first. Any transparent margin is cropped off before it is drawn.

Sizing it by width alone left its height to the file's proportions. Row 2 is 35 design units tall with bottom-aligned contents, so a signature squarer than 108/35 — about 3:1 — rendered taller than its row and grew upward through the row gap into the exposure readout. The strip's height is fixed, so nothing gave way; the two simply overlapped. A 2:1 signature came out 52.6 units tall against a 35-unit row and was drawn across the ISO reading.

Cropping matters for the same reason. The margin is what gets sized, so ink filling 56% of a padded file's height rendered at 56% of the size asked for, floating above the baseline rather than sitting on it. That the file should be cut tight to the ink used to be a requirement stated in a config comment and enforced nowhere.

## CJK captions

No CJK font is bundled. The smallest usable ones are 9-17MB against the 2.8MB the card's own three faces weigh, most users never need one, and a repository is the wrong place to put a binary that large: git history is permanent, fonts do not delta-compress, and every future version would add another full copy. The user registers files they already have instead, in `config.toml`, and they are tried in that order after the bundled faces.

Order is the user's because language detection would be a guess: `京都` is the same two code points in Chinese and in Japanese, and the two traditions draw several characters differently. Nothing here inspects the text to pick a font. What the run does instead is say when one caption was drawn from more than one file, which is the point at which letterforms stop matching within a line.

Registered fonts go **last** in the font stack. A stack is resolved character by character, and every CJK font also covers Latin, so anywhere earlier would hand it the gear names and the exposure readout and restyle the card with nothing said about it.

### Size compensation

Han ink is taller than the digits it shares a line with, so at one font-size the place name overpowers the date — backwards for the quietest line on the card. Measured from the outlines rather than the declared ascent, since it is ink the eye levels against:

```
                              ink above baseline    to match the digits
JetBrains Mono digits                0.741 em        —
Noto Sans TC                         0.842           0.880
Noto Sans JP                         0.832           0.891
Noto Sans KR                         0.832           0.891
Noto Sans SC                         0.842           0.880
Noto Sans CJK TC                     0.848           0.874
```

The ratio that levels them spans 0.874 to 0.891 across sans, serif and rounded designs in four regional variants, so `CJK_SIZE_RATIO` is one constant at 0.88 rather than a table to maintain per font. It has to be font-independent: nothing is bundled, so the value cannot be tuned against any particular file.

Compensation is applied per run of CJK characters rather than to the whole line, because a caption is often mixed — `京都 Fushimi Inari` — and sizing the element down would shrink the Latin with it.

The tracking is restated on each run even though it would be inherited. An inherited `letter-spacing` arrives as the length it already computed to on the parent: `.1em` on a 9px line inherits as 0.9px and stays 0.9px inside a 7.92px run. Restating it in em ties both to the run's own size, which is what keeps a character's advance at exactly `size × 0.88 × 1.1` and the caption budget arithmetic rather than measured.

Row 2 keeps its height. Its 35 design px leave the date line 11.0 once the lens line and the gap have taken theirs; the line box is 10.8 uncompensated and 9.5 compensated, and an inline child smaller than its line does not grow it. That 0.2px of headroom is asserted in `tests/test_cjk.py`, because overflow there would push up into row 1 rather than down into the paper.

### Fonts that fail to load

A declared face whose file is missing does not stop `document.fonts.ready` from resolving. The page then lays out in whatever the system offers, is measured as though that were the design, and is photographed the same way. The cmap check cannot catch it either: it reads the file the user named, not what the browser received. Every page therefore checks `FontFace.status` before measuring or shooting, and raises rather than producing a card.

## Bundled assets

Fonts and brand marks ship inside the package, so a card renders identically on any machine and the tool works offline. All are freely licensed: fonts under the SIL Open Font License, brand marks in the public domain as `PD-textlogo`, with each mark's source recorded in `logos.toml`.

Fetching marks at runtime was considered and rejected. It would trade a copyright question that does not exist — plain lettering is below the threshold of originality — for network dependency, rate limits, non-reproducible output, and marks chosen by a database rather than by eye. Wikidata's logo property returns a square roundel for Leica and a group logo for Sony; both are wrong for a card that aligns marks by height.

A mark is only bundled if it survives 11px on warm paper. Nothing's is white lettering on a solid black field, which at that size reads as a black bar, so it uses the text fallback instead.

## Known limitations

- **8 bits per channel.** Compositing happens in 8-bit RGB, so a 10-bit HEIF is narrowed on the way in. The run says so rather than narrowing silently. A 16-bit pipeline is possible but would need format-specific encode paths.
- **No RAW.** The card is made at the end of a workflow, after the picture has been chosen and graded, where the file is already a JPEG or HEIF. Reading RAW would pull the tool into developing, which other software already does.
- **HEIC above ~28MP needs tiling**, which is applied automatically. Without it libheif writes a file it cannot read back.
- **`--lossless` needs `jpegtran` on PATH**, which has no standard package on Windows. The flag reports that rather than failing obscurely; everything else works there.
- **A character no available font covers renders as an empty box.** No system font is ever consulted, which is what makes a card reproducible, so there is nothing to fall back to. The run says which characters before it renders.
