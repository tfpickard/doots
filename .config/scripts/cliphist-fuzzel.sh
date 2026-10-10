#!/usr/bin/env bash
# Clipboard history picker: cliphist + fuzzel. Bound to Mod+Semicolon in niri
# and the clipboard icon in waybar.
#   no args : pick an entry and copy it back to the clipboard
#   d       : pick an entry and delete it from history
#   w       : wipe the entire history (with confirmation)
set -euo pipefail

case "${1:-}" in
    d)
        cliphist list | fuzzel --dmenu --prompt="del> " | cliphist delete
        notify-send "Clipboard" "Entry deleted" ;;
    w)
        confirm=$(printf "no\nyes" | fuzzel --dmenu --prompt="wipe clipboard history? " --lines=2)
        [ "$confirm" = "yes" ] && cliphist wipe && notify-send "Clipboard" "History wiped" ;;
    *)
        cliphist list | fuzzel --dmenu --prompt="clip> " | cliphist decode | wl-copy ;;
esac
