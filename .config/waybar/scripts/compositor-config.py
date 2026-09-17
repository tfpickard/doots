#!/usr/bin/env python3
"""Derive a compositor-specific waybar config from a niri theme config.

Two things this generates, both from the same source theme so there is only
ever one file to keep in sync:

  hyprland   Under Hyprland there is no niri IPC socket, so the committed
             themes' `custom/niriws` / `custom/niriwindow` helpers (which
             follow niri's event stream) exit at once, waybar's
             restart-interval respawns them every few seconds, and the left
             side of the bar stays empty. This mode swaps those two modules
             for the built-in `hyprland/workspaces` and `hyprland/window`.

  niri-outputs
             waybar draws one identical bar per output by default, and the
             committed custom/niriws shows *every* workspace from *every*
             output on all of them. With one named workspace per app and
             three monitors, that's unreadable. This mode expands the single
             bar config into an array of bars -- one per connected output,
             via waybar's own "output" key -- and passes each helper
             `--output <connector>` so it only shows what belongs there.

             The trap: waybar's "output" matches the Wayland *connector*
             name (DP-2, eDP-1, ...), not make/model/serial -- the opposite
             of how niri/config.kdl pins monitors, specifically because
             connector names change when cables move. `niri msg -j outputs`
             is keyed by connector and carries the serial, so that's queried
             here at generation time rather than baked in.

Usage:
    compositor-config.py hyprland <source-config> <output-config>
    compositor-config.py niri-outputs <source-config> <output-config>

Called from ~/.config/waybar/launch.sh.
"""

from __future__ import annotations

import copy
import json
import subprocess
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
            "max-length": 34,
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


def convert_hyprland(config: dict) -> dict:
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


def niri_outputs() -> list[dict]:
    """Connected outputs, sorted left-to-right by logical x position.

    `niri msg -j outputs` is keyed by connector name; each value carries the
    serial (None for the laptop panel, which has no EDID serial worth
    matching on -- its connector name "eDP-1" never changes anyway).
    """
    try:
        proc = subprocess.run(
            ["niri", "msg", "-j", "outputs"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        data = json.loads(proc.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as err:
        print(f"compositor-config: niri msg -j outputs failed: {err}", file=sys.stderr)
        return []

    outputs = [
        {
            "connector": connector,
            "serial": info.get("serial"),
            "x": (info.get("logical") or {}).get("x", 0),
        }
        for connector, info in data.items()
    ]
    outputs.sort(key=lambda o: o["x"])
    return outputs


def generate_per_output(base: dict, outputs: list[dict]) -> list[dict]:
    """One bar per output, each filtered to just that output's workspaces
    and focused-window title via the two custom modules' --output flag."""
    bars = []
    for o in outputs:
        bar = copy.deepcopy(base)
        bar["output"] = o["connector"]
        for mod in ("custom/niriws", "custom/niriwindow"):
            if mod in bar and "exec" in bar[mod]:
                bar[mod] = dict(bar[mod])
                bar[mod]["exec"] = f"{bar[mod]['exec']} --output {o['connector']}"
        bars.append(bar)
    return bars


def load_config(path: str) -> dict | list | None:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        return json.loads(strip_jsonc(raw))
    except (OSError, json.JSONDecodeError) as err:
        print(f"compositor-config: cannot read {path}: {err}", file=sys.stderr)
        return None


def write_config(path: str, config) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=4)
            fh.write("\n")
        return True
    except OSError as err:
        print(f"compositor-config: cannot write {path}: {err}", file=sys.stderr)
        return False


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("hyprland", "niri-outputs"):
        print(
            f"usage: {argv[0]} hyprland|niri-outputs <source-config> <output-config>",
            file=sys.stderr,
        )
        return 2

    mode, src, dst = argv[1], argv[2], argv[3]
    config = load_config(src)
    if config is None:
        return 1

    if mode == "hyprland":
        if isinstance(config, list):
            config = [convert_hyprland(bar) for bar in config]
        elif isinstance(config, dict):
            config = convert_hyprland(config)
        else:
            print("compositor-config: unexpected config structure", file=sys.stderr)
            return 1
    else:
        base = config[0] if isinstance(config, list) else config
        if not isinstance(base, dict):
            print("compositor-config: unexpected config structure", file=sys.stderr)
            return 1
        outputs = niri_outputs()
        if not outputs:
            print("compositor-config: no outputs found, not generating", file=sys.stderr)
            return 1
        config = generate_per_output(base, outputs)

    return 0 if write_config(dst, config) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
