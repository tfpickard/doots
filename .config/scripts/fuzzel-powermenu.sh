#!/usr/bin/env bash
# Power menu via fuzzel dmenu. Used by waybar (custom/power) and niri (Mod+X).
set -euo pipefail

entries=" Lock\n Suspend\n Logout\n Reboot\n Poweroff"

choice=$(printf "%b" "$entries" | fuzzel --dmenu --prompt="power> " --lines=5 --width=18) || exit 0

case "$choice" in
    *Lock)     swaylock -f ;;
    *Suspend)  systemctl suspend ;;
    *Logout)   niri msg action quit --skip-confirmation ;;
    *Reboot)   systemctl reboot ;;
    *Poweroff) systemctl poweroff ;;
esac
