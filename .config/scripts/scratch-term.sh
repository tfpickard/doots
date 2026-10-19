#!/bin/sh
# Quake-style scratch terminals on persistent tmux sessions.
#
#   scratch-term.sh        Mod+Space        centred floating window, session "scratch"
#   scratch-term.sh full   Mod+Shift+Space  fills the working area, session "scratch-full"
#
# The first press spawns the terminal. Later presses summon it, or, if it
# already has focus, park it on the hidden named workspace "scratch" and hand
# focus back to whatever had it before. The two are independent: own window,
# own tmux session.
#
# It is summoned onto a display that does NOT hold the focus, so the window
# you are working in stays visible next to it (see pick_output):
#   2+ externals  the nearest other external screen (never the laptop panel)
#   1 external    the other of the two displays, whichever that is
#   0 externals   the only display there is
#
#   scratch-term.sh pick-output FOCUSED < outputs.json
# prints the display that rule picks, for tests/test-scratch-term.sh.
set -eu

# $1 = focused output name; stdin = `niri msg -j outputs`. Disabled outputs
# (lid shut) have no logical geometry and are skipped. Ranked by the gap
# between screen edges, so a screen that touches the focused one beats a
# farther one; then by centre distance, then left-to-right, top-to-bottom,
# so the choice is stable.
pick_output() {
    jq -r --arg f "$1" '
        def internal: .name | test("^(eDP|LVDS|DSI)");
        def gap($a; $b): ([0, $a.x - ($b.x + $b.width), $b.x - ($a.x + $a.width)] | max)
                       + ([0, $a.y - ($b.y + $b.height), $b.y - ($a.y + $a.height)] | max);
        def centre($r): [$r.x + $r.width / 2, $r.y + $r.height / 2];
        [.[] | select(.logical != null)] as $on
        | (first($on[] | select(.name == $f)) // null) as $fo
        | ([$on[] | select(internal | not)] | length) as $m
        | [$on[] | select(.name != $f) | select($m < 2 or (internal | not))] as $c
        | if $fo == null or ($c | length) == 0 then $f
          else $c
            | map(. as $o | {name, l: .logical,
                    gap: gap($o.logical; $fo.logical),
                    d: ([centre($o.logical), centre($fo.logical)]
                        | transpose | map((.[0] - .[1]) * (.[0] - .[1])) | add)})
            | sort_by([.gap, .d, .l.x, .l.y]) | first.name
          end'
}

if [ "${1:-}" = pick-output ]; then
    pick_output "$2"
    exit
fi

# Sizes are re-applied on every summon, because a floating window keeps its
# pixel size when it moves to a differently-sized screen. Keep these in step
# with the default-column-width / default-window-height in niri's rules.
case ${1:-float} in
float)
    app_id=dev.tom.scratch session=scratch width=70% height=65%
    ;;
full)
    app_id=dev.tom.scratch-full session=scratch-full width=100% height=100%
    ;;
*)
    echo "usage: ${0##*/} [float|full]" >&2
    exit 2
    ;;
esac
variant=${1:-float}
app_id=${SCRATCH_APP_ID:-$app_id}
session=${SCRATCH_SESSION:-$session}
hide_ws=${SCRATCH_HIDE_WS:-scratch}
# Who had focus before the last summon, so hiding can hand it back.
prev_file=${XDG_RUNTIME_DIR:-/tmp}/scratch-term.$variant.prev

win=$(niri msg -j windows |
    jq -r --arg a "$app_id" 'first(.[] | select(.app_id == $a) | .id) // empty')
focused=$(niri msg -j focused-window | jq -r '.id // empty')
focused_out=$(niri msg -j focused-output | jq -r '.name // empty')

if [ -n "$win" ] && [ "$win" = "$focused" ]; then
    niri msg action move-window-to-workspace --window-id "$win" --focus false "$hide_ws"
    if [ -s "$prev_file" ]; then
        read -r prev_win prev_out < "$prev_file" || true
        niri msg action focus-window --id "$prev_win" 2>/dev/null ||
            niri msg action focus-monitor "$prev_out" 2>/dev/null || true
    fi
    exit 0
fi

printf '%s %s\n' "${focused:-none}" "$focused_out" > "$prev_file"
target=$(niri msg -j outputs | pick_output "$focused_out")

if [ -z "$win" ]; then
    # Focus the target screen first: niri opens new windows on the focused
    # output, and the window rule then floats and sizes it there.
    [ "$target" = "$focused_out" ] || niri msg action focus-monitor "$target"
    # A distinct --class keeps ghostty from folding this into the main
    # single-instance process, so window rules can tell it apart.
    # --config-file loads last, so the scratch colours and shader win.
    # detach-on-destroy is off globally; without the session override,
    # exiting the last shell here would hop this window onto another session.
    exec ghostty --class="$app_id" --gtk-single-instance=false \
        --config-file="$HOME/.config/ghostty/scratch/$variant" \
        -e tmux new-session -A -s "$session" \; set-option detach-on-destroy on
fi

read -r idx name <<EOF
$(niri msg -j workspaces | jq -r --arg o "$target" \
    '.[] | select(.output == $o and .is_active) | "\(.idx) \(.name // "")"')
EOF

# move-window-to-monitor lands on that screen's active workspace, unless the
# window is already on that screen (say, parked on "scratch" there). The
# workspace move covers that case. A bare index resolves on the window's own
# screen, which by now is the target.
niri msg action move-window-to-monitor --id "$win" "$target"
niri msg action move-window-to-workspace --window-id "$win" --focus false "${name:-$idx}"
niri msg action set-window-width --id "$win" "$width"
niri msg action set-window-height --id "$win" "$height"
niri msg action center-window --id "$win"
niri msg action focus-window --id "$win"
