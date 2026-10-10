#!/usr/bin/env python3
"""
mutter-idle-monitor: a tiny D-Bus shim implementing org.gnome.Mutter.IdleMonitor
for wlroots-based Wayland compositors (niri, sway, Hyprland) that don't provide it.

Why this exists
---------------
Chromium/Chrome's Web Idle Detection API (used by Microsoft Teams, Slack, etc.
to set your "Available/Away" presence) reads the user's idle time on Linux from
the D-Bus service:

    name:   org.gnome.Mutter.IdleMonitor
    path:   /org/gnome/Mutter/IdleMonitor/Core
    method: GetIdletime() -> UInt64 (milliseconds since last input)
    method: AddIdleWatch(UInt64 interval_ms) -> UInt32 id
    method: AddUserActiveWatch() -> UInt32 id
    method: RemoveWatch(UInt32 id)
    signal: WatchFired(UInt32 id)

GNOME/Mutter provide this; niri does not. Without it Chrome cannot see your real
activity, so Teams flips you to "Away" even while you're working. This daemon
provides the service and derives real idle time from the compositor via swayidle
(ext-idle-notify-v1), so Teams follows your actual activity again.

It intentionally has no external Python deps beyond PyGObject (Gio/GLib), which
ships on Ubuntu.
"""

import os
import signal
import subprocess
import time

import gi
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_NAME = "org.gnome.Mutter.IdleMonitor"
OBJ_PATH = "/org/gnome/Mutter/IdleMonitor/Core"
IFACE = "org.gnome.Mutter.IdleMonitor"

# swayidle base resolution: how quickly we notice the user went idle.
# Teams uses a ~5 min threshold, so a few seconds of resolution is plenty.
IDLE_DETECT_SECONDS = 4

INTROSPECTION_XML = f"""
<node>
  <interface name="{IFACE}">
    <method name="GetIdletime">
      <arg type="t" name="idletime" direction="out"/>
    </method>
    <method name="AddIdleWatch">
      <arg type="t" name="interval" direction="in"/>
      <arg type="u" name="id" direction="out"/>
    </method>
    <method name="AddUserActiveWatch">
      <arg type="u" name="id" direction="out"/>
    </method>
    <method name="RemoveWatch">
      <arg type="u" name="id" direction="in"/>
    </method>
    <signal name="WatchFired">
      <arg type="u" name="id"/>
    </signal>
  </interface>
</node>
"""


class IdleMonitor:
    def __init__(self):
        self.connection = None
        self.reg_id = None

        # Activity state, driven by swayidle via SIGUSR1/SIGUSR2.
        self.active = True
        # Monotonic time (seconds) at which the current idle period began.
        self.idle_since = None

        # Watches: id -> dict(kind='idle'|'active', interval=ms, source=GLib id)
        self.watches = {}
        self._next_id = 1

        self.swayidle = None

    # ---- idle bookkeeping -------------------------------------------------
    def idle_ms(self):
        if self.active or self.idle_since is None:
            return 0
        return int((time.monotonic() - self.idle_since) * 1000)

    def _new_id(self):
        wid = self._next_id
        self._next_id += 1
        return wid

    def _fire(self, wid):
        if self.connection is None:
            return
        self.connection.emit_signal(
            None, OBJ_PATH, IFACE, "WatchFired", GLib.Variant("(u)", (wid,))
        )

    def _schedule_idle_watch(self, wid, interval_ms):
        """Fire this idle watch when total idle reaches interval_ms."""
        if self.active or self.idle_since is None:
            return
        already = self.idle_ms()
        delay = max(0, interval_ms - already)

        def cb():
            self.watches.get(wid, {}).pop("source", None)
            self._fire(wid)
            return GLib.SOURCE_REMOVE

        src = GLib.timeout_add(delay, cb)
        w = self.watches.get(wid)
        if w is not None:
            w["source"] = src

    # ---- transitions from swayidle ---------------------------------------
    def on_idle(self):
        # We learn about idle IDLE_DETECT_SECONDS after it actually began.
        if self.active:
            self.active = False
            self.idle_since = time.monotonic() - IDLE_DETECT_SECONDS
        # (Re)arm all idle watches relative to the real idle start.
        for wid, w in list(self.watches.items()):
            if w["kind"] == "idle" and "source" not in w:
                self._schedule_idle_watch(wid, w["interval"])
        return True  # keep GLib unix signal source

    def on_active(self):
        was_idle = not self.active
        self.active = True
        self.idle_since = None
        # Cancel pending idle-watch timers.
        for w in self.watches.values():
            src = w.pop("source", None)
            if src is not None:
                GLib.source_remove(src)
        if was_idle:
            # Fire (and remove) all user-active watches.
            for wid, w in list(self.watches.items()):
                if w["kind"] == "active":
                    self._fire(wid)
                    del self.watches[wid]
        return True

    # ---- D-Bus method dispatch -------------------------------------------
    def handle_call(self, conn, sender, path, iface, method, params, invocation):
        if method == "GetIdletime":
            invocation.return_value(GLib.Variant("(t)", (self.idle_ms(),)))
        elif method == "AddIdleWatch":
            (interval,) = params.unpack()
            wid = self._new_id()
            self.watches[wid] = {"kind": "idle", "interval": int(interval)}
            if not self.active:
                self._schedule_idle_watch(wid, int(interval))
            invocation.return_value(GLib.Variant("(u)", (wid,)))
        elif method == "AddUserActiveWatch":
            wid = self._new_id()
            self.watches[wid] = {"kind": "active"}
            invocation.return_value(GLib.Variant("(u)", (wid,)))
        elif method == "RemoveWatch":
            (wid,) = params.unpack()
            w = self.watches.pop(int(wid), None)
            if w is not None:
                src = w.get("source")
                if src is not None:
                    GLib.source_remove(src)
            invocation.return_value(None)
        else:
            invocation.return_error_literal(
                Gio.dbus_error_quark(),
                Gio.DBusError.UNKNOWN_METHOD,
                f"Unknown method {method}",
            )

    # ---- lifecycle --------------------------------------------------------
    def on_bus_acquired(self, connection, name):
        self.connection = connection
        node = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
        self.reg_id = connection.register_object(
            OBJ_PATH, node.interfaces[0], self.handle_call, None, None
        )
        self.start_swayidle()

    def start_swayidle(self):
        pid = os.getpid()
        # swayidle reports idle after IDLE_DETECT_SECONDS and resume on input.
        self.swayidle = subprocess.Popen(
            [
                "swayidle", "-w",
                "timeout", str(IDLE_DETECT_SECONDS), f"kill -USR2 {pid}",
                "resume", f"kill -USR1 {pid}",
            ]
        )

    def run(self):
        loop = GLib.MainLoop()
        self._loop = loop
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.on_active)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, self.on_idle)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: loop.quit() or True)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: loop.quit() or True)

        # If another instance already owns the name (e.g. session restart),
        # replace it, but if we later lose the name, exit cleanly so we don't
        # leave an orphaned swayidle behind.
        def on_name_lost(connection, name):
            loop.quit()

        Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.REPLACE | Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
            self.on_bus_acquired,
            None,
            on_name_lost,
        )
        try:
            loop.run()
        finally:
            if self.swayidle and self.swayidle.poll() is None:
                self.swayidle.terminate()


if __name__ == "__main__":
    IdleMonitor().run()
