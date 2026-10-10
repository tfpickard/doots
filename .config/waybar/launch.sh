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

CONFIG_PATH="$WAYBAR_DIR/themes$theme/$config_file"

# --- Compositor/output-aware left group -----------------------------------
#
# The committed themes drive their workspace/window indicators with
# custom/niriws and custom/niriwindow, which follow `niri msg event-stream`.
# Two things derive from the same source config at launch time rather than
# needing a second hand-written theme (which is how configs drift):
#
#   niri, N outputs   Waybar draws one identical bar per output by default,
#                      and the committed custom/niriws would show every
#                      workspace from every output on all of them -- with
#                      one named workspace per app across three monitors,
#                      that's unreadable. compositor-config.py's
#                      "niri-outputs" mode expands the single bar config
#                      into an array, one per connected output, each filtered
#                      to just that output.
#
#   Hyprland           There is no niri IPC socket, so custom/niriws and
#                      custom/niriwindow exit immediately, restart-interval
#                      respawns them every few seconds, and the left side of
#                      the bar just sits there blank. "hyprland" mode swaps
#                      those two modules for the built-in hyprland/workspaces
#                      and hyprland/window, which do their own
#                      separate-outputs -- so no per-output loop is needed on
#                      this path.
if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && [ -z "${NIRI_SOCKET:-}" ]; then
    GENERATED="${XDG_RUNTIME_DIR:-/tmp}/waybar-config-hyprland.json"
    if python3 "$WAYBAR_DIR/scripts/compositor-config.py" \
           hyprland "$CONFIG_PATH" "$GENERATED" 2>>"$LOG"; then
        CONFIG_PATH="$GENERATED"
        echo ":: waybar: Hyprland detected, using generated config"
    else
        echo ":: waybar: could not generate Hyprland config, using theme as-is" >&2
    fi
elif [ -n "${NIRI_SOCKET:-}" ]; then
    GENERATED="${XDG_RUNTIME_DIR:-/tmp}/waybar-bars.json"
    if python3 "$WAYBAR_DIR/scripts/compositor-config.py" \
           niri-outputs "$CONFIG_PATH" "$GENERATED" 2>>"$LOG"; then
        CONFIG_PATH="$GENERATED"
        n=$(python3 -c "import json;print(len(json.load(open('$GENERATED'))))" 2>/dev/null || echo '?')
        echo ":: waybar: niri detected, $n output(s), using generated per-output config"
    else
        echo ":: waybar: could not generate per-output config, using theme as-is" >&2
    fi
fi

echo ":: waybar theme: $theme ($variation)"
waybar -c "$CONFIG_PATH" \
       -s "$WAYBAR_DIR/themes$variation/$style_file" >"$LOG" 2>&1 &
disown
