#!/usr/bin/env python3
"""Run a vintage xscreensaver hack on EVERY monitor while the session is idle.

WHY THIS EXISTS
---------------
You cannot draw animation on top of a Wayland lock screen. Under the
ext-session-lock protocol the compositor renders ONLY the lock surface while
locked -- niri explicitly skips windows and layer-shell surfaces in that state
(src/niri.rs, the `is_locked()` branch of `surface_under_and_output`). So the
xscreensaver model of "pretty animation that is also the lock" has no direct
equivalent; the lock client itself has to do the drawing.

What you CAN have is the other half of xscreensaver's behaviour: a screensaver
that kicks in when you go idle, and a real lock once you have been away long
enough. swayidle drives that:

    idle 10 min  -> this script starts one hack per monitor, fullscreen
    any input    -> this script kills them, you are back where you were
    idle 45 min  -> the hacks are stopped and the screen locks for real

MULTI-MONITOR
-------------
The hacks are X11 programs running through xwayland-satellite, and they have no
idea what a Wayland output is. A niri window rule fullscreens them (matching on
TITLE, because each hack sets its own app-id from its name), but placement has
to be done afterwards over IPC: this script waits for each window to appear and
then moves it to its intended output with

    niri msg action move-window-to-monitor --id <id> <output>

USAGE
    lock-screensaver.py start        one hack per connected monitor
    lock-screensaver.py stop         stop all of them
    lock-screensaver.py list         show installed hacks and the shortlist
    lock-screensaver.py test NAME    run one hack, to audition it
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time

HACK_DIR = "/usr/libexec/xscreensaver"
DISPLAY_NUM = ":12"
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PIDFILE = os.path.join(RUNTIME, "lock-screensaver.pids")

# Vintage shortlist. These are chosen for period feel rather than novelty --
# several are direct descendants of the demos that shipped on the workstations
# the wallpaper is advertising:
#
#   atlantis     SGI's own GL demo (the sharks), IRIX
#   sproingies   SGI IRIX demo, the bouncing pyramid critters
#   pipes        the Windows 95 3D Pipes saver
#   flyingtoasters  After Dark, 1989
#   lament       the Hellraiser puzzle box
#   gears, pulsar, superquadrics, morph3d, moebius, cage, bubble3d, glplanet
#                early Mesa/GLX demos of the same era
#   galaxy, ifs, flow, attraction, hopalong, qix, pyro, rocks, juggler3d
#                classic 2D X11 hacks from the original xscreensaver
#   phosphor, apple2, xanalogtv, xmatrix, decayscreen, slidescreen
#                CRT/terminal nostalgia
#
# Anything in HACK_DIR works; edit freely. Names that aren't installed are
# skipped, and `list` calls them out rather than silently dropping them.
VINTAGE = [
    "atlantis",
    "sproingies",
    "pipes",
    "flyingtoasters",
    "lament",
    "gears",
    "pulsar",
    "superquadrics",
    "morph3d",
    "moebius",
    "cage",
    "bubble3d",
    "glplanet",
    "stonerview",
    "galaxy",
    "ifs",
    "flow",
    "attraction",
    "hopalong",
    "qix",
    "pyro",
    "rocks",
    "juggler3d",
    "phosphor",
    "apple2",
    "xanalogtv",
    "xmatrix",
    "decayscreen",
    "slidescreen",
]

# Hacks that read the screen contents and mangle them. They look like a broken
# monitor rather than a screensaver when there is nothing behind them, and on
# Wayland they cannot see the real desktop anyway, so they are never chosen
# automatically -- `test` still runs them if you ask.
SCREEN_GRABBERS = {"decayscreen", "slidescreen", "xanalogtv"}


def installed_hacks() -> list[str]:
    try:
        return sorted(
            name
            for name in os.listdir(HACK_DIR)
            if os.access(os.path.join(HACK_DIR, name), os.X_OK)
            and not name.startswith("xscreensaver-")
        )
    except OSError:
        return []


def niri_json(*args: str):
    try:
        out = subprocess.run(
            ["niri", "msg", "--json", *args],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def niri_action(*args: str) -> None:
    try:
        subprocess.run(
            ["niri", "msg", "action", *args],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def outputs() -> list[str]:
    data = niri_json("outputs")
    return sorted(data.keys()) if data else []


def read_pids() -> list[int]:
    try:
        with open(PIDFILE) as fh:
            pids = [int(line.strip()) for line in fh if line.strip()]
    except (OSError, ValueError):
        return []
    return [p for p in pids if os.path.exists(f"/proc/{p}")]


def write_pids(pids: list[int]) -> None:
    with open(PIDFILE, "w") as fh:
        fh.write("\n".join(str(p) for p in pids) + "\n")


def ensure_xwayland() -> bool:
    """Make sure a rootless XWayland is up on DISPLAY_NUM."""
    socket = f"/tmp/.X11-unix/X{DISPLAY_NUM.lstrip(':')}"
    if os.path.exists(socket):
        return True

    if not shutil.which("xwayland-satellite"):
        print("xwayland-satellite is not installed", file=sys.stderr)
        return False

    subprocess.Popen(
        ["xwayland-satellite", DISPLAY_NUM],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(50):
        if os.path.exists(socket):
            return True
        time.sleep(0.1)
    print("timed out waiting for xwayland-satellite", file=sys.stderr)
    return False


def screensaver_window_ids() -> dict[int, str]:
    """Map window id -> app_id for every xscreensaver window currently open."""
    data = niri_json("windows") or []
    found = {}
    for w in data:
        if "from the XScreenSaver" in (w.get("title") or ""):
            found[w["id"]] = w.get("app_id") or ""
    return found


def spawn(hack: str) -> int | None:
    env = dict(os.environ, DISPLAY=DISPLAY_NUM)
    try:
        # -window, not -root: rootless XWayland has no root window to draw on.
        proc = subprocess.Popen(
            [os.path.join(HACK_DIR, hack), "-window"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as err:
        print(f"failed to start {hack}: {err}", file=sys.stderr)
        return None
    return proc.pid


def stop() -> int:
    for pid in read_pids():
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    try:
        os.unlink(PIDFILE)
    except OSError:
        pass
    return 0


def start(only: str | None = None) -> int:
    if read_pids():
        return 0  # already running; don't stack them

    available = set(installed_hacks())
    if only:
        if only not in available:
            print(f"no such hack: {only}", file=sys.stderr)
            return 1
        pool = [only]
    else:
        pool = [h for h in VINTAGE if h in available and h not in SCREEN_GRABBERS]
        if not pool:
            print(f"no hacks from the shortlist found in {HACK_DIR}",
                  file=sys.stderr)
            return 1

    if not ensure_xwayland():
        return 1

    screens = outputs() or ["<none>"]
    # A different hack per screen where possible, so three monitors don't all
    # show the same thing. random.sample needs the pool to be at least as long
    # as the number of screens; fall back to independent choices if not.
    if only:
        picks = [only] * len(screens)
    elif len(pool) >= len(screens):
        picks = random.sample(pool, len(screens))
    else:
        picks = [random.choice(pool) for _ in screens]

    # Note which screensaver windows already exist (e.g. the manually toggled
    # atlantis) so they aren't mistaken for the ones started here.
    before = set(screensaver_window_ids())

    pids = []
    placements = []
    for screen, hack in zip(screens, picks):
        pid = spawn(hack)
        if pid is None:
            continue
        pids.append(pid)
        placements.append((screen, hack))
        # Start them one at a time: each new window has to be identified before
        # the next appears, otherwise there is no way to tell which is which.
        deadline = time.time() + 5
        new_id = None
        while time.time() < deadline:
            current = screensaver_window_ids()
            fresh = set(current) - before
            if fresh:
                new_id = max(fresh)
                before |= fresh
                break
            time.sleep(0.15)

        if new_id is not None and screen != "<none>":
            niri_action("move-window-to-monitor", "--id", str(new_id), screen)

    if not pids:
        return 1

    write_pids(pids)
    for screen, hack in placements:
        print(f"{hack} -> {screen}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="one hack per monitor (no-op if running)")
    sub.add_parser("stop", help="stop all running hacks")
    sub.add_parser("list", help="list installed hacks and the shortlist")
    t = sub.add_parser("test", help="run one hack by name on every monitor")
    t.add_argument("name")
    args = ap.parse_args()

    if args.cmd == "stop":
        return stop()
    if args.cmd == "start":
        return start()
    if args.cmd == "test":
        stop()
        return start(args.name)

    available = installed_hacks()
    print(f"{len(available)} hacks in {HACK_DIR}")
    print(f"outputs: {', '.join(outputs()) or '(niri not running)'}\n")

    picks = [h for h in VINTAGE if h in available and h not in SCREEN_GRABBERS]
    missing = [h for h in VINTAGE if h not in available]
    skipped = [h for h in VINTAGE if h in available and h in SCREEN_GRABBERS]

    print("vintage shortlist used by `start`:")
    for name in picks:
        print(f"  {name}")
    if skipped:
        print("\ninstalled but never auto-selected (they mangle screen "
              "contents, which\ndoesn't exist behind them on Wayland) -- "
              "`test` still runs them:")
        for name in skipped:
            print(f"  {name}")
    if missing:
        print("\nin the shortlist but NOT installed:")
        for name in missing:
            print(f"  {name}")
    print(f"\nall installed: {', '.join(available)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ---------------------------------------------------------------------------
# Wiring it into swayidle
# ---------------------------------------------------------------------------
#
# See the swayidle line in ~/.config/niri/config.kdl. The `resume` after the
# screensaver timeout is what dismisses the hacks on any input, and the `stop`
# in front of the lock matters: the hacks are ordinary windows, and leaving
# them running under the lock wastes a GPU for nothing, since the compositor
# will not render them while locked.
