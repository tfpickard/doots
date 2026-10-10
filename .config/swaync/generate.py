#!/usr/bin/env python3
"""Generate swaync's config.json from the commented config.jsonc.

swaync parses its config with a strict JSON parser: a single `//` comment makes
the WHOLE file fail to load, and it silently falls back to built-in defaults
with only a CRITICAL line on stderr to tell you. That's a miserable way to keep
a documented config, so the readable version lives in config.jsonc and this
strips the comments to produce the file swaync actually reads.

    ~/.config/swaync/generate.py          # regenerate config.json
    ~/.config/swaync/generate.py --check  # verify it's up to date (exit 1 if not)

Edit config.jsonc, run this, then reload with `swaync-client -R && swaync-client -rs`.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "config.jsonc")
DST = os.path.join(HERE, "config.json")


def strip_comments(text: str) -> str:
    """Remove // line comments that are not inside a string literal."""
    out = []
    for line in text.splitlines():
        in_string = False
        escaped = False
        cut = None
        for i, ch in enumerate(line):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = not in_string
            elif ch == "/" and not in_string and line[i : i + 2] == "//":
                cut = i
                break
        out.append(line if cut is None else line[:cut].rstrip())
    # Drop the blank lines the comments leave behind.
    return "\n".join(l for l in out if l.strip())


def main() -> int:
    check = "--check" in sys.argv

    try:
        raw = open(SRC, encoding="utf-8").read()
    except OSError as err:
        print(f"cannot read {SRC}: {err}", file=sys.stderr)
        return 1

    stripped = strip_comments(raw)

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as err:
        print(f"{SRC} is not valid JSONC: {err}", file=sys.stderr)
        return 1

    rendered = json.dumps(parsed, indent=2) + "\n"

    if check:
        try:
            current = open(DST, encoding="utf-8").read()
        except OSError:
            current = ""
        if current != rendered:
            print(f"{DST} is out of date; run {os.path.basename(__file__)}",
                  file=sys.stderr)
            return 1
        print("config.json is up to date")
        return 0

    with open(DST, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    print(f"wrote {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
