#!/usr/bin/env bash
# Toggle the CPU scaling governor between the two modes this machine exposes
# (powersave <-> performance). Bound to left-click on the waybar cpufreq module.
#
# Writing the governor needs root, so we escalate via pkexec (graphical polkit
# prompt) and prefer `cpupower` when present, falling back to sysfs writes.
set -euo pipefail

cur=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)

case "$cur" in
    performance) next=powersave ;;
    *)           next=performance ;;
esac

if command -v cpupower >/dev/null 2>&1; then
    pkexec cpupower frequency-set -g "$next" >/dev/null
else
    pkexec sh -c 'for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo "'"$next"'" > "$g"; done'
fi

if command -v notify-send >/dev/null 2>&1; then
    notify-send -t 2000 "CPU governor" "→ $next"
fi

# Refresh the waybar cpufreq module immediately (matches "signal": 9).
for pid in $(pidof waybar 2>/dev/null); do
    kill -SIGRTMIN+9 "$pid" 2>/dev/null || true
done
