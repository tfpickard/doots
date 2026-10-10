#!/usr/bin/env python3
"""Make the first window on an empty workspace fill the screen.

niri has no `layout` option for "open new columns full-width only when the
workspace is empty" -- `default-column-width` is unconditional. So this daemon
watches niri's IPC event stream and, whenever a window opens as the *only*
tiled window on its workspace, fires the `expand-column-to-available-width`
action.

That action grows the focused column into whatever horizontal space isn't taken
by other fully visible columns. With no other columns, that is the whole output
minus `gaps` and `struts`, which is exactly the "fill the screen with some
border space" behaviour. Open a second window and it takes the normal
`default-column-width`, so the scrolling layout still works as usual.

Started from niri's config with `spawn-at-startup`. Safe to run more than once,
though there is no reason to.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time

# Windows whose app-id is in here never trigger an expand. The xscreensaver GL
# hack opens fullscreen on the built-in panel via a window rule; poking the
# column width underneath it is pointless.
IGNORED_APP_IDS = {"Atlantis"}


def single_instance() -> "object | None":
    """Return a held lock, or None if another copy is already running.

    Kept so that starting this by hand in a running session doesn't leave a
    duplicate behind once niri spawns it again at the next login.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    lock = open(os.path.join(runtime, "niri-expand-lonely-column.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return None
    return lock


def niri_action(*args: str) -> None:
    try:
        subprocess.run(
            ["niri", "msg", "action", *args],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        pass


class Watcher:
    def __init__(self) -> None:
        # window id -> (workspace id, is_floating)
        self.windows: dict[int, tuple[int | None, bool]] = {}

    def _record(self, window: dict) -> None:
        self.windows[window["id"]] = (
            window.get("workspace_id"),
            bool(window.get("is_floating")),
        )

    def _tiled_on(self, workspace_id: int | None, *, exclude: int) -> int:
        if workspace_id is None:
            return 0
        return sum(
            1
            for wid, (ws, floating) in self.windows.items()
            if wid != exclude and ws == workspace_id and not floating
        )

    def handle(self, event: dict) -> None:
        if "WindowsChanged" in event:
            self.windows.clear()
            for window in event["WindowsChanged"]["windows"]:
                self._record(window)
            return

        if "WindowClosed" in event:
            self.windows.pop(event["WindowClosed"]["id"], None)
            return

        if "WindowOpenedOrChanged" not in event:
            return

        window = event["WindowOpenedOrChanged"]["window"]
        is_new = window["id"] not in self.windows
        self._record(window)

        if not is_new:
            return
        if window.get("is_floating"):
            return
        if (window.get("app_id") or "") in IGNORED_APP_IDS:
            return
        # The action operates on the focused column, so only act when the new
        # window actually took focus.
        if not window.get("is_focused"):
            return
        if self._tiled_on(window.get("workspace_id"), exclude=window["id"]):
            return

        niri_action("expand-column-to-available-width")


def stream() -> int:
    proc = subprocess.Popen(
        ["niri", "msg", "--json", "event-stream"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    watcher = Watcher()
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        watcher.handle(event)
    return proc.wait()


def main() -> int:
    socket_path = os.environ.get("NIRI_SOCKET")
    if not socket_path:
        print("NIRI_SOCKET is not set; not running under niri", file=sys.stderr)
        return 1

    lock = single_instance()
    if lock is None:
        print("another instance is already running", file=sys.stderr)
        return 0

    # A niri config reload or a brief IPC hiccup ends the stream, so reconnect
    # rather than die. But once the socket is gone niri itself is gone: exit,
    # instead of spinning forever after logout.
    while os.path.exists(socket_path):
        try:
            stream()
        except (OSError, subprocess.SubprocessError) as err:
            print(f"event stream failed: {err}", file=sys.stderr)
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
