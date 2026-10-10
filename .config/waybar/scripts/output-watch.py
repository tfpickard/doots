#!/usr/bin/env python3
"""Restart waybar when the set of connected outputs changes.

niri's IPC has no OutputsChanged event, so this infers a change from
WorkspacesChanged instead: a workspace's "output" field only changes when
outputs are added or removed, so watching the set of distinct outputs across
all workspaces is a reliable proxy. (This assumes at least one workspace
exists per connected output, which is always true -- niri creates one.)

Debounced by 1s: docking fires a burst of workspace-reassignment events as
each monitor comes up, and relaunching waybar on every one of them would be
wasteful and briefly flash the bar several times in a row.

Deliberately a separate long-lived process, not folded into launch.sh:
launch.sh restarts waybar (and would restart this if it lived there), so a
self-spawned watcher started from inside it would multiply on every restart
instead of running once for the session.
"""
import json
import subprocess
import sys
import threading
import time

LAUNCH_SH = "/home/tom/.config/waybar/launch.sh"
DEBOUNCE_SECONDS = 1.0


def current_outputs() -> set[str]:
    try:
        proc = subprocess.run(
            ["niri", "msg", "-j", "outputs"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return set(json.loads(proc.stdout))
    except Exception:
        return set()


def main() -> None:
    known = current_outputs()
    timer: threading.Timer | None = None

    def relaunch():
        print(f"waybar-output-watch: outputs now {sorted(known)}, relaunching",
              file=sys.stderr, flush=True)
        subprocess.Popen([LAUNCH_SH], start_new_session=True)

    proc = subprocess.Popen(
        ["niri", "msg", "-j", "event-stream"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if "WorkspacesChanged" not in ev:
            continue

        seen = {w["output"] for w in ev["WorkspacesChanged"]["workspaces"] if w.get("output")}
        if seen == known:
            continue
        known = seen

        if timer is not None:
            timer.cancel()
        timer = threading.Timer(DEBOUNCE_SECONDS, relaunch)
        timer.daemon = True
        timer.start()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(f"waybar-output-watch: {err}", file=sys.stderr)
        sys.exit(1)
