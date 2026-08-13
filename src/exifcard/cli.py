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

BROWSER_HINT = (
    "Chromium is missing. Run [bold]exifcard install-browser[/] once, then try again."
)


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


def _album_root(path: Path) -> Path:
    resolved = path.resolve()
    return resolved if resolved.is_dir() else resolved.parent


def _output_dir(photo: Path, root: Path, out_root: Path) -> Path:
    """Where one photo's card belongs.

    Cards mirror the source layout under a folder named after the album, so
    two albums passed in one run stay apart, and --recursive keeps a nested
    folder nested instead of flattening subfolders from different albums into
    a single directory where their files would collide.
    """
    album = out_root / (root.name or "cards")
    relative = photo.resolve().parent.relative_to(root)
    return album / relative if relative != Path(".") else album


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

    # Resolved once, before the batch, so that every card in a run is set from
    # the same files in the same order rather than from whatever the directory
    # happened to hold when each photo reached it.
    fonts = tuple(path.expanduser().resolve() for path in cfg.fonts)
    for path in fonts:
        if not path.exists():
            raise typer.BadParameter(f"font not found: {path}")

    photos: list[Path] = []
    roots: dict[Path, Path] = {}
    for path in paths:
        if not path.exists():
            raise typer.BadParameter(f"no such path: {path}")
        root = _album_root(path)
        for photo in _collect_photos(path, recursive):
            photos.append(photo)
            roots[photo] = root
    if not photos:
        err.print("[yellow]No photos found.[/]")
        raise typer.Exit(1)

    # Each photo's output folder comes from its own source folder, so passing
    # two albums in one run does not funnel one of them into a directory named
    # after the other -- and their same-numbered files do not collide.
    out_root = out or Path(cfg.out)
    out_dirs = {photo: _output_dir(photo, roots[photo], out_root) for photo in photos}
    caption_files = {
        directory: locations.load(locations_file or directory / locations.FILENAME)
        for directory in set(out_dirs.values())
    }

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
        fonts=fonts,
    )

    if dry_run:
        console.print(f"[bold]{len(photos)}[/] photo(s)")
        for photo in photos:
            out_dir = out_dirs[photo]
            target = render.plan_destination(photo, out_dir, render.resolve_format(photo, fmt))
            status = "[yellow]exists[/]" if target.exists() else "new"
            caption = caption_files[out_dir].get(photo.name) or location or ""
            console.print(f"  {photo.name:24} -> {target}  {status}  {caption}")
        return

    overwrite_state: dict = {"all": True if force else (False if skip_existing else None)}
    written = skipped = 0
    failures: list[tuple[Path, str]] = []

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except PlaywrightError as failure:
            if "Executable doesn't exist" in str(failure):
                err.print(f"[red]{BROWSER_HINT}[/]")
                raise typer.Exit(1) from None
            raise
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
                    out_dir = out_dirs[photo]
                    target = render.plan_destination(
                        photo, out_dir, render.resolve_format(photo, fmt)
                    )
                    if not _resolve_overwrite(target, overwrite_state):
                        skipped += 1
                        progress.advance(task)
                        continue

                    options.location = caption_files[out_dir].get(photo.name) or location or ""
                    try:
                        outcome = render.render(photo, target, options, browser=browser)
                    except (RuntimeError, OSError, ValueError) as failure:
                        # One unreadable file should not cost you the other 199.
                        # The run finishes, names what failed, and exits non-zero
                        # so a script still notices.
                        failures.append((photo, str(failure)))
                        progress.advance(task)
                        continue
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

    destinations = ", ".join(str(d) for d in sorted(set(out_dirs.values())))
    summary = f"[green]{written}[/] written, {skipped} skipped"
    if failures:
        summary += f", [red]{len(failures)} failed[/]"
    console.print(f"{summary} -> {destinations}")

    if failures:
        err.print("[red]failed:[/]")
        for photo, reason in failures:
            err.print(f"  {photo.name}  {reason}")
        raise typer.Exit(1)


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

    target = locations_file or _output_dir(photos[0], _album_root(path), out or Path(cfg.out)) / locations.FILENAME
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


@app.command("install-browser")
def install_browser(
    with_deps: Annotated[
        bool,
        typer.Option(
            "--with-deps",
            help="Also install Chromium's system libraries. Needed on most Linux "
            "distributions, where the browser otherwise downloads but will not start. "
            "Uses sudo.",
        ),
    ] = False,
) -> None:
    """Download the Chromium build used to render the info strip.

    Playwright keeps its browsers outside the Python package, so this has to
    happen once after installing. It is a command of its own because an
    installed tool exposes only exifcard's own entry point -- `playwright` is
    not on PATH, so the usual `playwright install chromium` is not available.
    """
    import subprocess

    command = [sys.executable, "-m", "playwright", "install"]
    if with_deps:
        command.append("--with-deps")
    command.append("chromium")

    result = subprocess.run(command)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)
    console.print("[green]Chromium installed.[/]")


@app.command("config-example")
def config_example() -> None:
    """Print a starter configuration file."""
    console.print(config_module.EXAMPLE, highlight=False)


if __name__ == "__main__":
    app()
