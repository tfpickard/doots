#!/usr/bin/env python3
"""waybar custom module: focused niri window title (event-driven).

Long-lived process following `niri msg event-stream`; emits JSON only when
the focused window changes. Replaces the hyprland/window module lost in the
Hyprland -> niri migration.
"""
import html
import json
import subprocess
import sys

MAX_LEN = 60


def emit(windows, focused_id, last):
    title = ""
    if focused_id is not None:
        w = windows.get(focused_id)
        if w:
            title = w.get("title") or w.get("app_id") or ""
    if len(title) > MAX_LEN:
        title = title[: MAX_LEN - 1] + "…"
    if title != last[0]:
        print(json.dumps({"text": html.escape(title), "tooltip": ""}), flush=True)
        last[0] = title


def main():
    last = [None]
    proc = subprocess.Popen(
        ["niri", "msg", "-j", "event-stream"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    windows = {}
    focused = None
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if "WindowsChanged" in ev:
            windows = {w["id"]: w for w in ev["WindowsChanged"]["windows"]}
            focused = next((w["id"] for w in windows.values() if w.get("is_focused")), None)
        elif "WindowOpenedOrChanged" in ev:
            w = ev["WindowOpenedOrChanged"]["window"]
            windows[w["id"]] = w
            if w.get("is_focused"):
                focused = w["id"]
        elif "WindowClosed" in ev:
            wid = ev["WindowClosed"]["id"]
            windows.pop(wid, None)
            if focused == wid:
                focused = None
        elif "WindowFocusChanged" in ev:
            focused = ev["WindowFocusChanged"]["id"]
        else:
            continue
        emit(windows, focused, last)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"text": ""}), flush=True)
        sys.exit(0)
