#!/usr/bin/env bash
# AC-aware DPMS control for niri, driven by swayidle timeouts.
#
#   idle-dpms.sh off   -> power monitors OFF, but ONLY when running on battery.
#                         When plugged into AC the screen is left on.
#   idle-dpms.sh on    -> power monitors back on (used on swayidle "resume").
#
# The idle screen-lock (swaylock) is handled separately in the niri config and
# is intentionally left untouched, so the machine still locks when idle.

set -u

on_ac() {
    # True (0) if any Mains/AC adapter currently reports online == 1.
    local type_file online_file
    for type_file in /sys/class/power_supply/*/type; do
        [ -r "$type_file" ] || continue
        [ "$(cat "$type_file")" = "Mains" ] || continue
        online_file="${type_file%/type}/online"
        [ -r "$online_file" ] && [ "$(cat "$online_file")" = "1" ] && return 0
    done
    return 1
}

case "${1:-}" in
    off)
        # Plugged in? Keep the screen on. On battery, power monitors off.
        on_ac && exit 0
        exec niri msg action power-off-monitors
        ;;
    on)
        exec niri msg action power-on-monitors
        ;;
    *)
        echo "usage: ${0##*/} {off|on}" >&2
        exit 2
        ;;
esac
