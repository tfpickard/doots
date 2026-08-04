#!/usr/bin/env python3
"""Run an xscreensaver hack as an idle screensaver, then hand over to the lock.

WHY THIS EXISTS
---------------
You cannot draw animation on top of a Wayland lock screen. Under the
ext-session-lock protocol the compositor renders ONLY the lock surface while
locked -- niri explicitly skips windows and layer-shell surfaces in that state
(src/niri.rs, the `is_locked()` branch of `surface_under_and_output`). So the
xscreensaver model of "pretty animation that is also the lock" has no direct
equivalent; the lock client itself has to do the drawing.

What you CAN have is the other half of xscreensaver's behaviour: a screensaver
that kicks in when you go idle, and a real lock that takes over once you have
been away long enough. That is what this does, driven by swayidle:

    idle 5 min   -> this script starts a random GL hack, fullscreen
    any input    -> this script kills it, you are back where you were
    idle 10 min  -> swaylock locks for real (the hack is killed first)

The hacks are X11 programs, so they run through xwayland-satellite, the same
rootless XWayland that the existing toggle-atlantis.sh uses.

USAGE
    lock-screensaver.py start     # start a random hack (idempotent)
    lock-screensaver.py stop      # stop any running hack
    lock-screensaver.py list      # list the hacks that are actually installed
    lock-screensaver.py test NAME # run one hack by name, to audition it

Wire it up in the niri config's swayidle line -- see the comment at the bottom.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import signal
import subprocess
import sys
import time

HACK_DIR = "/usr/libexec/xscreensaver"
DISPLAY_NUM = ":12"
PIDFILE = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "lock-screensaver.pid"
)

# A curated shortlist rather than all 258 hacks: these are the ones that look
# good fullscreen on a modern panel, don't flash white, and don't peg a CPU
# core. Add or remove freely -- anything in HACK_DIR works.
FAVOURITES = [
    "atlantis",      # the one already wired to Mod+Ctrl+Z
    "flurry",        # slow, colourful particle streams
    "wormhole",      # starfield flying through a wormhole
    "glmatrix",      # the Matrix code rain, in 3D
    "cube21",        # rotating puzzle cube
    "endgame",       # chess endgames, plays itself
    "fliptext",      # text tumbling in 3D
    "galaxy",        # colliding galaxies
    "hypertorus",    # 4D torus projection
    "lavalite",      # lava lamp
    "pipes",         # the 3D pipes screensaver
    "starwars",      # scrolling opening crawl
    "surfaces",      # parametric surfaces
    "unknownpleasures",  # the Joy Division album cover, animated
    "hextrail",      # hexagonal growth patterns
    "cityflow",      # flying over a city grid
]


def installed_hacks() -> list[str]:
    try:
        return sorted(
            name
            for name in os.listdir(HACK_DIR)
            if os.access(os.path.join(HACK_DIR, name), os.X_OK)
        )
    except OSError:
        return []


def read_pid() -> int | None:
    try:
        with open(PIDFILE) as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return None
    # Only report it if it's actually still alive.
    return pid if os.path.exists(f"/proc/{pid}") else None


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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(50):
        if os.path.exists(socket):
            return True
        time.sleep(0.1)
    print("timed out waiting for xwayland-satellite", file=sys.stderr)
    return False


def stop() -> int:
    pid = read_pid()
    if pid:
        try:
            # The hack is started in its own session, so signal the group to
            # be sure nothing is left behind.
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


def start(hack: str | None = None) -> int:
    if read_pid():
        return 0  # already running; don't stack them

    available = set(installed_hacks())
    if hack:
        if hack not in available:
            print(f"no such hack: {hack}", file=sys.stderr)
            return 1
        choice = hack
    else:
        pool = [h for h in FAVOURITES if h in available] or sorted(available)
        if not pool:
            print(f"no hacks found in {HACK_DIR}", file=sys.stderr)
            return 1
        choice = random.choice(pool)

    if not ensure_xwayland():
        return 1

    env = dict(os.environ, DISPLAY=DISPLAY_NUM)
    # -window, not -root: rootless XWayland has no root window to draw on.
    proc = subprocess.Popen(
        [os.path.join(HACK_DIR, choice), "-window"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    with open(PIDFILE, "w") as fh:
        fh.write(str(proc.pid))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="start a random hack (no-op if one is running)")
    sub.add_parser("stop", help="stop the running hack")
    sub.add_parser("list", help="list installed hacks")
    t = sub.add_parser("test", help="run one hack by name")
    t.add_argument("name")
    args = ap.parse_args()

    if args.cmd == "stop":
        return stop()
    if args.cmd == "start":
        return start()
    if args.cmd == "test":
        stop()
        return start(args.name)
    if args.cmd == "list":
        available = installed_hacks()
        print(f"{len(available)} hacks in {HACK_DIR}\n")
        picks = [h for h in FAVOURITES if h in available]
        missing = [h for h in FAVOURITES if h not in available]
        print("shortlist used by `start` (edit FAVOURITES in this file):")
        for name in picks:
            print(f"  {name}")
        if missing:
            print("\nin FAVOURITES but NOT installed (silently skipped):")
            for name in missing:
                print(f"  {name}")
        print(f"\nall installed: {', '.join(available)}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

# ---------------------------------------------------------------------------
# Wiring it into swayidle
# ---------------------------------------------------------------------------
#
# Replace the swayidle line in ~/.config/niri/config.kdl with a version that
# has a screensaver stage before the lock stage. Note the `resume` for the
# screensaver timeout, which is what dismisses the hack on any input:
#
#   spawn-sh-at-startup "swayidle -w \
#       timeout 300  '~/.config/scripts/lock-screensaver.py start' \
#            resume  '~/.config/scripts/lock-screensaver.py stop' \
#       timeout 600  '~/.config/scripts/lock-screensaver.py stop; swaylock -f' \
#       timeout 900  '~/.config/scripts/idle-dpms.sh off' \
#            resume  '~/.config/scripts/idle-dpms.sh on' \
#       before-sleep 'swaylock -f'"
#
# The `stop` in front of swaylock matters: the hack is an ordinary window, and
# leaving it running under the lock wastes a GPU for nothing, since the
# compositor won't render it while locked.
