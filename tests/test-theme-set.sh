#!/usr/bin/env bash
# Behavioral tests for .config/themes/theme-set
set -uo pipefail
. "$REPO_ROOT/tests/lib.sh"

SANDBOX=$(make_sandbox)
trap 'rm -rf "$SANDBOX"' EXIT
THEME_SET="$SANDBOX/themes/theme-set"

# --- --list -----------------------------------------------------------------
assert_ok "--list exits zero" bash "$THEME_SET" --list

summary
