#!/usr/bin/env bash
# Behavioral tests for .config/themes/theme-set
set -uo pipefail
. "$REPO_ROOT/tests/lib.sh"

SANDBOX=$(make_sandbox)
trap 'rm -rf "$SANDBOX"' EXIT
THEME_SET="$SANDBOX/themes/theme-set"

# --- --list -----------------------------------------------------------------
LIST=$(bash "$THEME_SET" --list 2>&1) || LIST="EXIT-FAILURE: $LIST"
assert_contains "--list includes cyberdream"       "$LIST" "cyberdream"
assert_contains "--list includes aura"             "$LIST" "aura"
assert_contains "--list includes catppuccin-mocha" "$LIST" "catppuccin-mocha"
assert_contains "--list includes dreamcore-pastel" "$LIST" "dreamcore-pastel"

# `active` is a symlink-to-directory. `find -type d` excluded it implicitly;
# a naive glob rewrite would list it as a selectable theme.
( cd "$SANDBOX/themes" && ln -sfn cyberdream active )
LIST=$(bash "$THEME_SET" --list 2>&1) || LIST="EXIT-FAILURE: $LIST"
assert_not_contains "--list excludes the active symlink" "$LIST" "active"
rm -f "$SANDBOX/themes/active"

# --- sed_inplace ------------------------------------------------------------
# Source the script's helpers without running main. THEME_SET_LIB=1 makes the
# script define functions and return before dispatch.
THEME_SET_LIB=1 . "$THEME_SET"

# theme-set sets `set -euo pipefail`, and sourcing leaks that into THIS shell.
# Verified: without the reset below, the first assertion whose command returns
# non-zero kills the test file silently. Restore lenient mode immediately.
set +e +u
set +o pipefail

SCRATCH="$SANDBOX/scratch.txt"
printf 'alpha\nbeta\n' > "$SCRATCH"
assert_ok "sed_inplace succeeds" sed_inplace "$SCRATCH" -e 's/alpha/gamma/'
assert_eq  "sed_inplace rewrote the file" "gamma
beta" "$(cat "$SCRATCH")"

# A failing sed must leave the original intact rather than truncate it.
printf 'alpha\n' > "$SCRATCH"
assert_fails "sed_inplace reports sed failure" sed_inplace "$SCRATCH" -e 's/[/'
assert_eq "sed_inplace left the file intact on failure" "alpha" "$(cat "$SCRATCH")"

# No temp files may survive.
assert_eq "sed_inplace leaves no temp files" "" "$(find "$SANDBOX" -name 'scratch.txt.*' 2>/dev/null)"

summary
