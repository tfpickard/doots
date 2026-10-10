#!/usr/bin/env bash
# Do-not-disturb toggle that works with whichever notification daemon is up.
#
# mako and swaync spell this completely differently:
#   mako    modes are a LIST you add to or remove from (makoctl mode -a/-r).
#           There is no toggle flag -- `makoctl mode -t` is not valid and just
#           prints "Illegal option -t".
#   swaync  has a real toggle: swaync-client -d
#
# so a single keybind needs this shim. Bound to Mod+Ctrl+N.
#
#   dnd.sh          toggle
#   dnd.sh on       force on
#   dnd.sh off      force off
#   dnd.sh status   print current state (on/off)

set -u

MODE="do-not-disturb"

mako_state() {
    makoctl mode 2>/dev/null | grep -qx "$MODE" && echo on || echo off
}

swaync_state() {
    # swaync-client -D prints "true"/"false" for the DND state.
    case "$(swaync-client -D 2>/dev/null)" in
        true) echo on ;;
        *)    echo off ;;
    esac
}

daemon() {
    if pgrep -x swaync >/dev/null 2>&1; then
        echo swaync
    elif pgrep -x mako >/dev/null 2>&1; then
        echo mako
    else
        echo none
    fi
}

d="$(daemon)"
[ "$d" = none ] && { echo "no notification daemon running" >&2; exit 1; }

case "$d" in
    mako)   state="$(mako_state)" ;;
    swaync) state="$(swaync_state)" ;;
esac

case "${1:-toggle}" in
    status)
        echo "$d: dnd $state"
        exit 0
        ;;
    on)  want=on ;;
    off) want=off ;;
    toggle|"")
        [ "$state" = on ] && want=off || want=on
        ;;
    *)
        echo "usage: $(basename "$0") [toggle|on|off|status]" >&2
        exit 1
        ;;
esac

[ "$want" = "$state" ] && exit 0

if [ "$d" = mako ]; then
    if [ "$want" = on ]; then
        makoctl mode -a "$MODE" >/dev/null
    else
        makoctl mode -r "$MODE" >/dev/null
    fi
else
    # swaync's -d flag toggles, and we already know it needs to change.
    swaync-client -d >/dev/null 2>&1
fi

command -v notify-send >/dev/null && [ "$want" = off ] && \
    notify-send "Do not disturb" "Notifications are back on."

echo "$d: dnd $want"
