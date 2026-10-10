#!/usr/bin/env python3
"""Generate the SGI SDDM theme's pixel-art icons.

Sugar Candy ships smooth 28x28 Material glyphs. Next to bevelled Motif chrome
they are the one thing left that reads as 2015 rather than 1995, so they are
replaced with icons drawn on a 14x14 grid -- coarse enough that every pixel is
visible at the size the greeter actually draws them.

The designs live below as ASCII art rather than SVG path data, because the
whole point is that they are pixel grids: you can see and edit the picture.

Three things make these drop-in replacements rather than a QML change:

  * The filenames are fixed. Input.qml and SystemButtons.qml build icon paths
    as "../Assets/<Name>.svgz", so the names and the .svgz extension (gzipped
    SVG, which Qt's loader handles transparently) are part of the contract.
  * Colour comes from QML, not from here. Both call sites set `icon.color`,
    which makes Qt recolour the whole glyph, so the fill below is arbitrary --
    these only need to carry shape.
  * A 28-unit viewBox over a 14-cell grid means one cell is exactly 2 units,
    so the icon stays on whole pixels at 28px, 56px and every other doubling.
    `shape-rendering="crispEdges"` stops the renderer antialiasing the edges
    back into mush at the sizes in between.

The originals are recoverable from git history; they were committed intact
before this script first overwrote them.
"""

import gzip
import sys
from pathlib import Path

GRID = 14
CELL = 2  # viewBox units per grid cell; GRID * CELL = the 28x28 upstream size

# '#' is an inked pixel, anything else is transparent. Every row must be
# exactly GRID characters wide -- checked at build time, since a short row
# silently shifts the rest of the drawing left.
ICONS = {
    # Head and shoulders. Sits inside the username field, so it is the one
    # icon visible without triggering a power action.
    "User": """
    ..............
    ..............
    .....####.....
    ....######....
    ....######....
    ....######....
    .....####.....
    ..............
    ....######....
    ..##########..
    .############.
    .############.
    .############.
    ..............
    """,
    # IEC power symbol: broken ring, stem through the gap.
    "Shutdown": """
    ..............
    ......##......
    ......##......
    ...##.##.##...
    ..##..##..##..
    .##...##...##.
    .##........##.
    .##........##.
    .##........##.
    .##........##.
    ..##......##..
    ...########...
    ..............
    ..............
    """,
    # Ring with the arrowhead flaring off the top right.
    "Reboot": """
    ..............
    ....####...##.
    ..##....##.###
    .##......#####
    .##........##.
    ##............
    ##............
    ##............
    ##..........##
    .##........##.
    ..##......##..
    ....######....
    ..............
    ..............
    """,
    # Crescent moon. Two things it is easy to get wrong, because each one
    # turns it into a different glyph: drawn as an *outline* it closes into a
    # thick "C" and reads as Reboot sitting next to it, and drawn at uniform
    # thickness it reads as a bracket. It only says "moon" when the belly is
    # fat and the two tips flare back toward the bite on the right.
    "Suspend": """
    ..............
    ......####....
    ....######....
    ...#####......
    ..#####.......
    ..#####.......
    .#####........
    .#####........
    ..#####.......
    ..#####.......
    ...#####......
    ....######....
    ......####....
    ..............
    """,
    # Zz -- deeper sleep than the crescent, and legible at 28px where a
    # second moon variant would not be.
    "Hibernate": """
    ..............
    ..######......
    .....##.......
    ....##........
    ...##.........
    ..######......
    ..............
    ........####..
    ..........##..
    .........##...
    ........####..
    ..............
    ..............
    ..............
    """,
}


def parse(name, art):
    rows = [line.strip() for line in art.strip("\n").split("\n")]
    rows = [r for r in rows if r]
    if len(rows) != GRID:
        raise ValueError(f"{name}: {len(rows)} rows, expected {GRID}")
    for y, row in enumerate(rows):
        if len(row) != GRID:
            raise ValueError(f"{name}: row {y} is {len(row)} wide, expected {GRID}")
    return rows


def to_svg(rows):
    """Emit one <rect> per horizontal run of inked cells.

    Merging runs keeps the file small, but more importantly it stops adjacent
    per-pixel rects from showing hairline seams where their edges meet.
    """
    rects = []
    for y, row in enumerate(rows):
        x = 0
        while x < GRID:
            if row[x] != "#":
                x += 1
                continue
            start = x
            while x < GRID and row[x] == "#":
                x += 1
            rects.append(
                f'<rect x="{start * CELL}" y="{y * CELL}" '
                f'width="{(x - start) * CELL}" height="{CELL}"/>'
            )
    size = GRID * CELL
    body = "\n  ".join(rects)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}" shape-rendering="crispEdges">\n'
        f'  <g fill="#ffffff">\n  {body}\n  </g>\n'
        f"</svg>\n"
    )


def main():
    out = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else Path(__file__).resolve().parent.parent / "sddm/sgi-sddm/Assets"
    )
    if not out.is_dir():
        sys.exit(f"not a directory: {out}")
    for name, art in ICONS.items():
        svg = to_svg(parse(name, art))
        path = out / f"{name}.svgz"
        # mtime=0 so regenerating byte-identical art doesn't churn the gzip
        # header and show up as a spurious diff.
        with gzip.GzipFile(path, "wb", mtime=0) as fh:
            fh.write(svg.encode())
        print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
