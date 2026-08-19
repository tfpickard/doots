#!/usr/bin/env bash
# Toggle the xscreensaver "atlantis" GL hack on/off.
# When starting, it ensures xwayland-satellite is running on DISPLAY=:12,
# then launches atlantis. The niri window-rule (match app-id="Atlantis")
# takes care of placing it fullscreen on eDP-1.

set -u

DISPLAY_NUM=":12"
ATLANTIS="/usr/libexec/xscreensaver/atlantis"

if pgrep -x atlantis >/dev/null 2>&1; then
    pkill -x atlantis
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
