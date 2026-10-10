#!/usr/bin/env bash
# Switch the running notification daemon.
#
# Only ONE process can own org.freedesktop.Notifications on the session bus, so
# mako, swaync and fnott are mutually exclusive -- starting a second one just
# gets "name already taken" and it exits. This script stops whatever is running
# and starts the one you asked for.
#
#   notify-daemon.sh              show which daemon is active
#   notify-daemon.sh mako         lightweight, config at themes/active/mako.ini
#   notify-daemon.sh swaync       slide-out control centre, DND, media controls
#   notify-daemon.sh fnott        minimal, keyboard-driven, no GTK
#   notify-daemon.sh test         send a few notifications to see the styling
#
# The daemon started here is NOT persisted; niri's spawn-at-startup still
# starts mako at login. Change that line in ~/.config/niri/config.kdl if you
# decide to switch for good.
#
# Daemons are started with setsid so they survive this script's shell exiting.
# Without it the daemon is a child of whatever terminal you ran this from and
# dies with it, taking your notifications with it.

set -u

DAEMONS="mako swaync fnott"

bus_owner() {
    gdbus call --session \
        --dest org.freedesktop.DBus \
        --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.GetNameOwner \
        org.freedesktop.Notifications 2>/dev/null
}

running_daemon() {
    for d in $DAEMONS; do
        if pgrep -x "$d" >/dev/null 2>&1; then
            echo "$d"
            return 0
        fi
    done
    return 1
}

stop_all() {
    for d in $DAEMONS; do
        for pid in $(pgrep -x "$d" 2>/dev/null); do
            kill "$pid" 2>/dev/null
        done
    done
    # Give the bus a moment to release the name, or the next daemon will fail
    # to acquire it and quit immediately.
    for _ in $(seq 1 20); do
        bus_owner >/dev/null 2>&1 || break
        sleep 0.1
    done
}

status() {
    current="$(running_daemon || true)"
    if [ -n "$current" ]; then
        echo "active notification daemon: $current"
    else
        echo "no notification daemon is running"
    fi
    owner="$(bus_owner || true)"
    [ -n "$owner" ] && echo "bus name owner: $owner"
}

send_tests() {
    command -v notify-send >/dev/null || { echo "notify-send not installed" >&2; return 1; }
    notify-send -u low "Low urgency" "Quiet background chatter."
    sleep 0.4
    notify-send -u normal "Normal urgency" "A regular notification with a bit of body text to show wrapping."
    sleep 0.4
    notify-send -u critical "Critical urgency" "This one should stay until dismissed."
}

case "${1:-status}" in
    status|"")
        status
        ;;
    test)
        send_tests
        ;;
    mako)
        stop_all
        setsid mako >/dev/null 2>&1 &
        sleep 0.5
        status
        ;;
    swaync)
        stop_all
        # The packaged swaync.service is masked so it can't race mako at login;
        # start the binary directly instead of via systemd.
        setsid swaync >/dev/null 2>&1 &
        sleep 0.8
        status
        ;;
    fnott)
        stop_all
        setsid fnott >/dev/null 2>&1 &
        sleep 0.5
        status
        ;;
    *)
        echo "usage: $(basename "$0") [status|mako|swaync|fnott|test]" >&2
        exit 1
        ;;
esac
