# exifcard

A local CLI tool that turns a photo and its EXIF data into a finished card image: the photo on top, a quiet metadata strip below, written out as a single flat image file.

It is built for personal album archiving and the occasional share, not for social platforms. The output is an image, not a web page — no buttons, no device frames, no interactive elements.

## Status

Early. The layout is specified and settled; the implementation has not been written yet. There is nothing to install or run at this point.

## What the card shows

```
┌─────────────────────────────────────┐
│              PHOTO                  │
├─────────────────────────────────────┤
│ [logo]│Body        56mm · f/1.4 ... │
│ Lens brand  Lens model   [signature]│
│ 2026.03.14 · Kyoto                  │
└─────────────────────────────────────┘
```

Camera brand logo, body model, lens brand (only when it differs from the body's), lens model, focal length, aperture, shutter speed, ISO, date, an optional location, and an optional handwritten signature.

Fields are read from EXIF (`Make`, `Model`, `LensModel`, `FocalLength`, `FNumber`, `ExposureTime`, `ISOSpeedRatings`, `DateTimeOriginal`) and normalized for display. Gear names appear exactly as EXIF reports them unless a user-editable table renames them, so `ILCE-7M4` can read as `α7 IV` without every camera needing to be registered first.

## Design principles

- The photo is the subject. The metadata strip stays quiet — nothing in it is promoted to a heading.
- The info strip has a fixed height regardless of the photo's aspect ratio, so a whole album stays visually consistent.
- Grouping comes from columns and line spacing, not dividers or boxes.
- No rounded corners, no shadows, no gradients, no accent colors.
- The layout is defined once at a 760px baseline and scales uniformly to any output size, so text never reflows between sizes.

## License

MIT. Free to use, modify, and sell, including commercially; keep the copyright and license notice with any substantial portion you redistribute. See [LICENSE](LICENSE).
