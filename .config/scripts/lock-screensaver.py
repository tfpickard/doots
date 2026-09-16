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

CYCLING, AND "ANY KEY BUT THIS ONE"
-----------------------------------
There is no `xscreensaver` daemon here to talk to with `xscreensaver-command
-next`: these are the bare hacks, run directly on a rootless XWayland. So
"switch to the next animation" means killing what is on screen and starting the
next set, which is what `shuffle`/`next`/`prev` do.

The hard part is doing that WITHOUT dismissing the screensaver, because the
keypress asking for it is input, and input is exactly what tells swayidle you
are back. Both halves therefore go through this script:

    the cycle keys  ->  `shuffle` (etc), which first records a request
    swayidle resume ->  `wake`, which pauses briefly, sees that request, and
                        leaves the hacks up instead of stopping them

Any other key produces a `wake` with no request behind it, and stops the
screensaver as before. Once the screensaver is up, dismissal is driven by a
dedicated short-timeout swayidle (`watch`) started alongside the hacks, because
the main swayidle only fires `resume` once per idle period -- after the first
cycle it would be spent, and nothing would dismiss the screensaver at all.

USAGE
    lock-screensaver.py start        one hack per connected monitor
    lock-screensaver.py stop         stop all of them
    lock-screensaver.py shuffle      re-roll: a new random hack on every screen
    lock-screensaver.py next         ... or walk the shortlist in order
    lock-screensaver.py prev         ... backwards
    lock-screensaver.py wake         swayidle's resume hook (cycle, or stop)
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
SELF = os.path.realpath(__file__)
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PIDFILE = os.path.join(RUNTIME, "lock-screensaver.pids")
# Where `next`/`prev` are in the shortlist: the index of the hack showing on the
# first output. Kept out of the pidfile so the position survives a stop/start.
CYCLEFILE = os.path.join(RUNTIME, "lock-screensaver.cycle")
# What is on screen right now, one hack per line, in output order. `shuffle`
# reads it so a re-roll never hands you back the hack you just asked to change.
CURRENTFILE = os.path.join(RUNTIME, "lock-screensaver.current")
# "A cycle key was pressed." Written before the hacks are touched and refreshed
# as they come up; `wake` treats its presence as "leave the screensaver alone".
REQUESTFILE = os.path.join(RUNTIME, "lock-screensaver.request")
WATCHERFILE = os.path.join(RUNTIME, "lock-screensaver.watcher")

# How long `wake` waits for a cycle request to show up before concluding there
# isn't one and dismissing the screensaver. The keypress reaches niri's bind and
# swayidle's resume at the same moment and there is no ordering guarantee
# between them, so this is what makes the outcome independent of who wins:
# comfortably longer than a Python interpreter takes to start (~50ms), short
# enough not to feel like lag when you actually meant to dismiss it.
WAKE_GRACE = 0.35
# How long a request counts as fresh on its timestamp alone. This only has to
# cover the gap between the keybind firing and `wake` looking, so it is kept
# short: while a cycle is actually in progress the pid below is what marks it as
# pending, and anything longer would mean a key pressed just after a cycle
# failing to dismiss the screensaver.
REQUEST_TTL = 0.75
# Ceiling on the pid check, so a recycled pid can't leave a request pending for
# the rest of the session. Comfortably longer than the slowest possible cycle
# (one 5s window wait per screen).
REQUEST_MAX = 30.0

# Pressing a key to cycle also wakes swayidle. `wake` knows not to stop the
# hacks, but a swayidle still running the older `resume '... stop'` line (this
# session, before the config was reloaded) does not. That stop reads the pidfile,
# so the new hacks are safe as long as they are recorded after it has run; the
# settle gives it time to fire first.
RESUME_SETTLE = 0.5

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


def stray_hack_pids() -> list[int]:
    """Hacks running that this script did not start.

    The atlantis spawned at login and the one behind Mod+Ctrl+Z are ordinary
    processes with no pidfile entry. `stop` leaves them alone on purpose -- they
    are ambient decoration, not the screensaver -- but cycling has to clear them
    or the next hack simply stacks on top of them.
    """
    tracked = set(read_pids())
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in tracked:
            continue
        try:
            exe = os.path.realpath(os.readlink(f"/proc/{pid}/exe"))
        except OSError:
            continue  # gone, or not ours to look at
        if os.path.dirname(exe) == HACK_DIR:
            found.append(pid)
    return found


def kill_pids(pids: list[int], group: bool = True,
              sig: int = signal.SIGTERM) -> None:
    """Signal each pid, optionally the whole process group with it.

    Hacks this script starts get `start_new_session=True`, so their group holds
    nothing else and killing it is the reliable way to take down a hack that
    forked. Strays are the opposite case: an atlantis started by
    toggle-atlantis.sh sits in the group of whatever launched the script, so
    killing its group takes that shell (and its siblings) down with it. Those
    get a plain kill.
    """
    for pid in pids:
        if group:
            try:
                os.killpg(os.getpgid(pid), sig)
                continue
            except (OSError, ProcessLookupError):
                pass
        try:
            os.kill(pid, sig)
        except OSError:
            pass


def cycle_pool() -> list[str]:
    available = set(installed_hacks())
    return [h for h in VINTAGE if h in available and h not in SCREEN_GRABBERS]


def read_cycle() -> int:
    """Index into cycle_pool() of the hack on the first output, -1 if unset."""
    try:
        with open(CYCLEFILE) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return -1


def write_cycle(index: int) -> None:
    try:
        with open(CYCLEFILE, "w") as fh:
            fh.write(f"{index}\n")
    except OSError:
        pass


def read_current() -> list[str]:
    try:
        with open(CURRENTFILE) as fh:
            return [line.strip() for line in fh if line.strip()]
    except OSError:
        return []


def write_current(picks: list[str]) -> None:
    try:
        with open(CURRENTFILE, "w") as fh:
            fh.write("\n".join(picks) + "\n")
    except OSError:
        pass


def note_request() -> None:
    """Record 'a cycle key was pressed', for `wake` to find.

    The file holds the pid doing the cycling, which is what keeps a slow cycle
    -- three screens, a few seconds -- marked as in progress without having to
    guess a duration. A cycle that dies partway through stops counting as soon
    as its pid does, rather than wedging the screensaver permanently up.
    """
    try:
        with open(REQUESTFILE, "w") as fh:
            fh.write(f"{os.getpid()}\n")
    except OSError:
        pass


def request_pending() -> bool:
    try:
        age = time.time() - os.stat(REQUESTFILE).st_mtime
        with open(REQUESTFILE) as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return False
    if age < REQUEST_TTL:
        return True
    return (age < REQUEST_MAX and pid != os.getpid()
            and os.path.exists(f"/proc/{pid}"))


def clear_request() -> None:
    try:
        os.unlink(REQUESTFILE)
    except OSError:
        pass


def watcher_alive() -> bool:
    try:
        with open(WATCHERFILE) as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        return False
    return os.path.exists(f"/proc/{pid}")


def start_watcher() -> None:
    """Watch for the input that should dismiss the screensaver.

    The main swayidle cannot do this. It fires `resume` once when you come back
    from being idle, and then nothing again until the next full 10-minute
    timeout -- so the moment a cycle key is used (which is itself a resume) the
    screensaver would be up with no way left to dismiss it. A second swayidle
    with a 1-second timeout re-arms constantly: it goes idle a second after each
    cycle and fires `resume` on the very next input, whatever that input is.
    """
    if watcher_alive() or not shutil.which("swayidle"):
        return
    try:
        proc = subprocess.Popen(
            ["swayidle", "-w", "timeout", "1", "true", "resume", f"{SELF} wake"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return
    try:
        with open(WATCHERFILE, "w") as fh:
            fh.write(f"{proc.pid}\n")
    except OSError:
        pass


def stop_watcher() -> None:
    try:
        with open(WATCHERFILE) as fh:
            pid = int(fh.read().strip())
    except (OSError, ValueError):
        pid = None
    if pid is not None:
        # SIGKILL, not SIGTERM, and this is not paranoia: swayidle runs its
        # `resume` command on the way out if it happens to be idle at the time
        # -- which it always is here, since the screensaver only runs when you
        # are away. A polite SIGTERM therefore fires one last `wake`, seconds
        # later, at whatever is on screen by then; the symptom is a screensaver
        # that starts and instantly dies because the *previous* watcher's dying
        # gasp caught it. SIGKILL can't be handled, so nothing is run.
        #
        # The process, not its group: `wake` is normally run BY this watcher and
        # so shares its group, and killing the group would take the caller down
        # mid-stop -- leaving the watcher dead, the hacks alive and nothing left
        # to dismiss them.
        kill_pids([pid], group=False, sig=signal.SIGKILL)
    try:
        os.unlink(WATCHERFILE)
    except OSError:
        pass


X_SOCKET = f"/tmp/.X11-unix/X{DISPLAY_NUM.lstrip(':')}"


def ensure_xwayland() -> bool:
    """Make sure a rootless XWayland is up on DISPLAY_NUM."""
    if os.path.exists(X_SOCKET):
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
        if os.path.exists(X_SOCKET):
            return True
        time.sleep(0.1)
    print("timed out waiting for xwayland-satellite", file=sys.stderr)
    return False


def xwayland_pids() -> list[int]:
    """Every xwayland-satellite serving DISPLAY_NUM."""
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as fh:
                argv = fh.read().split(b"\0")
        except OSError:
            continue
        if (argv and argv[0].endswith(b"xwayland-satellite")
                and DISPLAY_NUM.encode() in argv):
            found.append(int(entry))
    return found


def restart_xwayland() -> bool:
    """Replace the X server on DISPLAY_NUM, however healthy it looks.

    The socket file is not proof of a working server. A long-lived
    xwayland-satellite can end up answering X queries -- xdpyinfo is perfectly
    happy -- while no window it is asked for ever makes it onto the screen, at
    which point every hack starts up, finds its window gone and exits 0 within a
    quarter of a second. The only reliable check is whether a hack actually
    survives, so that is what this is hung off: it is called when one doesn't.
    """
    kill_pids(xwayland_pids(), group=False)
    for _ in range(30):  # Xwayland removes the socket as it goes
        if not os.path.exists(X_SOCKET):
            break
        time.sleep(0.1)
    else:
        try:
            os.unlink(X_SOCKET)  # server gone but socket left behind
        except OSError:
            pass
    return ensure_xwayland()


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
    stop_watcher()
    kill_pids(read_pids())
    for path in (PIDFILE, CURRENTFILE):
        try:
            os.unlink(path)
        except OSError:
            pass
    return 0


def launch(picks: list[str], screens: list[str], watch: bool = True,
           retried: bool = False) -> int:
    """Spawn one hack per screen, place each on its output, record the pids."""
    if not ensure_xwayland():
        return 1

    # Note which screensaver windows already exist (e.g. the manually toggled
    # atlantis) so they aren't mistaken for the ones started here.
    before = set(screensaver_window_ids())

    pids = []
    placements = []
    for screen, hack in zip(screens, picks):
        pid = spawn(hack)
        if pid is None:
            continue
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
            if not os.path.exists(f"/proc/{pid}"):
                break  # gave up before it ever had a window
            time.sleep(0.15)

        if new_id is None and not os.path.exists(f"/proc/{pid}"):
            # A hack that dies before showing anything means the X server is
            # wedged, not that this particular hack is broken -- so replace the
            # server and try the whole set once more. Only worth doing for the
            # first one: if later hacks die, X is evidently fine.
            if not pids and not retried and restart_xwayland():
                return launch(picks, screens, watch, retried=True)
            print(f"{hack} exited immediately", file=sys.stderr)
            continue

        pids.append(pid)
        placements.append((screen, hack))
        if new_id is not None and screen != "<none>":
            niri_action("move-window-to-monitor", "--id", str(new_id), screen)

    if not pids:
        return 1

    write_pids(pids)
    write_current([hack for _, hack in placements])
    if watch:
        start_watcher()
    for screen, hack in placements:
        print(f"{hack} -> {screen}")
    return 0


def pick_random(pool: list[str], count: int, avoid: list[str]) -> list[str]:
    """A hack per screen, different from each other and from what's showing."""
    # A re-roll that hands back what you were already looking at reads as a key
    # that didn't work, so the current set is excluded -- unless doing that
    # would leave too few to fill the screens, in which case showing something
    # again beats showing nothing.
    fresh = [h for h in pool if h not in avoid]
    if len(fresh) >= count:
        pool = fresh
    if len(pool) >= count:
        return random.sample(pool, count)
    return [random.choice(pool) for _ in range(count)]


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
        pool = cycle_pool()
        if not pool:
            print(f"no hacks from the shortlist found in {HACK_DIR}",
                  file=sys.stderr)
            return 1

    screens = outputs() or ["<none>"]
    # A different hack per screen where possible, so three monitors don't all
    # show the same thing.
    picks = [only] * len(screens) if only else pick_random(pool, len(screens), [])

    # No dismiss-on-input watcher when auditioning a named hack: `test` is run
    # from a terminal, and a screensaver that vanishes the moment you type the
    # next command is not much use for looking at one.
    rc = launch(picks, screens, watch=not only)
    if rc == 0 and not only:
        # Leave the cycle where the random pick landed, so the first Mod+Ctrl+
        # Shift+Z after an idle screensaver moves on from what you're looking at
        # rather than jumping back to the top of the list.
        write_cycle(pool.index(picks[0]))
    return rc


def cycle(step: int | None) -> int:
    """Put different hacks up without taking the screensaver down.

    step None re-rolls at random; 1 and -1 walk the shortlist in order, a
    screen's worth at a time, so repeated presses eventually show you everything
    instead of the same few favourites.

    There is no daemon to ask for the next animation -- `xscreensaver-command
    -next` needs a running xscreensaver, and these are the bare hacks -- so this
    is kill-and-relaunch. Which makes the request marker the important part: the
    keypress that got us here is also waking swayidle, and `wake` has to be able
    to tell "they want a new animation" from "they want their desktop back"
    before it decides whether to stop the hacks.
    """
    note_request()

    pool = cycle_pool()
    if not pool:
        print(f"no hacks from the shortlist found in {HACK_DIR}",
              file=sys.stderr)
        clear_request()
        return 1

    screens = outputs() or ["<none>"]
    if step is None:
        picks = pick_random(pool, len(screens), read_current())
        index = pool.index(picks[0])
    else:
        span = min(len(screens), len(pool))  # how far one press moves the list
        current = read_cycle()
        index = 0 if step > 0 else -span
        if 0 <= current < len(pool):
            index = current + step * span
        index %= len(pool)
        picks = [pool[(index + n) % len(pool)] for n in range(len(screens))]

    running = read_pids()
    strays = stray_hack_pids()
    kill_pids(running)
    kill_pids(strays, group=False)
    try:
        os.unlink(PIDFILE)
    except OSError:
        pass
    if running or strays:
        # Also gives a legacy swayidle's `resume` -> `stop` (triggered by the
        # very keypress that got us here) time to run before the new pids are
        # written, so it can't kill the hacks we are about to start.
        time.sleep(RESUME_SETTLE)
        note_request()

    rc = launch(picks, screens)
    if rc == 0:
        write_cycle(index)
    else:
        clear_request()
    return rc


def wake() -> int:
    """swayidle's resume hook: dismiss the screensaver, unless it was a cycle.

    Every key produces one of these, including the cycle keys, so the marker is
    the only thing separating "I'm back" from "next animation, please". Waiting
    for it first is what makes the answer the same whether niri's bind or
    swayidle's resume happens to run first.
    """
    seen = read_pids()
    if not seen:
        return 0  # nothing up; nothing to dismiss
    time.sleep(WAKE_GRACE)
    if request_pending():
        return 0
    if read_pids() != seen:
        # Different hacks are up than the ones this wake was raised about, so
        # something restarted the screensaver while we waited. Stopping now
        # would kill a screensaver nobody asked to dismiss.
        return 0
    return stop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="one hack per monitor (no-op if running)")
    sub.add_parser("stop", help="stop all running hacks")
    sub.add_parser("shuffle", help="a new random hack on every screen")
    sub.add_parser("next", help="walk the shortlist forwards instead")
    sub.add_parser("prev", help="... backwards")
    sub.add_parser("wake", help="swayidle resume hook: cycle, or stop")
    sub.add_parser("list", help="list installed hacks and the shortlist")
    t = sub.add_parser("test", help="run one hack by name on every monitor")
    t.add_argument("name")
    args = ap.parse_args()

    if args.cmd == "stop":
        return stop()
    if args.cmd == "start":
        return start()
    if args.cmd == "shuffle":
        return cycle(None)
    if args.cmd == "next":
        return cycle(1)
    if args.cmd == "prev":
        return cycle(-1)
    if args.cmd == "wake":
        return wake()
    if args.cmd == "test":
        stop()
        return start(args.name)

    available = installed_hacks()
    print(f"{len(available)} hacks in {HACK_DIR}")
    print(f"outputs: {', '.join(outputs()) or '(niri not running)'}\n")

    picks = [h for h in VINTAGE if h in available and h not in SCREEN_GRABBERS]
    missing = [h for h in VINTAGE if h not in available]
    skipped = [h for h in VINTAGE if h in available and h in SCREEN_GRABBERS]
    position = read_cycle()

    print("vintage shortlist used by `start`, walked in order by `next`:")
    for i, name in enumerate(picks):
        print(f"  {'->' if i == position else '  '} {name}")
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
# Wiring it into swayidle, and into the keybinds
# ---------------------------------------------------------------------------
#
# See the swayidle line in ~/.config/niri/config.kdl. Its `resume` runs `wake`
# rather than `stop`, which is what lets one key mean "next animation" while
# every other key still means "I'm back" -- swayidle sees no difference between
# them, so the decision has to be made here.
#
# The `stop` in front of the lock (in lock.sh) matters for a different reason:
# the hacks are ordinary windows, and leaving them running under the lock wastes
# a GPU for nothing, since the compositor will not render them while locked.
