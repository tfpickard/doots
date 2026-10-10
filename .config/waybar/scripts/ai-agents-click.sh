#!/usr/bin/env bash
# Click actions for the waybar custom/aiagents module.
#
#   focus    (left click)  raise the IDE window hosting the agent sessions
#   summary  (right click) fire the module's tooltip off as a notification,
#                          for when the bar is on another output
#
# Focusing works under niri and Hyprland; on anything else it degrades to the
# notification so the click is never a no-op.
set -u

ACTION="${1:-focus}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# app-ids of the editors that host Copilot agent sessions.
IDE_IDS='code-insiders|code|Code|VSCodium|code-oss'

summary() {
    local json text tooltip
    json=$(python3 "$SCRIPT_DIR/ai-agents.py" 2>/dev/null) || return 1
    text=$(printf '%s' "$json" | jq -r '.text // ""')
    # Notifications take plain text, so drop the tooltip's Pango markup.
    tooltip=$(printf '%s' "$json" | jq -r '.tooltip // ""' | sed -E 's/<[^>]+>//g')
    notify-send -a waybar -u normal "AI agents  $text" "$tooltip"
}

focus_niri() {
    local id
    id=$(niri msg -j windows 2>/dev/null | jq -r --arg re "^($IDE_IDS)$" '
        [.[] | select((.app_id // "") | test($re))] | first | .id // empty')
    [ -n "$id" ] || return 1
    niri msg action focus-window --id "$id" >/dev/null 2>&1
}

focus_hypr() {
    local addr
    addr=$(hyprctl -j clients 2>/dev/null | jq -r --arg re "^($IDE_IDS)$" '
        [.[] | select((.class // "") | test($re))] | first | .address // empty')
    [ -n "$addr" ] || return 1
    hyprctl dispatch focuswindow "address:$addr" >/dev/null 2>&1
}

case "$ACTION" in
    summary)
        summary
        ;;
    focus)
        if [ -n "${NIRI_SOCKET:-}" ] && focus_niri; then
            exit 0
        fi
        if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && focus_hypr; then
            exit 0
        fi
        summary
        ;;
    *)
        echo "usage: ${0##*/} [focus|summary]" >&2
        exit 2
        ;;
esac
