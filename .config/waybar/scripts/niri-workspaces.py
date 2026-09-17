#!/usr/bin/env python3
"""waybar custom module: niri workspace pills.

Event-driven: instead of waybar polling us every second (spawning a Python
interpreter 86k times a day), this runs once as a long-lived process, follows
`niri msg event-stream`, and prints a new JSON line only when workspaces
actually change. Colors come from the global theme system
(~/.config/themes/active/palette.json) with Catppuccin fallbacks.

With --output NAME, only that output's workspaces are shown -- used when
waybar draws one bar per monitor (see launch.sh and compositor-config.py's
niri-outputs mode); without it, every workspace on every output is shown,
which is the previous single-bar behaviour.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time


def exit_when_orphaned():
    """Exit if our waybar parent dies.

    Waybar spawns custom-module execs via `sh -c`; when waybar restarts, those
    children are reparented to init and — because this script only writes on
    events — would otherwise linger forever. We find the waybar ancestor and
    quit as soon as it disappears.
    """
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


FALLBACK = {
    "bg": "#1e1e2e",
    "accent": "#cba6f7",
    "text": "#cdd6f4",
    "overlay": "#6c7086",
    "red": "#f38ba8",
}


def palette():
    try:
        with open(os.path.expanduser("~/.config/themes/active/palette.json")) as f:
            p = json.load(f)
        return {k: p.get(k, v) for k, v in FALLBACK.items()}
    except Exception:
        return FALLBACK


FOCUSED = "\u25cf"   # ● focused workspace
OCCUPIED = "\u2022"  # • holds windows
EMPTY = "\u00b7"     # · empty

# Short labels for the ten fixed-desk workspaces -- their full names ("agents",
# "term1") are fine in binds and window rules, but ten of them plus whatever
# empty scratch workspaces niri creates (empty-workspace-above-first, plus the
# trailing empty one niri always keeps) is enough text to overflow the bar
# when they all collapse onto one output (undocked, or before docking spreads
# them across three). Unknown names fall back to their first 4 characters,
# so a future workspace added without updating this map still degrades
# gracefully instead of blowing up the bar.
SHORT_NAMES = {
    "code": "code", "agents": "agt", "chat": "chat", "mail": "mail",
    "web1": "w1", "web2": "w2", "web3": "w3",
    "term1": "t1", "term2": "t2", "term3": "t3",
}


def is_empty_scratch(w):
    """An unnamed, unoccupied workspace with no claim on your attention --
    the auto-created scratch space above/after the fixed desk. Showing these
    is pure noise unless you're actually on one right now."""
    return (
        not w.get("name")
        and w.get("active_window_id") is None
        and not w.get("is_focused")
        and not w.get("is_urgent")
    )


def render(workspaces, pal, output=None):
    if output:
        workspaces = [w for w in workspaces if w.get("output") == output]
    workspaces = [w for w in workspaces if not is_empty_scratch(w)]
    workspaces.sort(key=lambda w: ((w.get("output") or ""), w.get("idx") or 0))
    pills = []
    for w in workspaces:
        name = w.get("name")
        label = SHORT_NAMES.get(name, name[:4]) if name else w.get("idx", "?")
        if w.get("is_urgent"):
            pills.append(
                f"<span color='{pal['red']}' weight='bold'>{FOCUSED} {label}</span>"
            )
        elif w.get("is_focused"):
            pills.append(
                f"<span color='{pal['accent']}' weight='bold' size='large'>{FOCUSED} {label}</span>"
            )
        elif w.get("active_window_id") is not None:
            pills.append(f"<span color='{pal['text']}'>{OCCUPIED} {label}</span>")
        else:
            pills.append(f"<span color='{pal['overlay']}'>{EMPTY} {label}</span>")
    return "  ".join(pills)


def emit(text, last):
    if text != last[0]:
        print(json.dumps({"text": text, "tooltip": ""}), flush=True)
        last[0] = text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="only show this output's workspaces")
    args = parser.parse_args()

    exit_when_orphaned()
    last = [None]
    proc = subprocess.Popen(
        ["niri", "msg", "-j", "event-stream"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    workspaces = []
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if "WorkspacesChanged" in ev:
            workspaces = ev["WorkspacesChanged"]["workspaces"]
        elif "WorkspaceActivated" in ev:
            wid = ev["WorkspaceActivated"]["id"]
            focused = ev["WorkspaceActivated"]["focused"]
            output = next((w.get("output") for w in workspaces if w["id"] == wid), None)
            for w in workspaces:
                if w.get("output") == output:
                    w["is_active"] = w["id"] == wid
                if focused:
                    w["is_focused"] = w["id"] == wid
        elif "WorkspaceUrgencyChanged" in ev:
            wid = ev["WorkspaceUrgencyChanged"]["id"]
            for w in workspaces:
                if w["id"] == wid:
                    w["is_urgent"] = ev["WorkspaceUrgencyChanged"]["urgent"]
        elif "WorkspaceActiveWindowChanged" in ev:
            wid = ev["WorkspaceActiveWindowChanged"]["workspace_id"]
            for w in workspaces:
                if w["id"] == wid:
                    w["active_window_id"] = ev["WorkspaceActiveWindowChanged"]["active_window_id"]
        else:
            continue
        emit(render(list(workspaces), palette(), args.output), last)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"text": ""}), flush=True)
        sys.exit(0)
