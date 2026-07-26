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

summary
