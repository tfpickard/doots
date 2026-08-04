#!/usr/bin/env python3
"""Show input devices and how niri classifies them.

niri does not expose input devices over IPC (`niri msg` has no `inputs`
command), which makes "why isn't my mouse/trackball setting applying?" hard to
answer. This reproduces niri's own classification logic so you can see exactly
which config block governs each device.

niri decides using src/input/mod.rs::apply_libinput_settings:

    is_touchpad   = libinput tap finger count > 0
    is_trackball  = udev property ID_INPUT_TRACKBALL is set
    is_trackpoint = udev property ID_INPUT_POINTINGSTICK is set
    is_mouse      = has pointer capability AND none of the above

So a device is governed by `mouse { }` unless udev *tags* it otherwise. Many
Bluetooth/USB trackballs are only tagged ID_INPUT_MOUSE, which is why their
`trackball { }` block silently does nothing.

Usage:
    niri-inputs.py            # summary table
    niri-inputs.py -v         # add udev properties and libinput settings

Reading /dev/input/* requires membership of the `input` group (or root); without
it the libinput columns are shown as "?" and everything else still works.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

DEVICES_FILE = "/proc/bus/input/devices"

# Config block -> the niri section that governs the device.
BLOCK_TOUCHPAD = "touchpad"
BLOCK_TRACKBALL = "trackball"
BLOCK_TRACKPOINT = "trackpoint"
BLOCK_MOUSE = "mouse"
BLOCK_KEYBOARD = "keyboard"
BLOCK_NONE = "-"

REL_WHEEL_BIT = 8


class Device:
    def __init__(self, name: str, handlers: str, rel: int, is_key: bool):
        self.name = name
        self.handlers = handlers
        self.rel = rel
        self.is_key = is_key
        self.event = next(
            (h for h in handlers.split() if h.startswith("event")), ""
        )
        self.props: dict[str, str] = {}

    @property
    def node(self) -> str:
        return f"/dev/input/{self.event}" if self.event else ""

    @property
    def has_pointer(self) -> bool:
        # libinput reports the pointer capability for anything with relative
        # X/Y motion; udev's ID_INPUT_MOUSE tracks the same idea.
        return bool(self.rel & 0b11) or "ID_INPUT_MOUSE" in self.props

    @property
    def has_wheel(self) -> bool:
        return bool(self.rel >> REL_WHEEL_BIT & 1)

    def block(self, tap_finger_counts: dict[str, int]) -> str:
        """Which niri config block applies, using niri's own precedence."""
        if tap_finger_counts.get(self.event, 0) > 0:
            return BLOCK_TOUCHPAD
        if "ID_INPUT_TRACKBALL" in self.props:
            return BLOCK_TRACKBALL
        if "ID_INPUT_POINTINGSTICK" in self.props:
            return BLOCK_TRACKPOINT
        if self.has_pointer:
            return BLOCK_MOUSE
        if self.is_key or "ID_INPUT_KEYBOARD" in self.props:
            return BLOCK_KEYBOARD
        return BLOCK_NONE


def parse_devices() -> list[Device]:
    try:
        raw = open(DEVICES_FILE, encoding="utf-8", errors="replace").read()
    except OSError as err:
        sys.exit(f"cannot read {DEVICES_FILE}: {err}")

    devices = []
    for block in raw.split("\n\n"):
        name = re.search(r'N: Name="([^"]*)"', block)
        handlers = re.search(r"H: Handlers=(.*)", block)
        if not name or not handlers:
            continue
        rel = re.search(r"B: REL=([0-9a-fA-F]+)", block)
        devices.append(
            Device(
                name=name.group(1).strip(),
                handlers=handlers.group(1).strip(),
                rel=int(rel.group(1), 16) if rel else 0,
                is_key=bool(re.search(r"B: KEY=", block)),
            )
        )
    return devices


def load_udev(devices: list[Device]) -> None:
    """Attach ID_INPUT_* udev properties. These are what niri actually reads."""
    if not shutil.which("udevadm"):
        return
    for dev in devices:
        if not dev.node:
            continue
        try:
            out = subprocess.run(
                ["udevadm", "info", "--query=property", dev.node],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for line in out.splitlines():
            key, _, value = line.partition("=")
            if key.startswith("ID_INPUT") or key in ("ID_BUS",):
                dev.props[key] = value


def load_libinput() -> tuple[dict[str, int], dict[str, dict[str, str]]]:
    """Parse `libinput list-devices` for tap finger count and settings.

    IMPORTANT: these are the *defaults libinput computes for a fresh context*,
    not the values niri currently has applied. libinput settings are per-context
    and niri does not expose its own. Use this to see what a device *supports*
    and what it looks like before configuration -- not as proof of niri's state.
    """
    taps: dict[str, int] = {}
    settings: dict[str, dict[str, str]] = {}
    if not shutil.which("libinput"):
        return taps, settings
    try:
        out = subprocess.run(
            ["libinput", "list-devices"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return taps, settings

    for chunk in out.split("\n\n"):
        kernel = re.search(r"Kernel:\s+(\S+)", chunk)
        if not kernel:
            continue
        event = os.path.basename(kernel.group(1))
        fields = {}
        for key in ("Nat.scrolling", "Middle emulation", "Scroll methods",
                    "Scroll button", "Tap-to-click", "Accel profiles",
                    "Capabilities", "Left-handed"):
            m = re.search(rf"^{re.escape(key)}:\s*(.*)$", chunk, re.M)
            if m:
                fields[key] = m.group(1).strip()
        settings[event] = fields
        # libinput prints "Tap-to-click: n/a" for devices with no tap support;
        # anything else means a finger count > 0, i.e. niri sees a touchpad.
        tap = fields.get("Tap-to-click", "n/a")
        taps[event] = 0 if tap in ("n/a", "") else 1
    return taps, settings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Show input devices and the niri config block that governs each."
    )
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="also show udev ID_INPUT_* properties and libinput settings")
    ap.add_argument("-a", "--all", action="store_true",
                    help="include devices that are neither pointers nor keyboards")
    args = ap.parse_args()

    devices = parse_devices()
    load_udev(devices)
    taps, settings = load_libinput()
    have_libinput = bool(settings)

    rows = []
    for dev in devices:
        block = dev.block(taps)
        if not args.all and block in (BLOCK_NONE,):
            continue
        if not args.all and block == BLOCK_KEYBOARD and not dev.has_pointer:
            # Keyboards are listed, but skip the pile of ACPI/HDMI pseudo-inputs.
            if not any(k.startswith("ID_INPUT_KEY") for k in dev.props):
                continue
        rows.append((dev, block))

    name_w = max([len(d.name) for d, _ in rows] + [6])
    print(f"{'DEVICE'.ljust(name_w)}  {'EVENT':<8} {'NIRI BLOCK':<11} "
          f"{'WHEEL':<6} {'NAT.SCROLL*':<12} BUS")
    print("-" * (name_w + 50))
    for dev, block in rows:
        s = settings.get(dev.event, {})
        nat = s.get("Nat.scrolling", "?" if not have_libinput else "n/a")
        print(f"{dev.name.ljust(name_w)}  {dev.event:<8} {block:<11} "
              f"{'yes' if dev.has_wheel else '-':<6} {nat:<12} "
              f"{dev.props.get('ID_BUS', '-')}")

    print("\n* Nat.scrolling is libinput's DEFAULT for a fresh context, not the "
          "value niri\n  currently has applied -- libinput settings are "
          "per-context and niri does not\n  expose its own. Trust the niri "
          "config block column to know which settings win.")
    print("\n  Direction, stated physically (the word 'natural' causes endless "
          "confusion):\n    natural-scroll OFF -> wheel up moves content DOWN "
          "(traditional wheel)\n    natural-scroll ON  -> wheel up moves content "
          "UP   (touchscreen-like)")

    if args.verbose:
        for dev, block in rows:
            print(f"\n=== {dev.name}  [{dev.event}]")
            print(f"    niri block : {block} {{ }}")
            print(f"    handlers   : {dev.handlers}")
            tags = {k: v for k, v in dev.props.items() if k.startswith("ID_INPUT")}
            print(f"    udev tags  : {', '.join(sorted(tags)) or '(none)'}")
            for key, value in sorted(settings.get(dev.event, {}).items()):
                print(f"    {key:<17}: {value}")

    if not have_libinput:
        print("\nNote: could not read libinput device info (needs the 'input' "
              "group or root).\n      Re-run with sudo for the full picture.")

    # Show which config blocks actually govern something. A block with no
    # devices is dead config -- this is the usual reason a `trackball { }` or
    # `trackpoint { }` section appears to be ignored.
    print("\nConfig block coverage:")
    for block in (BLOCK_TOUCHPAD, BLOCK_MOUSE, BLOCK_TRACKBALL, BLOCK_TRACKPOINT):
        owned = [d.name for d, b in rows if b == block]
        if owned:
            print(f"  {block + ' { }':<14} -> {', '.join(owned)}")
        else:
            print(f"  {block + ' { }':<14} -> (no devices: this block does nothing)")

    if not any(b == BLOCK_TRACKBALL for _, b in rows):
        print("\nIf you have a trackball, udev is not tagging it "
              "ID_INPUT_TRACKBALL, so niri treats\nit as a plain mouse. See "
              "etc/udev/rules.d/71-trackball-tags.rules in the dotfiles repo.")

    print("\nNote: niri reads these udev tags when a device is ADDED. After "
          "changing a udev\nrule, reconnect the device (or restart niri) -- a "
          "config reload alone will not\nreclassify an already-connected device.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
