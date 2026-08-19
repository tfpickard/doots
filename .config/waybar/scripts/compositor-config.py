#!/usr/bin/env python3
"""Derive a Hyprland-compatible waybar config from a niri theme config.

The committed themes show workspaces and the focused window with the
`custom/niriws` / `custom/niriwindow` helpers, which follow niri's IPC event
stream. Under Hyprland there is no niri socket: those helpers exit at once,
waybar's `restart-interval` respawns them every few seconds, and the left side
of the bar stays empty.

Keeping a second hand-written theme in sync is how configs drift, so instead we
read the *same* theme config and swap only those two modules for the built-in
`hyprland/workspaces` and `hyprland/window` modules. Everything else -- styling,
groups, the other modules -- is untouched, so the existing style.css keeps
working.

Usage:
    compositor-config.py <source-config> <output-config>

Called from ~/.config/waybar/launch.sh when HYPRLAND_INSTANCE_SIGNATURE is set.
"""

from __future__ import annotations

import json
import re
import sys

# niri module -> (hyprland replacement, module settings)
REPLACEMENTS: dict[str, tuple[str, dict]] = {
    "custom/niriws": (
        "hyprland/workspaces",
        {
            "format": "{name}",
            "on-click": "activate",
            "all-outputs": False,
        },
    ),
    "custom/niriwindow": (
        "hyprland/window",
        {
            "format": "{title}",
            "max-length": 60,
            "separate-outputs": True,
        },
    ),
}


def strip_jsonc(text: str) -> str:
    """Drop // line comments, which waybar allows but json.loads does not.

    Comment markers inside string literals are left alone.
    """
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
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def convert(config: dict) -> dict:
    """Swap the niri-only modules for their Hyprland equivalents."""
    # Rewrite every module list (modules-left/center/right and any group/*).
    def rewrite(names: list) -> list:
        return [REPLACEMENTS.get(n, (n, None))[0] if isinstance(n, str) else n for n in names]

    for key, value in list(config.items()):
        if key.startswith("modules-") and isinstance(value, list):
            config[key] = rewrite(value)
        elif (
            key.startswith("group/")
            and isinstance(value, dict)
            and isinstance(value.get("modules"), list)
        ):
            value["modules"] = rewrite(value["modules"])

    # Drop the niri module definitions and add the Hyprland ones.
    for old, (new, settings) in REPLACEMENTS.items():
        config.pop(old, None)
        if new not in config:
            config[new] = dict(settings)

    return config


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(f"usage: {argv[0]} <source-config> <output-config>", file=sys.stderr)
        return 2

    src, dst = argv[1], argv[2]
    try:
        with open(src, encoding="utf-8") as fh:
            raw = fh.read()
        config = json.loads(strip_jsonc(raw))
    except (OSError, json.JSONDecodeError) as err:
        print(f"compositor-config: cannot read {src}: {err}", file=sys.stderr)
        return 1

    # Waybar accepts a single object or a list of bars.
    if isinstance(config, list):
        config = [convert(bar) for bar in config]
    elif isinstance(config, dict):
        config = convert(config)
    else:
        print("compositor-config: unexpected config structure", file=sys.stderr)
        return 1

    try:
        with open(dst, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=4)
            fh.write("\n")
    except OSError as err:
        print(f"compositor-config: cannot write {dst}: {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
