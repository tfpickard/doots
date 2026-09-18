#!/usr/bin/env python3
"""Shared engine: launch and place the ten fixed-desk workspace apps.

The problem this solves: three of these apps (Chrome, ghostty) open more than
one window that share an app-id, so a niri window-rule cannot tell them
apart -- there is nothing in `niri msg windows` that distinguishes "the second
Chrome window" from "the third". The two VS Code windows share a PID too, but
ARE told apart by title ("Agents" vs everything else), so they get a
window-rule in config.kdl and this engine only double-checks that rule fired.

The trick for the truly ambiguous windows is to never have two unclaimed
windows of the same app-id in flight at once: launch one, wait for a window
matching that app-id to appear that no earlier slot already claimed, claim it,
move it, and only then launch the next. Because launches are serialized,
"the newest matching window nobody has claimed yet" is unambiguous even
though the windows themselves are identical.

Two entry points share this engine:
  niri-autostart-apps.py  -- runs at niri startup, launches whatever isn't
                             already running (spawn=True)
  niri-replace.py         -- re-places whatever already exists after a dock
                             cycle scrambles things, launches nothing new
                             (spawn=False)

Idempotent either way: a slot whose target workspace already has a matching
window is skipped, so re-running (or a niri config reload re-firing
spawn-at-startup) never launches duplicates.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

CHROME = "/opt/google/chrome/google-chrome"

TEAMS_APP_ID = "cifhbcnohmdccbgoicgdjpfamggdegmo"
OUTLOOK_APP_ID = "faolnafnngnfdaknnbpnkhgohbobgegn"


@dataclass
class Slot:
    ws: str
    app_id: str          # exact niri app_id to match
    cmd: list[str] | None  # None = never spawned, only adopted (VS Code's
                            # "agents" window comes back via session restore)
    title_hint: re.Pattern | None = None  # only needed when a sibling slot
                                           # shares this app_id (VS Code)
    # If a niri window-rule already places this app-id/title combination,
    # the engine still verifies and corrects, but a failure here means the
    # rule broke, not that IPC placement is the primary mechanism.
    rule_placed: bool = False


SLOTS: list[Slot] = [
    # VS Code: rule-placed by title (config.kdl). title_hint here means our
    # own adoption scan also respects the split, so a launch-order race can't
    # make the "code" slot steal the "agents" window before the rule (which
    # actually fires at window-creation, before this script ever sees it) --
    # this is belt-and-braces, not the primary mechanism.
    Slot("agents", "com.microsoft.VSCodeInsiders", None,
         title_hint=re.compile("Agents"), rule_placed=True),
    Slot("code", "com.microsoft.VSCodeInsiders", ["code-insiders"], rule_placed=True),

    # Chat: two different apps, same workspace. No ambiguity -- app_id alone
    # distinguishes them from each other; both are rule-placed.
    Slot("chat", f"chrome-{TEAMS_APP_ID}-Default",
         [CHROME, "--profile-directory=Default", f"--app-id={TEAMS_APP_ID}"],
         rule_placed=True),
    # Slack. --disable-gpu is required, not cosmetic: the snap's EGL stack
    # fails to initialise on this machine ("Failed to get system egl
    # display", then "Initialization of all (2) EGL display types failed"),
    # and Electron then never constructs its BrowserWindow at all. The
    # process starts, authenticates, loads the whole workspace and sits
    # there with no window AND no tray icon, which is what made this look
    # like a placement bug rather than a rendering one. With GPU disabled
    # the window maps in about three seconds.
    #
    # Worth re-testing after a snap or Mesa update -- host Mesa (25.2.8) and
    # the mesa-2404 snap (25.2.8-snap288) already match, and the opengl and
    # gnome-46-2404 interfaces are connected, so this is not simple version
    # skew and may well be fixed upstream without warning. Software
    # rendering is fine for chat; if huddles or screen-share regress, that
    # is the first thing to revisit.
    Slot("chat", "slack", ["/snap/bin/slack", "--disable-gpu"],
         rule_placed=True),

    # Mail: rule-placed, same shape as Teams.
    Slot("mail", f"chrome-{OUTLOOK_APP_ID}-Default",
         [CHROME, "--profile-directory=Default", f"--app-id={OUTLOOK_APP_ID}"],
         rule_placed=True),

    # Three plain Chrome windows -- genuinely indistinguishable from each
    # other. No window-rule can place these; IPC placement is the only
    # mechanism. Declared in the order they should be claimed.
    Slot("web1", "google-chrome", [CHROME, "--new-window"]),
    Slot("web2", "google-chrome", [CHROME, "--new-window"]),
    Slot("web3", "google-chrome", [CHROME, "--new-window"]),

    # Three ghostty windows -- same story.
    Slot("term1", "com.mitchellh.ghostty", ["ghostty"]),
    Slot("term2", "com.mitchellh.ghostty", ["ghostty"]),
    Slot("term3", "com.mitchellh.ghostty", ["ghostty"]),
]

# Serials from niri/config.kdl's `output` blocks. Used only to decide how
# long to wait for docking before giving up and proceeding laptop-only.
EXTERNAL_SERIALS = ("BJ4X5X2", "920C993")

SPAWN_WAIT_TIMEOUT = 20  # seconds to wait for one launched window to appear
ADOPT_ONLY_TIMEOUT = 15  # seconds to wait for a window we never spawn ourselves
OUTPUT_WAIT_TIMEOUT = 15  # seconds to wait for external monitors at login

# If not one external has appeared by this point, we are almost certainly
# undocked rather than mid-enumeration, so stop waiting. Partial docking
# (one monitor up, one still negotiating) still gets the full timeout --
# that case really is a race worth waiting out. Without this, every
# laptop-only login paid OUTPUT_WAIT_TIMEOUT in full before placing
# anything.
OUTPUT_WAIT_GRACE = 3.0

# Snap apps must not inherit XDG_*_HOME. prezto exports those even when they
# hold the spec default; snaps then try to write to the real ~/.config,
# ~/.cache, ... and the snap `home` AppArmor profile denies top-level
# dotfiles, so the app dies with SIGTRAP before mapping a window.
#
# .zshrc already works around this (see its "ESSENTIAL PLUGINS" section) by
# defining a zsh function per /snap/bin/* command that strips the variables.
# That only covers interactive shells. This script launches via Popen, which
# inherits the environment directly and bypasses the function entirely --
# so placement worked when niri ran it via spawn-at-startup (clean
# environment) and silently failed for every snap slot when run by hand from
# a terminal, which is exactly how it gets re-run after docking.
#
# Confirmed by coredump rather than inferred: four Slack SIGTRAPs in one
# session, the last reproduced on demand from a shell with XDG_CONFIG_HOME
# set to nothing more exotic than its own default value.
SNAP_HOSTILE_VARS = ("XDG_CACHE_HOME", "XDG_CONFIG_HOME",
                     "XDG_DATA_HOME", "XDG_STATE_HOME")


def spawn_env(cmd: list[str]) -> dict[str, str] | None:
    """Environment for a slot launch: None (inherit) for ordinary commands,
    XDG-stripped for snaps."""
    if not cmd or not os.path.realpath(cmd[0]).startswith("/snap/"):
        return None
    env = os.environ.copy()
    for var in SNAP_HOSTILE_VARS:
        env.pop(var, None)
    return env


def log(msg: str) -> None:
    print(f"[niri-placement] {msg}", file=sys.stderr, flush=True)


def niri_json(*args: str):
    try:
        out = subprocess.run(
            ["niri", "msg", "-j", *args],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return json.loads(out.stdout)
    except Exception as err:
        log(f"niri msg -j {' '.join(args)} failed: {err}")
        return None


def move_window_to_workspace(window_id: int, ws_name: str) -> None:
    subprocess.run(
        ["niri", "msg", "action", "move-window-to-workspace",
         "--window-id", str(window_id), "--focus", "false", ws_name],
        capture_output=True, text=True, timeout=5,
    )


def focus_workspace(ws_name: str) -> None:
    subprocess.run(
        ["niri", "msg", "action", "focus-workspace", ws_name],
        capture_output=True, text=True, timeout=5,
    )


def wait_for_outputs(serials: tuple[str, ...], timeout: float) -> None:
    """Wait for docking. Not fatal if it never happens -- laptop-only login
    is a normal case, not an error; the named workspaces just collapse onto
    eDP-1 and redistribute whenever the monitors do appear."""
    deadline = time.time() + timeout
    grace = time.time() + OUTPUT_WAIT_GRACE
    missing = set(serials)
    while missing and time.time() < deadline:
        outputs = niri_json("outputs") or {}
        seen = {info.get("serial") for info in outputs.values()}
        missing -= seen
        if not missing:
            break
        # Nothing at all after the grace period means undocked, not slow.
        if len(missing) == len(serials) and time.time() >= grace:
            break
        time.sleep(0.5)
    if missing:
        log(f"proceeding without: {', '.join(sorted(missing))} (undocked?)")


class WindowTracker:
    """Follows `niri msg event-stream` and keeps a live window_id -> window
    dict, with a wait() that wakes callers on every update instead of making
    them poll."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._windows: dict[int, dict] = {}
        self._ready = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=5)

    def _run(self) -> None:
        self._proc = subprocess.Popen(
            ["niri", "msg", "-j", "event-stream"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        for line in self._proc.stdout:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            with self._cond:
                if "WindowsChanged" in ev:
                    self._windows = {
                        w["id"]: w for w in ev["WindowsChanged"]["windows"]
                    }
                    self._ready.set()
                elif "WindowOpenedOrChanged" in ev:
                    w = ev["WindowOpenedOrChanged"]["window"]
                    self._windows[w["id"]] = w
                elif "WindowClosed" in ev:
                    self._windows.pop(ev["WindowClosed"]["id"], None)
                else:
                    continue
                self._cond.notify_all()

    def snapshot(self) -> dict[int, dict]:
        with self._cond:
            return dict(self._windows)

    def wait_for(self, predicate: Callable[[dict], bool],
                 timeout: float) -> dict | None:
        deadline = time.time() + timeout
        with self._cond:
            while True:
                for w in self._windows.values():
                    if predicate(w):
                        return w
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)


def matches(slot: Slot, w: dict) -> bool:
    if w.get("app_id") != slot.app_id:
        return False
    if slot.title_hint and not slot.title_hint.search(w.get("title") or ""):
        return False
    return True


def run(spawn: bool) -> None:
    """Place every slot. spawn=False (niri-replace.py) only adopts and moves
    windows that already exist; spawn=True (niri-autostart-apps.py) also
    launches whatever a slot needs and isn't running."""
    if spawn:
        wait_for_outputs(EXTERNAL_SERIALS, OUTPUT_WAIT_TIMEOUT)

    ws_by_name = {w["name"]: w["id"] for w in (niri_json("workspaces") or [])
                  if w.get("name")}
    missing_ws = {slot.ws for slot in SLOTS} - set(ws_by_name)
    if missing_ws:
        log(f"named workspaces not found (config not loaded?): {missing_ws}")
        return

    tracker = WindowTracker()
    tracker.start()

    claimed: set[int] = set()

    def unclaimed_match(slot: Slot) -> dict | None:
        for w in tracker.snapshot().values():
            if w["id"] not in claimed and matches(slot, w):
                return w
        return None

    for slot in SLOTS:
        target_id = ws_by_name[slot.ws]

        # Idempotent: if this slot's target workspace already holds a
        # matching window, there's nothing to do -- covers re-runs and
        # config reloads without relaunching anything.
        already = [
            w for w in tracker.snapshot().values()
            if w.get("workspace_id") == target_id and matches(slot, w)
        ]
        if already:
            claimed.add(already[0]["id"])
            continue

        win = unclaimed_match(slot)

        if win is None and slot.cmd is not None and spawn:
            log(f"{slot.ws}: launching {' '.join(slot.cmd)}")
            try:
                subprocess.Popen(
                    slot.cmd, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True,
                    env=spawn_env(slot.cmd),
                )
            except OSError as err:
                log(f"{slot.ws}: launch failed: {err}")
                continue
            win = tracker.wait_for(
                lambda w, s=slot: matches(s, w) and w["id"] not in claimed,
                SPAWN_WAIT_TIMEOUT,
            )
        elif win is None and slot.cmd is None:
            # e.g. the "agents" window: never spawned directly, only ever
            # adopted from VS Code's own session restore (triggered by the
            # "code" slot's launch, which may run after this one in
            # declaration order -- so give it a grace window too).
            win = tracker.wait_for(
                lambda w, s=slot: matches(s, w) and w["id"] not in claimed,
                ADOPT_ONLY_TIMEOUT,
            )

        if win is None:
            if slot.cmd is not None and not spawn:
                log(f"{slot.ws}: no window yet and spawn disabled, skipping")
            else:
                log(f"{slot.ws}: no matching window appeared, giving up")
            continue

        claimed.add(win["id"])
        if win.get("workspace_id") != target_id:
            move_window_to_workspace(win["id"], slot.ws)
            log(f"{slot.ws}: placed window {win['id']} ({slot.app_id})")

    focus_workspace("code")
