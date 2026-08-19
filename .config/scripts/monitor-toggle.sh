#!/usr/bin/env bash
# Toggle a floating monitoring terminal for a waybar module.
#
#   monitor-toggle.sh <app-id> <command> [args...]
#
# First invocation launches a *dedicated* ghostty window (single-instance
# disabled so the process owns the window) with the given Wayland app-id,
# running <command>. A niri window-rule matching ^com\.waybar\. floats it, so
# it never disturbs the tiling layout. A second invocation on the same app-id
# closes that window (and whatever is running inside it) instead of spawning a
# duplicate.
set -u

if [ "$#" -lt 2 ]; then
    echo "usage: monitor-toggle.sh <app-id> <command> [args...]" >&2
    exit 2
fi

appid="$1"; shift
runtime="${XDG_RUNTIME_DIR:-/tmp}"
pidfile="$runtime/waybar-monitor-${appid}.pid"

# Already open? Close it.
if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile" 2>/dev/null || true)
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        rm -f "$pidfile"
        exit 0
    fi
    rm -f "$pidfile"
fi

# Not open: launch a floating terminal running the tool.
ghostty \
    --class="$appid" \
    --title="$appid" \
    --gtk-single-instance=false \
    -e "$@" &
echo $! > "$pidfile"
