#!/usr/bin/env bash
# Toggle the waybar battery module's bar text between wattage and current+voltage.
# Bound to left-click on the custom/battery module. Flips a state file the
# battery-power.py script reads, then pokes waybar (RTMIN+8) so the change is
# instant instead of waiting for the next poll interval.
set -u

state="${XDG_RUNTIME_DIR:-/tmp}/waybar-battery-mode"
cur=$(cat "$state" 2>/dev/null || echo power)

if [ "$cur" = "power" ]; then
    echo vi > "$state"
else
    echo power > "$state"
fi

for pid in $(pidof waybar 2>/dev/null); do
    kill -SIGRTMIN+8 "$pid" 2>/dev/null || true
done
