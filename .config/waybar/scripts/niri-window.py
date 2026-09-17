#!/usr/bin/env python3
"""waybar custom module: focused niri window title (event-driven).

Long-lived process following `niri msg event-stream`; emits JSON only when
the relevant window changes. Replaces the hyprland/window module lost in the
Hyprland -> niri migration.

Without --output: the globally focused window, wherever it is. This is the
original single-bar behaviour.

With --output NAME: *that output's* active window -- the active window of
whichever workspace is currently active on that output -- which is not
necessarily the globally focused window. This is what makes per-output bars
(see launch.sh and compositor-config.py's niri-outputs mode) show three
different titles instead of the same one three times: each bar asks about
its own output's own workspace, tracked the same way niri-workspaces.py
tracks is_active per output.
"""
import argparse
import html
import json
import os
import subprocess
import sys
import threading
import time

MAX_LEN = 34


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


def resolve_title(windows, window_id):
    if window_id is None:
        return ""
    w = windows.get(window_id)
    if not w:
        return ""
    return w.get("title") or w.get("app_id") or ""


def truncate(title):
    if len(title) > MAX_LEN:
        return title[: MAX_LEN - 1] + "…"
    return title


def emit(title, last):
    title = truncate(title)
    if title != last[0]:
        print(json.dumps({"text": html.escape(title), "tooltip": ""}), flush=True)
        last[0] = title


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        help="show this output's active window instead of the globally focused one",
    )
    args = parser.parse_args()

    exit_when_orphaned()
    last = [None]
    proc = subprocess.Popen(
        ["niri", "msg", "-j", "event-stream"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )

    windows = {}
    focused = None          # globally focused window id (no --output)
    workspaces = {}         # id -> workspace dict (--output mode only)

    def title_for_output(output):
        ws = next(
            (w for w in workspaces.values()
             if w.get("output") == output and w.get("is_active")),
            None,
        )
        if ws is None:
            return ""
        return resolve_title(windows, ws.get("active_window_id"))

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
        elif "WorkspacesChanged" in ev:
            workspaces = {w["id"]: w for w in ev["WorkspacesChanged"]["workspaces"]}
        elif "WorkspaceActivated" in ev:
            wid = ev["WorkspaceActivated"]["id"]
            output = workspaces.get(wid, {}).get("output")
            for w in workspaces.values():
                if w.get("output") == output:
                    w["is_active"] = w["id"] == wid
        elif "WorkspaceActiveWindowChanged" in ev:
            wid = ev["WorkspaceActiveWindowChanged"]["workspace_id"]
            if wid in workspaces:
                workspaces[wid]["active_window_id"] = ev["WorkspaceActiveWindowChanged"]["active_window_id"]
        else:
            continue

        if args.output:
            emit(title_for_output(args.output), last)
        else:
            emit(resolve_title(windows, focused), last)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"text": ""}), flush=True)
        sys.exit(0)
