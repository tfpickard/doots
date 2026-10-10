#!/usr/bin/env bash
# Toggle a "keep active" mouse jiggler so Microsoft Teams stops showing you as
# idle/away while you work in other windows (e.g. VS Code).
#
# How it works:
#   Every INTERVAL seconds it nudges the pointer 1px and back via ydotool. That
#   resets the Wayland compositor idle timer that Chrome's Idle Detection API
#   reads, so Teams keeps you "Available". Run again to toggle it off and let
#   your presence follow real idle again -> YOU decide when you look idle.
#
# REQUIREMENT (one-time): In Chrome, grant teams.microsoft.com the
#   "Idle detection" permission (Site settings) so Teams follows system idle.
#   Without it, Teams tracks only its own tab and this jiggle won't reach it.
#
# Bound to a niri key (Mod+Ctrl+P); running it again toggles it off.

set -u

INTERVAL="${TEAMS_JIGGLE_INTERVAL:-60}"    # seconds between nudges (well under Teams' idle threshold)
PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/teams-keep-active.pid"

notify() {
    command -v notify-send >/dev/null 2>&1 && notify-send -a "Teams" "$1" "$2"
}

# --- Toggle OFF if a jiggler is already running -----------------------------
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
    notify "Keep-active OFF" "Teams presence now follows your real idle."
    exit 0
fi
rm -f "$PIDFILE"

# --- Toggle ON: start the jiggle loop in the background ---------------------
if ! command -v ydotool >/dev/null 2>&1; then
    notify "Keep-active failed" "ydotool is not installed."
    exit 1
fi

(
    while true; do
        ydotool mousemove 1 0     >/dev/null 2>&1
        ydotool mousemove -- -1 0 >/dev/null 2>&1
        sleep "$INTERVAL"
    done
) &
echo $! > "$PIDFILE"
notify "Keep-active ON" "Nudging every ${INTERVAL}s so Teams stays Available."
exit 0
