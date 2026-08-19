#!/usr/bin/env python3
"""waybar custom module: focused niri window title (event-driven).

Long-lived process following `niri msg event-stream`; emits JSON only when
the focused window changes. Replaces the hyprland/window module lost in the
Hyprland -> niri migration.
"""
import html
import json
import os
import subprocess
import sys
import threading
import time

MAX_LEN = 60


def exit_when_orphaned():
    """Exit if our waybar parent dies (see niri-workspaces.py for rationale)."""
    def ppid(pid):
        try:
            with open(f"/proc/{pid}/stat") as f:
                d = f.read()
            return int(d[d.rfind(")") + 2:].split()[1])
        except Exception:
            return 0

    def comm(pid):
        try:
            with open(f"/proc/{pid}/comm") as f:
                return f.read().strip()
        except Exception:
            return ""

    target, pid = 0, os.getpid()
    for _ in range(8):
        pid = ppid(pid)
        if pid <= 1:
            break
        target = pid
        if comm(pid) == "waybar":
            break
    if not target:
        return

    def loop():
        while os.path.exists(f"/proc/{target}"):
            time.sleep(4)
        os._exit(0)

    threading.Thread(target=loop, daemon=True).start()


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
    exit_when_orphaned()
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
