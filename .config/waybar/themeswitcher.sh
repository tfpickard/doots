#!/usr/bin/env bash
# Pick a waybar *layout* theme with fuzzel and relaunch waybar with it.
# (Bar layouts live in ~/.config/waybar/themes/<name>. For color palettes
# across ALL apps, use `theme-set` instead.)
set -euo pipefail

WAYBAR_DIR="$HOME/.config/waybar"

mapfile -t themes < <(find "$WAYBAR_DIR/themes" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)

if [ "${#themes[@]}" -eq 0 ]; then
    notify-send "Waybar" "No themes found in $WAYBAR_DIR/themes"
    exit 1
fi

choice=$(printf '%s\n' "${themes[@]}" | fuzzel --dmenu --prompt="waybar> " --lines="${#themes[@]}") || exit 0

echo "/$choice;/$choice" > "$HOME/.cache/.themestyle.sh"
"$WAYBAR_DIR/launch.sh"
notify-send "Waybar theme changed" "Now using: $choice"
