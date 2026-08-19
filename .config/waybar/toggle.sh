#!/usr/bin/env bash
# Toggle waybar on/off (bound in niri / usable from a terminal).
if [ -f "$HOME/.cache/waybar-disabled" ]; then
    rm "$HOME/.cache/waybar-disabled"
else
    touch "$HOME/.cache/waybar-disabled"
fi
exec "$HOME/.config/waybar/launch.sh"
