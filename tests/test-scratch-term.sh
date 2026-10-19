#!/usr/bin/env bash
# Tests for which screen .config/scripts/scratch-term.sh summons onto.
set -uo pipefail
. "$REPO_ROOT/tests/lib.sh"

SCRATCH="$REPO_ROOT/.config/scripts/scratch-term.sh"

# The picker is a jq program; jq is a runtime dependency of the script anyway,
# but not of this suite, so skip rather than fail without it.
if ! command -v jq >/dev/null 2>&1; then
    printf '  skip scratch-term: jq not installed\n'
    exit 0
fi

# out NAME X Y W H -> one entry of `niri msg -j outputs` (keyed by name).
out() { printf '"%s":{"name":"%s","logical":{"x":%s,"y":%s,"width":%s,"height":%s}}' "$1" "$1" "$2" "$3" "$4" "$5"; }
off() { printf '"%s":{"name":"%s","logical":null}' "$1" "$1"; }
pick() { printf '{%s}' "$1" | sh "$SCRATCH" pick-output "$2"; }

# --- 0 externals: the only screen --------------------------------------------
LAPTOP=$(out eDP-1 0 0 1920 1200)
assert_eq "0 ext: laptop alone stays on the laptop" "eDP-1" "$(pick "$LAPTOP" eDP-1)"

# --- 1 external: the other of the two ----------------------------------------
ONE="$(out DP-1 0 0 2560 1440),$(out eDP-1 2560 0 1920 1200)"
assert_eq "1 ext: focus on external -> laptop" "eDP-1" "$(pick "$ONE" DP-1)"
assert_eq "1 ext: focus on laptop -> external" "DP-1"  "$(pick "$ONE" eDP-1)"

# Lid shut: the panel is disabled, so only one display is really there.
LID="$(out DP-1 0 0 2560 1440),$(off eDP-1)"
assert_eq "1 ext, lid shut: stays on the external" "DP-1" "$(pick "$LID" DP-1)"

# --- 2 externals (the docked desk): the other external, never the laptop ------
DESK="$(out DP-7 0 0 1920 1080),$(out DP-8 1920 0 1920 1080),$(out eDP-1 3840 0 1920 1200)"
assert_eq "2 ext: left external -> centre external"    "DP-8" "$(pick "$DESK" DP-7)"
assert_eq "2 ext: centre external -> left, not laptop" "DP-7" "$(pick "$DESK" DP-8)"
assert_eq "2 ext: laptop -> the external beside it"    "DP-8" "$(pick "$DESK" eDP-1)"

# --- 3 externals: adjacent beats farther; ties go left-most ------------------
ROW="$(out A 0 0 1920 1080),$(out B 1920 0 1920 1080),$(out C 3840 0 1920 1080),$(out eDP-1 5760 0 1920 1200)"
assert_eq "3 ext: left end -> its neighbour, not the far one" "B" "$(pick "$ROW" A)"
assert_eq "3 ext: middle, two equal neighbours -> left one"  "A" "$(pick "$ROW" B)"
assert_eq "3 ext: right end -> its neighbour"                 "B" "$(pick "$ROW" C)"
assert_eq "3 ext: laptop -> the external beside it"          "C" "$(pick "$ROW" eDP-1)"

# Stacked: the screen sharing an edge wins over a nearer-centred diagonal one.
STACK="$(out TOP 0 0 3840 1080),$(out L 0 1080 1920 1080),$(out R 1920 1080 1920 1080),$(out eDP-1 3840 1080 1920 1200)"
assert_eq "3 ext stacked: of two touching screens, the nearer-centred wins" "TOP" "$(pick "$STACK" R)"

# A touching screen beats a nearer-centred one across a gap.
GAP="$(out F 0 0 100 2000),$(out WIDE 100 0 3000 100),$(out NEAR 150 900 200 200)"
assert_eq "touching screen beats a nearer one across a gap" "WIDE" "$(pick "$GAP" F)"

summary
