#!/usr/bin/env bash
# Launch (or relaunch) waybar with the selected theme.
#
# Theme selection lives in ~/.cache/.themestyle.sh as "/THEME;/VARIATION"
# (kept for compatibility with themeswitcher.sh). Colors inside a theme come
# from the global theme system (~/.config/themes/active) — switch palettes
# with `theme-set`, switch bar layouts with themeswitcher.sh.
set -u

WAYBAR_DIR="$HOME/.config/waybar"
LOG=/tmp/waybar.log

# Respect the toggle.sh kill switch.
if [ -f "$HOME/.cache/waybar-disabled" ]; then
    pkill -x waybar
    exit 0
fi

# Restart cleanly if already running.
pkill -x waybar && sleep 0.2

# Default / persisted theme.
themestyle="/dope;/dope"
if [ -f "$HOME/.cache/.themestyle.sh" ]; then
    themestyle=$(cat "$HOME/.cache/.themestyle.sh")
else
    echo "$themestyle" > "$HOME/.cache/.themestyle.sh"
fi

IFS=';' read -r theme variation <<< "$themestyle"

# Fall back to dope if the persisted theme vanished.
if [ ! -f "$WAYBAR_DIR/themes$variation/style.css" ]; then
    theme="/dope"; variation="/dope"
    echo "/dope;/dope" > "$HOME/.cache/.themestyle.sh"
fi

config_file="config"
style_file="style.css"
[ -f "$WAYBAR_DIR/themes$theme/config-custom" ] && config_file="config-custom"
[ -f "$WAYBAR_DIR/themes$variation/style-custom.css" ] && style_file="style-custom.css"

echo ":: waybar theme: $theme ($variation)"
waybar -c "$WAYBAR_DIR/themes$theme/$config_file" \
       -s "$WAYBAR_DIR/themes$variation/$style_file" >"$LOG" 2>&1 &
disown
