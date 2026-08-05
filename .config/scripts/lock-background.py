#!/usr/bin/env python3
"""Generate Silicon Graphics style lock-screen backgrounds, one per output.

The source wallpaper (~/Pictures/Wallpaper/indigo.png) is 1280x800, which is
smaller than any of the monitors here, so scaling it up for the lock screen
gives a soft, obviously-upscaled logo. Instead this lifts the white logo out of
the flat blue field as an alpha mask and re-composites it, crisply, onto a
canvas at each output's exact resolution.

Doing it per output also avoids the other problem: with a single image and
--scaling fill, swaylock crops the same picture differently on a 1920x1080
panel and a 1920x1200 one, so the logo lands in a different place on each
screen.

    lock-background.py            regenerate for the currently connected outputs
    lock-background.py --list     show what would be generated
    lock-background.py --size WxH generate one extra image at a fixed size
                                  (for SDDM, which runs before niri does)

Output goes to ~/.cache/sgi-lock/<output>.png, and the files are regenerated
whenever the source wallpaper is newer. They're in the cache rather than the
repo because they're derived, per machine, and several megabytes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

SOURCE = os.path.expanduser("~/Pictures/Wallpaper/indigo.png")
CACHE = os.path.expanduser("~/.cache/sgi-lock")

# The flat field colour of the SGI wallpaper, sampled from the source: it is
# 89% of the image. Everything else is the white logo and its antialiasing.
SGI_BLUE = (0x29, 0x55, 0x8E)

# Logo width as a fraction of the output width. The original artwork puts the
# lockup across ~90% of a 1280px canvas, which is far too shouty spread across
# a 1920px monitor with a password ring on top of it.
LOGO_WIDTH_FRACTION = 0.42

# Vertical placement, as a fraction of output height. Kept above centre so the
# unlock indicator (which swaylock draws dead centre) doesn't sit on the logo.
LOGO_CENTRE_Y = 0.27


def require_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        sys.exit(
            "python3-pil is required.\n"
            "    sudo apt install python3-pil"
        )


def outputs() -> dict[str, tuple[int, int]]:
    """Map output name -> (width, height) in physical pixels, via niri IPC."""
    try:
        raw = subprocess.run(
            ["niri", "msg", "--json", "outputs"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
        data = json.loads(raw)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}

    found = {}
    for name, info in data.items():
        modes = info.get("modes") or []
        idx = info.get("current_mode")
        if modes and idx is not None and 0 <= idx < len(modes):
            mode = modes[idx]
            found[name] = (mode["width"], mode["height"])
        else:
            logical = info.get("logical") or {}
            if logical.get("width") and logical.get("height"):
                found[name] = (int(logical["width"]), int(logical["height"]))
    return found


def extract_logo():
    """Return the logo as an RGBA image, cropped to its bounding box.

    The source is white artwork on a flat blue field, so the alpha channel is
    just "how far is this pixel from the background colour", normalised. That
    keeps the antialiased edges smooth instead of producing a jagged 1-bit
    cutout.
    """
    from PIL import Image

    src = Image.open(SOURCE).convert("RGB")
    width, height = src.size
    pixels = src.load()

    # Max possible distance from the background, used to normalise.
    span = max(
        abs(255 - SGI_BLUE[0]),
        abs(255 - SGI_BLUE[1]),
        abs(255 - SGI_BLUE[2]),
    )

    logo = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    out = logo.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            dist = max(
                abs(r - SGI_BLUE[0]),
                abs(g - SGI_BLUE[1]),
                abs(b - SGI_BLUE[2]),
            )
            if dist > 8:  # ignore JPEG-ish noise in the flat field
                alpha = min(255, int(255 * dist / span))
                out[x, y] = (255, 255, 255, alpha)

    box = logo.getbbox()
    return logo.crop(box) if box else logo


def render(logo, size: tuple[int, int], dest: str,
           logo_y: float = LOGO_CENTRE_Y,
           logo_width: float = LOGO_WIDTH_FRACTION) -> None:
    from PIL import Image

    width, height = size
    canvas = Image.new("RGB", (width, height), SGI_BLUE)

    target_w = int(width * logo_width)
    scale = target_w / logo.width
    target_h = max(1, int(logo.height * scale))
    scaled = logo.resize((target_w, target_h), Image.LANCZOS)

    x = (width - target_w) // 2
    y = int(height * logo_y) - target_h // 2
    canvas.paste(scaled, (x, y), scaled)

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    canvas.save(dest)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true",
                    help="show what would be generated, and exit")
    ap.add_argument("--size", metavar="WxH", action="append", default=[],
                    help="also generate a fixed-size image (repeatable)")
    ap.add_argument("--force", action="store_true",
                    help="regenerate even if the cached file is up to date")
    ap.add_argument("--logo-y", type=float, default=LOGO_CENTRE_Y,
                    metavar="F",
                    help="vertical centre of the logo, 0-1 (default %(default)s). "
                         "The SDDM background uses a low value so the logo sits "
                         "under the login form instead of behind the clock.")
    ap.add_argument("--logo-width", type=float, default=LOGO_WIDTH_FRACTION,
                    metavar="F",
                    help="logo width as a fraction of output width "
                         "(default %(default)s)")
    ap.add_argument("--out", metavar="PATH",
                    help="write to this exact path instead of the cache "
                         "(only valid with a single --size)")
    args = ap.parse_args()

    if not os.path.exists(SOURCE):
        sys.exit(f"source wallpaper not found: {SOURCE}")

    # With --out the caller wants exactly one specific image, so don't mix in
    # the auto-detected outputs.
    targets: dict[str, tuple[int, int]] = {} if args.out else dict(outputs())
    for spec in args.size:
        try:
            w, h = (int(v) for v in spec.lower().split("x", 1))
        except ValueError:
            sys.exit(f"bad --size {spec!r}, expected WxH like 1920x1080")
        targets[f"{w}x{h}"] = (w, h)

    if not targets:
        # No niri running and nothing asked for: still produce something
        # usable, so this works from a TTY or a fresh install.
        targets["1920x1080"] = (1920, 1080)

    if args.list:
        for name, (w, h) in sorted(targets.items()):
            print(f"  {name:<28} {w}x{h} -> {os.path.join(CACHE, name + '.png')}")
        return 0

    require_pillow()

    src_mtime = os.path.getmtime(SOURCE)
    if args.out and len(targets) != 1:
        sys.exit("--out needs exactly one --size")

    stale = {
        name: size for name, size in targets.items()
        if args.force or args.out
        or not os.path.exists(os.path.join(CACHE, f"{name}.png"))
        or os.path.getmtime(os.path.join(CACHE, f"{name}.png")) < src_mtime
    }

    if not stale:
        print("all lock backgrounds are up to date")
        return 0

    # Extracting the mask is the slow part, so do it once for all outputs.
    logo = extract_logo()
    for name, size in sorted(stale.items()):
        dest = args.out if args.out else os.path.join(CACHE, f"{name}.png")
        render(logo, size, dest, args.logo_y, args.logo_width)
        print(f"wrote {dest} ({size[0]}x{size[1]})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
