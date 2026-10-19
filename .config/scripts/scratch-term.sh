#!/bin/sh
# Quake-style drop-down terminal on a persistent tmux session.
# First press spawns it, then each press summons it to the focused workspace
# or, if it already has focus, parks it on a hidden named workspace.
set -eu

app_id=${SCRATCH_APP_ID:-dev.tom.scratch}
session=${SCRATCH_SESSION:-scratch}
hide_ws=${SCRATCH_HIDE_WS:-scratch}

win=$(niri msg -j windows |
    jq -r --arg a "$app_id" 'first(.[] | select(.app_id == $a) | .id) // empty')

if [ -z "$win" ]; then
    # A distinct --class keeps ghostty from folding this into the main
    # single-instance process, so the window rule can tell it apart.
    # detach-on-destroy is off globally; without the session override,
    # exiting the last shell here would hop this window onto another session.
    exec ghostty --class="$app_id" --gtk-single-instance=false \
        -e tmux new-session -A -s "$session" \; set-option detach-on-destroy on
fi

focused=$(niri msg -j focused-window | jq -r '.id // empty')
if [ "$win" = "$focused" ]; then
    niri msg action move-window-to-workspace --window-id "$win" --focus false "$hide_ws"
    exit 0
fi

read -r out idx name <<EOF
$(niri msg -j workspaces | jq -r '.[] | select(.is_focused) | "\(.output) \(.idx) \(.name // "")"')
EOF

# Workspace indexes are per-output, so land on the right output before an
# index means anything.
niri msg action move-window-to-monitor --id "$win" "$out"
niri msg action move-window-to-workspace --window-id "$win" --focus false "${name:-$idx}"
niri msg action focus-window --id "$win"
