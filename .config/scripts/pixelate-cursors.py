#!/usr/bin/env python3
"""Rebuild an Xcursor theme as pixel art.

The stock themes on this box are all antialiased: even the chunky-looking ones
(whiteglass, handhelds) are just *small* bitmaps with soft edges, so scaling
them up gives blur rather than bigger pixels. This takes a theme you already
like and re-renders every cursor in it as genuine low-bit pixel art:

    1. area-downscale each cursor to a small square grid (default 16x16)
    2. hard-threshold alpha to fully on or fully off -- no soft edges, which
       is what actually reads as "8-bit"
    3. quantise the remaining colours down to a small palette (default 16,
       i.e. 4-bit colour)
    4. scale back up by whole-number factors with nearest-neighbour, so one
       source pixel becomes a crisp NxN block

Working from an existing theme means the whole cursor set comes along --
including the dozens of symlinked aliases that applications actually ask for
-- instead of having to hand-draw fifty sprites.

Usage:
    pixelate-cursors.py [source-theme] [--name NAME] [--grid N]
                        [--colors N] [--scales 1,2,3,4] [--list]

    pixelate-cursors.py whiteglass --name whiteglass-4bit

The result is written to ~/.local/share/icons/<NAME>. Apply it with:

    gsettings set org.gnome.desktop.interface cursor-theme '<NAME>'
"""
import argparse
import os
import shutil
import struct
import sys

from PIL import Image

CHUNK_IMAGE = 0xFFFD0002
SEARCH_ROOTS = [
    os.path.expanduser("~/.local/share/icons"),
    os.path.expanduser("~/.icons"),
    "/usr/share/icons",
]
# Install to ~/.icons rather than ~/.local/share/icons. Both resolve on this
# system, but only ~/.icons is in the path compiled into libXcursor and
# libwayland-cursor ("~/.icons:/usr/share/icons:/usr/share/pixmaps"); support
# for $XDG_DATA_HOME/icons is a newer addition that older builds -- and
# whatever a given app happens to bundle -- may not have. ~/.icons is the one
# location every version searches.
OUT_ROOT = os.path.expanduser("~/.icons")


# Modern toolkits (GTK4, Qt, Electron/Chromium, Firefox) ask for cursors by
# their CSS names. Legacy X11 themes like DMZ ship only the traditional names,
# so those requests miss entirely and the app silently falls back to some other
# theme -- which is how you end up with one blocky pointer and one smooth one,
# or a stray red I-beam from a completely different theme.
#
# Mapping CSS name -> first legacy name that exists closes the gap. Aliases are
# only created when the target is present and the name is not already taken.
CSS_ALIASES = {
    "default": ["left_ptr", "arrow", "top_left_arrow"],
    "context-menu": ["left_ptr"],
    "pointer": ["hand2", "hand1", "hand"],
    "text": ["xterm", "ibeam"],
    "vertical-text": ["xterm"],
    "wait": ["watch"],
    "progress": ["left_ptr_watch", "watch"],
    "help": ["question_arrow", "left_ptr_help"],
    "crosshair": ["cross", "tcross", "crosshair"],
    "cell": ["plus", "cross"],
    "not-allowed": ["crossed_circle", "circle"],
    "no-drop": ["dnd-none", "crossed_circle"],
    "grab": ["hand1", "hand2"],
    "grabbing": ["grabbing", "fleur"],
    "all-scroll": ["fleur"],
    "move": ["fleur", "move"],
    "alias": ["link"],
    "copy": ["copy"],
    "col-resize": ["sb_h_double_arrow", "h_double_arrow"],
    "row-resize": ["sb_v_double_arrow", "v_double_arrow"],
    "ew-resize": ["sb_h_double_arrow", "h_double_arrow"],
    "ns-resize": ["sb_v_double_arrow", "v_double_arrow"],
    "nesw-resize": ["fd_double_arrow"],
    "nwse-resize": ["bd_double_arrow"],
    "n-resize": ["top_side"],
    "e-resize": ["right_side"],
    "s-resize": ["bottom_side"],
    "w-resize": ["left_side"],
    "ne-resize": ["top_right_corner"],
    "nw-resize": ["top_left_corner"],
    "se-resize": ["bottom_right_corner"],
    "sw-resize": ["bottom_left_corner"],
    "zoom-in": ["left_ptr"],
    "zoom-out": ["left_ptr"],
    "pointing_hand": ["hand2"],
    "openhand": ["hand1"],
    "closedhand": ["grabbing", "fleur"],
    "forbidden": ["crossed_circle"],
    "size_ver": ["sb_v_double_arrow"],
    "size_hor": ["sb_h_double_arrow"],
    "size_bdiag": ["fd_double_arrow"],
    "size_fdiag": ["bd_double_arrow"],
    "size_all": ["fleur"],
    "split_h": ["sb_h_double_arrow"],
    "split_v": ["sb_v_double_arrow"],
    "up_arrow": ["sb_up_arrow", "left_ptr"],
}


def add_css_aliases(cursors_dir):
    """Symlink modern CSS cursor names onto whichever legacy name exists."""
    added = 0
    for alias, targets in CSS_ALIASES.items():
        dst = os.path.join(cursors_dir, alias)
        if os.path.lexists(dst):
            continue
        for t in targets:
            if os.path.exists(os.path.join(cursors_dir, t)):
                os.symlink(t, dst)
                added += 1
                break
    return added


# --- Xcursor container ------------------------------------------------------

def read_cursor(path):
    """Decode an Xcursor file into [(size, w, h, xhot, yhot, delay, BGRA)]."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"Xcur":
        return []
    _hdr, _ver, ntoc = struct.unpack_from("<III", data, 4)
    out = []
    for i in range(ntoc):
        ctype, _sub, pos = struct.unpack_from("<III", data, 16 + i * 12)
        if ctype != CHUNK_IMAGE:
            continue
        hs, _t, size, _v, w, h, xh, yh, delay = struct.unpack_from(
            "<IIIIIIIII", data, pos)
        px = data[pos + hs: pos + hs + w * h * 4]
        if len(px) == w * h * 4:
            out.append((size, w, h, xh, yh, delay, px))
    return out


def write_cursor(path, images):
    """Encode [(size, w, h, xhot, yhot, delay, BGRA)] as an Xcursor file."""
    ntoc = len(images)
    header = b"Xcur" + struct.pack("<III", 16, 0x10000, ntoc)
    toc = b""
    body = b""
    pos = len(header) + ntoc * 12
    for size, w, h, xh, yh, delay, px in images:
        toc += struct.pack("<III", CHUNK_IMAGE, size, pos + len(body))
        body += struct.pack("<IIIIIIIII", 36, CHUNK_IMAGE, size, 1,
                            w, h, xh, yh, delay) + px
    with open(path, "wb") as f:
        f.write(header + toc + body)


def to_image(w, h, px):
    im = Image.frombytes("RGBA", (w, h), bytes(px))
    b, g, r, a = im.split()          # Xcursor stores BGRA
    return Image.merge("RGBA", (r, g, b, a))


def to_bgra(im):
    r, g, b, a = im.split()
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


# --- the pixel-art part -----------------------------------------------------

def pixelate(im, grid, ncolors, alpha_cut=110):
    """Reduce an RGBA cursor to a hard-edged, few-colour grid x grid sprite."""
    if im.size != (grid, grid):
        # BOX (area average) rather than LANCZOS: no ringing, and it behaves
        # sanely for the small ratios we ask for once the source is chosen
        # near the grid size.
        im = im.resize((grid, grid), Image.BOX)
    small = im

    r, g, b, a = small.split()
    # Hard alpha is what sells the effect: antialiased edges are exactly what
    # makes a small cursor read as "smooth but blurry" rather than "pixel art".
    # It also removes the soft drop shadow these themes are drawn with.
    a = a.point(lambda v: 255 if v >= alpha_cut else 0)

    rgb = Image.merge("RGB", (r, g, b))
    # Quantise only the visible pixels, so fully transparent ones (often black)
    # cannot drag palette entries away from the real colours.
    if a.getbbox():
        vis = rgb.copy()
        vis.putalpha(a)
        pal = vis.crop(a.getbbox()).convert("RGB").quantize(
            colors=max(2, ncolors), method=Image.MEDIANCUT)
        rgb = rgb.quantize(palette=pal, dither=Image.NONE).convert("RGB")

    out = rgb.copy()
    out.putalpha(a)
    return out


def convert_file(src, dst, grid, ncolors, scales):
    imgs = read_cursor(src)
    if not imgs:
        return False

    # Work from the native size closest to the grid, not the largest one.
    # These themes are drawn with a soft drop shadow; area-averaging a 48px
    # rendering down to 16 cells smears that shadow into the cursor body and
    # everything turns to grey mush. Starting near 1:1 keeps the silhouette,
    # and the alpha threshold then discards the shadow outright.
    best = min({i[0] for i in imgs}, key=lambda s: (abs(s - grid), -s))
    frames = [i for i in imgs if i[0] == best]

    out = []
    for size, w, h, xh, yh, delay, px in frames:
        sprite = pixelate(to_image(w, h, px), grid, ncolors)
        for s in scales:
            big = sprite.resize((grid * s, grid * s), Image.NEAREST)
            # Hotspot in source pixels -> grid cell -> upscaled pixels.
            gx = min(grid - 1, int(round(xh * grid / max(1, w))))
            gy = min(grid - 1, int(round(yh * grid / max(1, h))))
            out.append((grid * s, grid * s, grid * s,
                        gx * s, gy * s, delay, to_bgra(big)))
    if not out:
        return False
    write_cursor(dst, out)
    return True


# --- theme plumbing ---------------------------------------------------------

def find_theme(name):
    for root in SEARCH_ROOTS:
        p = os.path.join(root, name)
        if os.path.isdir(os.path.join(p, "cursors")):
            return p
    return None


def list_themes():
    seen = []
    for root in SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for t in sorted(os.listdir(root)):
            p = os.path.join(root, t)
            if os.path.isdir(os.path.join(p, "cursors")) and t not in seen:
                seen.append(t)
                imgs = []
                for c in os.listdir(os.path.join(p, "cursors"))[:200]:
                    f = os.path.join(p, "cursors", c)
                    if os.path.isfile(f) and not os.path.islink(f):
                        imgs = read_cursor(f)
                        if imgs:
                            break
                sizes = sorted({i[0] for i in imgs}) if imgs else []
                print(f"  {t:24s} sizes={sizes}")
    return 0


def verify(theme, size=32):
    """Report what libXcursor clients actually resolve for a theme.

    This is the question that matters when a cursor change appears not to have
    worked, and it is not answerable by looking at the files: it depends on the
    search path, the Inherits chain and whether the modern CSS names exist.
    """
    import ctypes
    import ctypes.util

    class XcursorImage(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint), ("size", ctypes.c_uint),
                    ("width", ctypes.c_uint), ("height", ctypes.c_uint),
                    ("xhot", ctypes.c_uint), ("yhot", ctypes.c_uint),
                    ("delay", ctypes.c_uint),
                    ("pixels", ctypes.POINTER(ctypes.c_uint32))]

    try:
        lib = ctypes.CDLL(ctypes.util.find_library("Xcursor") or "libXcursor.so.1")
    except OSError:
        print("libXcursor not available", file=sys.stderr)
        return 1
    lib.XcursorLibraryLoadImage.restype = ctypes.POINTER(XcursorImage)
    lib.XcursorLibraryLoadImage.argtypes = [ctypes.c_char_p, ctypes.c_char_p,
                                            ctypes.c_int]

    env = os.environ.get("XCURSOR_THEME", "<unset>")
    print(f"XCURSOR_THEME={env}   probing theme {theme!r} at {size}px\n")
    bad = 0
    for name in ("default", "text", "pointer", "grab", "wait", "not-allowed",
                 "ns-resize", "xterm", "hand2", "left_ptr"):
        p = lib.XcursorLibraryLoadImage(name.encode(), theme.encode(), size)
        if not p:
            print(f"  {name:12s} -> NOT FOUND")
            bad += 1
            continue
        im = p.contents
        px = [im.pixels[i] for i in range(im.width * im.height)]
        soft = sum(1 for v in px if 8 < (v >> 24) < 248)
        cols = len({v & 0xFFFFFF for v in px if (v >> 24) > 8})
        red = sum(1 for v in px if (v >> 24) > 8
                  and ((v >> 16) & 0xFF) > 120
                  and ((v >> 16) & 0xFF) > ((v >> 8) & 0xFF) + 40)
        tag = "pixel-art" if soft == 0 and cols <= 20 else "SMOOTH (another theme?)"
        if soft:
            bad += 1
        note = "  [reddish - looks like the sgi theme]" if red > 4 else ""
        print(f"  {name:12s} -> {im.width}x{im.height} colors={cols:3d} "
              f"soft={soft:4d}  {tag}{note}")

    print("\nAll pixel-art means the theme is installed correctly." if not bad
          else "\nSomething is resolving elsewhere - check Inherits and the CSS aliases.")
    print("Running apps cache their cursor theme at startup; restart them to "
          "see changes\n(a VS Code window reload is not enough, it reuses the "
          "same process).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", default="whiteglass")
    ap.add_argument("--name", default=None, help="output theme name")
    ap.add_argument("--grid", type=int, default=16, help="pixel grid (default 16)")
    ap.add_argument("--colors", type=int, default=16,
                    help="palette size; 16 = 4-bit colour (default)")
    ap.add_argument("--scales", default="1,2,3,4",
                    help="whole-number upscales to emit (default 1,2,3,4)")
    ap.add_argument("--list", action="store_true", help="list installed themes")
    ap.add_argument("--verify", nargs="?", const="", metavar="THEME",
                    help="report what libXcursor clients resolve, then exit")
    args = ap.parse_args()

    if args.list:
        return list_themes()
    if args.verify is not None:
        return verify(args.verify or os.environ.get("XCURSOR_THEME", "default"))

    src_dir = find_theme(args.source)
    if not src_dir:
        print(f"no cursor theme named {args.source!r}; try --list", file=sys.stderr)
        return 1

    scales = [int(s) for s in args.scales.split(",") if s.strip()]
    name = args.name or f"{args.source}-{args.grid}px"
    out_dir = os.path.join(OUT_ROOT, name)
    out_cursors = os.path.join(out_dir, "cursors")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_cursors)

    src_cursors = os.path.join(src_dir, "cursors")
    converted = skipped = linked = 0
    for entry in sorted(os.listdir(src_cursors)):
        s = os.path.join(src_cursors, entry)
        d = os.path.join(out_cursors, entry)
        # Themes alias heavily (hashed names -> canonical ones); keeping the
        # links means every name an application might ask for still resolves.
        if os.path.islink(s):
            target = os.readlink(s)
            os.symlink(target, d)
            linked += 1
            continue
        try:
            if convert_file(s, d, args.grid, args.colors, scales):
                converted += 1
            else:
                shutil.copy2(s, d)
                skipped += 1
        except Exception as e:
            print(f"  ! {entry}: {e}", file=sys.stderr)
            shutil.copy2(s, d)
            skipped += 1

    aliased = add_css_aliases(out_cursors)

    with open(os.path.join(out_dir, "index.theme"), "w") as f:
        f.write("[Icon Theme]\n"
                f"Name={name}\n"
                f"Comment=Pixel-art rebuild of {args.source} "
                f"({args.grid}x{args.grid}, {args.colors} colours)\n"
                "Inherits=hicolor\n")
    with open(os.path.join(out_dir, "cursor.theme"), "w") as f:
        f.write(f"[Icon Theme]\nInherits={name}\n")

    print(f"{name}: {converted} pixelated, {linked} aliases, "
          f"{aliased} CSS names, {skipped} copied")
    print(f"  -> {out_dir}")
    print(f"  gsettings set org.gnome.desktop.interface cursor-theme '{name}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
