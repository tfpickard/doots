#!/usr/bin/env bash
# Toggle the xscreensaver "atlantis" GL hack on/off.
#
# It doubles as the off switch for the whole screensaver: if ANY hack is running
# -- atlantis, or a set put up by `lock-screensaver.py next` (Mod+Ctrl+Shift+Z)
# -- this stops all of them rather than adding one more. Otherwise it starts
# atlantis, and the niri window-rule (match app-id="Atlantis") places it
# fullscreen on eDP-1.
#
# When starting, it ensures xwayland-satellite is running on DISPLAY=:12.

set -u

DISPLAY_NUM=":12"
HACK_DIR="/usr/libexec/xscreensaver"
ATLANTIS="$HACK_DIR/atlantis"

if pgrep -f "^$HACK_DIR/" >/dev/null 2>&1; then
    # Go through the script for the ones it tracks, so its pidfile is cleaned
    # up, then sweep anything it doesn't know about (this atlantis included).
    "$HOME/.config/scripts/lock-screensaver.py" stop >/dev/null 2>&1
    pkill -f "^$HACK_DIR/" >/dev/null 2>&1
    exit 0
fi

# Make sure the X server (xwayland-satellite) is up before launching an X app.
if ! pgrep -f "xwayland-satellite ${DISPLAY_NUM}" >/dev/null 2>&1; then
    xwayland-satellite "$DISPLAY_NUM" >/tmp/xwayland-satellite.log 2>&1 &
    # Wait for the X socket to appear (up to ~5s).
    for _ in $(seq 1 50); do
        [ -S "/tmp/.X11-unix/X${DISPLAY_NUM#:}" ] && break
        sleep 0.1
    done
fi

DISPLAY="$DISPLAY_NUM" "$ATLANTIS" -window >/tmp/atlantis.log 2>&1 &
exit 0
