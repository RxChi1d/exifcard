"""Command line interface."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from PIL import Image
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

from . import config as config_module
from . import encode, layout, locations, metadata, render

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="Render a photo and its EXIF metadata into a finished card image.",
)
console = Console()
err = Console(stderr=True)

PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".heic", ".heif"}

IO_PANEL = "Input and output"
ENCODE_PANEL = "Encoding"
CARD_PANEL = "Card"

QUALITY_HELP = (
    "Encoder quality. The scale differs per format and the numbers are not "
    "comparable: jpg 1-100 (default 95, plus the source's own chroma sampling), "
    "heic 1-100 (default 70, about the same fidelity as jpg 95), png ignores it. "
    "Output is lossy by default; use --lossless for a bit-exact photo."
)


def _collect_photos(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    walker = path.rglob("*") if recursive else path.glob("*")
    return sorted(
        p for p in walker if p.is_file() and p.suffix.lower() in PHOTO_SUFFIXES and not p.name.startswith(".")
    )


def _album_name(path: Path) -> str:
    resolved = path.resolve()
    directory = resolved if resolved.is_dir() else resolved.parent
    return directory.name or "cards"


def _resolve_overwrite(destination: Path, state: dict) -> bool:
    """Ask before replacing an existing card, remembering an "all" answer."""
    if not destination.exists():
        return True
    if state.get("all") is not None:
        return state["all"]

    if not sys.stdin.isatty():
        raise typer.BadParameter(
            f"{destination} already exists and this is not an interactive terminal. "
            "Pass --force to overwrite or --skip-existing to leave it alone."
        )

    answer = console.input(f"[yellow]{destination}[/] exists. Overwrite? [y/N/a/s/q] ").strip().lower()
    if answer == "a":
        state["all"] = True
        return True
    if answer == "s":
        state["all"] = False
        return False
    if answer == "q":
        raise typer.Abort()
    return answer == "y"


@app.command("render")
def render_cards(
    paths: Annotated[list[Path], typer.Argument(help="Photo files or directories to render.")],
    out: Annotated[
        Path | None, typer.Option("--out", help="Output root. Defaults to ./outputs.", rich_help_panel=IO_PANEL)
    ] = None,
    recursive: Annotated[
        bool, typer.Option("--recursive", help="Descend into subdirectories.", rich_help_panel=IO_PANEL)
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing cards without asking.", rich_help_panel=IO_PANEL)
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option("--skip-existing", help="Leave existing cards alone without asking.", rich_help_panel=IO_PANEL),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be written, without writing it.", rich_help_panel=IO_PANEL),
    ] = False,
    fmt: Annotated[
        str | None,
        typer.Option("--format", help="Output format. Defaults to the input's format.", rich_help_panel=ENCODE_PANEL),
    ] = None,
    quality: Annotated[
        int | None, typer.Option("--quality", help=QUALITY_HELP, rich_help_panel=ENCODE_PANEL)
    ] = None,
    lossless: Annotated[
        bool,
        typer.Option(
            "--lossless",
            help="Copy the photo's JPEG data verbatim instead of re-encoding it. "
            "Requires jpegtran and a photo whose dimensions are multiples of 16; "
            "fails loudly rather than quietly falling back.",
            rich_help_panel=ENCODE_PANEL,
        ),
    ] = False,
    width: Annotated[
        int | None,
        typer.Option("--width", help="Card width in pixels. Defaults to the photo's own resolution.", rich_help_panel=ENCODE_PANEL),
    ] = None,
    exif_mode: Annotated[
        str,
        typer.Option(
            "--exif",
            help="all keeps the source EXIF, safe drops GPS and serial numbers, none writes no metadata.",
            rich_help_panel=ENCODE_PANEL,
        ),
    ] = "all",
    frame: Annotated[
        str | None,
        typer.Option("--frame", help="bleed (screen) or equal (print, adds a hairline).", rich_help_panel=CARD_PANEL),
    ] = None,
    paper: Annotated[
        str | None, typer.Option("--paper", help="warm or white.", rich_help_panel=CARD_PANEL)
    ] = None,
    signature: Annotated[
        Path | None, typer.Option("--signature", help="Signature image, overriding the config.", rich_help_panel=CARD_PANEL)
    ] = None,
    no_signature: Annotated[
        bool, typer.Option("--no-signature", help="Render without a signature.", rich_help_panel=CARD_PANEL)
    ] = False,
    location: Annotated[
        str | None,
        typer.Option("--location", help="Caption applied to every photo in this run.", rich_help_panel=CARD_PANEL),
    ] = None,
    locations_file: Annotated[
        Path | None,
        typer.Option("--locations", help="locations.toml to read per-photo captions from.", rich_help_panel=CARD_PANEL),
    ] = None,
    config_path: Annotated[Path | None, typer.Option("--config", help="Configuration file to use.")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Report each card as it is written.")] = False,
) -> None:
    """Render cards for one or more photos."""
    cfg = config_module.Config.load(config_path)

    if fmt and fmt not in encode.FORMATS:
        raise typer.BadParameter(f"--format must be one of {', '.join(encode.FORMATS)}")
    if exif_mode not in ("all", "safe", "none"):
        raise typer.BadParameter("--exif must be all, safe or none")
    frame = frame or cfg.frame
    if frame not in layout.FRAMES:
        raise typer.BadParameter("--frame must be bleed or equal")
    paper = paper or cfg.paper
    if paper not in layout.PAPER:
        raise typer.BadParameter("--paper must be warm or white")
    if force and skip_existing:
        raise typer.BadParameter("--force and --skip-existing contradict each other")

    signature_path = None if no_signature else (signature or cfg.signature)
    if signature_path:
        signature_path = signature_path.expanduser().resolve()
        if not signature_path.exists():
            raise typer.BadParameter(f"signature not found: {signature_path}")

    photos: list[Path] = []
    for path in paths:
        if not path.exists():
            raise typer.BadParameter(f"no such path: {path}")
        photos.extend(_collect_photos(path, recursive))
    if not photos:
        err.print("[yellow]No photos found.[/]")
        raise typer.Exit(1)

    out_root = out or Path(cfg.out)
    out_dir = out_root / _album_name(paths[0])
    captions = locations.load(locations_file or out_dir / locations.FILENAME)

    options = render.Options(
        frame=frame,
        paper=paper,
        width=width,
        fmt=fmt,
        quality=quality,
        lossless=lossless,
        exif_mode=exif_mode,
        signature=signature_path,
        signature_width=cfg.signature_width or layout.SIGNATURE_WIDTH,
        gear=cfg.gear,
    )

    if dry_run:
        console.print(f"[bold]{len(photos)}[/] photo(s) -> {out_dir}")
        for photo in photos:
            target = render.plan_destination(photo, out_dir, render.resolve_format(photo, fmt))
            status = "[yellow]exists[/]" if target.exists() else "new"
            caption = captions.get(photo.name) or location or ""
            console.print(f"  {photo.name:24} -> {target.name:24} {status}  {caption}")
        return

    overwrite_state: dict = {"all": True if force else (False if skip_existing else None)}
    written = skipped = 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                TimeRemainingColumn(),
                console=console,
                disable=len(photos) < 2,
            ) as progress:
                task = progress.add_task("Rendering", total=len(photos))
                for photo in photos:
                    target = render.plan_destination(
                        photo, out_dir, render.resolve_format(photo, fmt)
                    )
                    if not _resolve_overwrite(target, overwrite_state):
                        skipped += 1
                        progress.advance(task)
                        continue

                    options.location = captions.get(photo.name) or location or ""
                    try:
                        outcome = render.render(photo, target, options, browser=browser)
                    except (RuntimeError, OSError, ValueError) as failure:
                        err.print(f"[red]{photo.name}: {failure}[/]")
                        raise typer.Exit(1) from None
                    written += 1
                    if verbose:
                        console.print(
                            f"  {photo.name} -> {target} "
                            f"({outcome.card_size[0]}x{outcome.card_size[1]}"
                            f"{', lossless' if outcome.lossless else ''})"
                        )
                    for note in outcome.notes:
                        err.print(f"  [yellow]{photo.name}: {note}[/]")
                    progress.advance(task)
        finally:
            browser.close()

    console.print(f"[green]{written}[/] written, {skipped} skipped -> {out_dir}")


@app.command("locations")
def locations_cmd(
    path: Annotated[Path, typer.Argument(help="Photo directory to scan.")],
    out: Annotated[Path | None, typer.Option("--out", help="Output root. Defaults to ./outputs.")] = None,
    locations_file: Annotated[
        Path | None, typer.Option("--locations", help="Write to this file instead of the default.")
    ] = None,
    config_path: Annotated[Path | None, typer.Option("--config", help="Configuration file to use.")] = None,
) -> None:
    """Add every photo in a directory to a locations.toml, leaving captions for you to fill in.

    Existing entries, comments and ordering are never touched, so running this
    again after shooting more frames only appends what is new.
    """
    cfg = config_module.Config.load(config_path)
    photos = _collect_photos(path, recursive=False)
    if not photos:
        err.print("[yellow]No photos found.[/]")
        raise typer.Exit(1)

    target = locations_file or (out or Path(cfg.out)) / _album_name(path) / locations.FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[str, str]] = []
    for photo in photos:
        try:
            with Image.open(photo) as im:
                data = metadata.read(photo, image=im, gear=cfg.gear)
            note = " ".join(p for p in (data.date, data.body) if p)
        except Exception:
            note = ""
        entries.append((photo.name, note))

    added = locations.scaffold(target, entries)
    console.print(f"[green]{added}[/] new entr{'y' if added == 1 else 'ies'} appended to {target}")


@app.command("config-example")
def config_example() -> None:
    """Print a starter configuration file."""
    console.print(config_module.EXAMPLE, highlight=False)


if __name__ == "__main__":
    app()
