"""Render the info strip with Chromium.

Only the strip goes through the browser. The photo is never handed to it: that
keeps the photo's pixels, colour profile and bit depth untouched, and keeps the
browser working on an image a few hundred pixels tall no matter how large the
photo is.

What the browser buys us is text layout -- letter-spacing, baseline alignment
and flexbox edge-to-edge distribution -- at exactly the values the design
specifies, rather than reimplemented approximately in a drawing library.
"""

from __future__ import annotations

import html
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import layout
from .metadata import CardData

FONTS = Path(__file__).parent / "assets" / "fonts"

_FONT_FACES = [
    ("Archivo", "Archivo.ttf"),
    ("JetBrains Mono", "JetBrainsMono.ttf"),
    ("Noto Sans", "NotoSans.ttf"),
]


@dataclass(frozen=True)
class StripSpec:
    """Everything that varies between one rendered strip and the next."""

    data: CardData
    card_width: float
    frame: str = "bleed"
    paper: str = "warm"
    logo: Path | None = None
    signature: Path | None = None
    signature_width: float = layout.SIGNATURE_WIDTH


def _font_faces() -> str:
    return "\n".join(
        f"@font-face{{font-family:'{family}';src:url('file://{FONTS / filename}');"
        f"font-weight:100 900;font-display:block}}"
        for family, filename in _FONT_FACES
    )


def _stack(*families: str) -> str:
    return ",".join(f"'{f}'" for f in families) + ",sans-serif"


def build_html(spec: StripSpec) -> str:
    """The strip as a standalone document, laid out at the 760px baseline.

    Scaling to the output size is done by the browser's device pixel ratio, so
    every length in here stays at its design value and nothing has to be
    pre-multiplied.
    """
    d = spec.data
    mode = layout.FRAMES[spec.frame]
    paper = layout.PAPER[spec.paper]
    gear_font = _stack(layout.FONT_GEAR, layout.FONT_FALLBACK)
    mono_font = _stack(layout.FONT_READOUT, layout.FONT_FALLBACK)

    if spec.logo:
        brand = (
            f'<img src="file://{spec.logo}" alt="" '
            f'style="height:{layout.LOGO_HEIGHT}px;width:auto;display:block;'
            f'opacity:{layout.LOGO_OPACITY}">'
        )
    elif d.brand_label:
        # The spec's stand-in for a missing wordmark: the maker's name set at
        # the body model's size and colour, with wider tracking.
        brand = (
            f'<span style="font-family:{gear_font};font-size:{layout.SIZE_BODY}px;'
            f"font-weight:500;letter-spacing:{layout.TRACK_EXPOSURE}em;"
            f"line-height:{layout.LINE_HEIGHT};"
            f'color:{layout.COLOR_BODY};white-space:nowrap">{html.escape(d.brand_label)}</span>'
        )
    else:
        brand = ""

    divider = (
        f'<div style="width:{layout.DIVIDER_WIDTH}px;height:{layout.DIVIDER_HEIGHT}px;'
        f'background:{layout.COLOR_DIVIDER};flex:none"></div>'
        if brand and d.body
        else ""
    )

    body = (
        f'<div style="font-family:{gear_font};font-size:{layout.SIZE_BODY}px;font-weight:500;'
        f"letter-spacing:{layout.TRACK_BODY}em;color:{layout.COLOR_BODY};"
        f"line-height:{layout.LINE_HEIGHT};"
        f'white-space:nowrap">{html.escape(d.body)}</div>'
        if d.body
        else ""
    )

    exposure = (
        f'<div style="font-family:{mono_font};font-size:{layout.SIZE_EXPOSURE}px;'
        f"letter-spacing:{layout.TRACK_EXPOSURE}em;color:{layout.COLOR_EXPOSURE};"
        f"line-height:{layout.LINE_HEIGHT};"
        f'white-space:nowrap">{html.escape(d.exposure)}</div>'
        if d.exposure
        else ""
    )

    lens_brand = (
        f'<span style="letter-spacing:{layout.TRACK_LENS_BRAND}em;'
        f'color:{layout.COLOR_LENS_BRAND}">{html.escape(d.lens_brand)} </span>'
        if d.lens_brand
        else ""
    )
    lens = (
        f'<div style="font-family:{gear_font};font-size:{layout.SIZE_LENS}px;'
        f"letter-spacing:{layout.TRACK_LENS}em;color:{layout.COLOR_LENS};"
        f"line-height:{layout.LINE_HEIGHT};"
        f'white-space:nowrap">{lens_brand}{html.escape(d.lens)}</div>'
        if d.lens or d.lens_brand
        else ""
    )

    timeline = (
        f'<div style="font-family:{mono_font};font-size:{layout.SIZE_DATE}px;'
        f"letter-spacing:{layout.TRACK_DATE}em;color:{layout.COLOR_DATE};"
        f"line-height:{layout.LINE_HEIGHT};"
        f'white-space:nowrap">{html.escape(d.timeline)}</div>'
        if d.timeline
        else ""
    )

    signature = (
        f'<img src="file://{spec.signature}" alt="" '
        f'style="width:{spec.signature_width}px;height:auto;display:block;flex:none;'
        f'opacity:{layout.SIGNATURE_OPACITY};margin-bottom:{layout.SIGNATURE_BASELINE_NUDGE}px">'
        if spec.signature
        else ""
    )


    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
{_font_faces()}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{background:{paper}}}
#strip{{width:{layout.BASELINE_WIDTH}px;background:{paper};
  padding:0 {mode.card_pad_side}px;font-family:{gear_font}}}
#info{{padding:{mode.info_pad_top}px {mode.info_pad_side}px {mode.info_pad_bottom}px;
  display:flex;flex-direction:column;gap:{layout.ROW_GAP}px}}
#row1{{display:flex;align-items:center;justify-content:space-between;
  gap:{layout.ROW_GROUP_GAP}px;height:{layout.ROW1_HEIGHT}px}}
#row1left{{display:flex;align-items:center;gap:{layout.ROW1_LEFT_GAP}px;flex:none}}
#row2{{display:flex;align-items:flex-end;justify-content:space-between;
  gap:{layout.ROW_GROUP_GAP}px;height:{layout.ROW2_HEIGHT}px}}
#row2left{{display:flex;flex-direction:column;justify-content:flex-end;
  gap:{layout.ROW2_LINE_GAP}px;min-width:0}}
</style></head><body>
<div id="strip"><div id="info">
  <div id="row1"><div id="row1left">{brand}{divider}{body}</div>{exposure}</div>
  <div id="row2"><div id="row2left">{lens}{timeline}</div>{signature}</div>
</div></div>
</body></html>"""


def render(spec: StripSpec, browser=None) -> Image.Image:
    """Rasterize the strip at the card's real pixel width."""
    from playwright.sync_api import sync_playwright

    scale = layout.scale_for(spec.card_width)
    html_source = build_html(spec)

    def shoot(page_browser) -> bytes:
        page = page_browser.new_page(
            viewport={"width": int(layout.BASELINE_WIDTH), "height": 400},
            device_scale_factor=scale,
        )
        try:
            with tempfile.TemporaryDirectory() as tmp:
                doc = Path(tmp) / "strip.html"
                doc.write_text(html_source, encoding="utf-8")
                page.goto(doc.as_uri())
                page.wait_for_function("document.fonts.ready.then(() => true)")
                return page.locator("#strip").screenshot(type="png")
        finally:
            page.close()

    if browser is not None:
        png = shoot(browser)
    else:
        with sync_playwright() as pw:
            owned = pw.chromium.launch()
            try:
                png = shoot(owned)
            finally:
                owned.close()

    import io

    return Image.open(io.BytesIO(png)).convert("RGB")


def measure(spec: StripSpec, browser=None) -> dict[str, dict[str, float]]:
    """Return each element's box in baseline pixels, for geometry tests."""
    from playwright.sync_api import sync_playwright

    html_source = build_html(spec)
    script = """() => {
      const out = {};
      const ids = ['strip', 'info', 'row1', 'row1left', 'row2', 'row2left'];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        const r = el.getBoundingClientRect();
        out[id] = {x: r.x, y: r.y, width: r.width, height: r.height};
      }
      const row1 = document.getElementById('row1');
      const row2 = document.getElementById('row2');
      if (row1 && row1.lastElementChild !== row1.firstElementChild) {
        const r = row1.lastElementChild.getBoundingClientRect();
        out.exposure = {x: r.x, y: r.y, width: r.width, height: r.height};
      }
      if (row2 && row2.lastElementChild !== row2.firstElementChild) {
        const r = row2.lastElementChild.getBoundingClientRect();
        out.signature = {x: r.x, y: r.y, width: r.width, height: r.height};
      }
      return out;
    }"""

    def probe(page_browser):
        page = page_browser.new_page(viewport={"width": int(layout.BASELINE_WIDTH), "height": 400})
        try:
            with tempfile.TemporaryDirectory() as tmp:
                doc = Path(tmp) / "strip.html"
                doc.write_text(html_source, encoding="utf-8")
                page.goto(doc.as_uri())
                page.wait_for_function("document.fonts.ready.then(() => true)")
                return page.evaluate(script)
        finally:
            page.close()

    if browser is not None:
        return probe(browser)
    with sync_playwright() as pw:
        owned = pw.chromium.launch()
        try:
            return probe(owned)
        finally:
            owned.close()
