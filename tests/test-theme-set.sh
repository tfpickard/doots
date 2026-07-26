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

# --- sed_inplace: permissions must be preserved ------------------------------
# mktemp creates the temp file 0600; a naive mv onto the target carries that
# mode along, silently downgrading a 644 file to owner-only.
PERM_FILE="$SANDBOX/perm.txt"
printf 'alpha\n' > "$PERM_FILE"
chmod 644 "$PERM_FILE"
MODE_BEFORE=$(ls -l "$PERM_FILE" | awk '{print $1}')
assert_ok "sed_inplace succeeds on a 644 file" sed_inplace "$PERM_FILE" -e 's/alpha/gamma/'
MODE_AFTER=$(ls -l "$PERM_FILE" | awk '{print $1}')
assert_eq "sed_inplace preserves the original file mode" "$MODE_BEFORE" "$MODE_AFTER"

# --- sed_inplace: a symlink target must stay a symlink -----------------------
# mv'ing the temp file over a symlink path replaces the link with a plain
# file, orphaning whatever it used to point at. The real file behind the
# link must receive the edit instead, and the link itself must survive.
REAL_FILE="$SANDBOX/real-target.txt"
printf 'alpha\n' > "$REAL_FILE"
LINK_FILE="$SANDBOX/link-to-real.txt"
ln -s "$REAL_FILE" "$LINK_FILE"
assert_ok "sed_inplace succeeds through a symlink" sed_inplace "$LINK_FILE" -e 's/alpha/gamma/'
if [ -L "$LINK_FILE" ]; then LINK_STATE=symlink; else LINK_STATE=not-a-symlink; fi
assert_eq "sed_inplace leaves the path a symlink" "symlink" "$LINK_STATE"
assert_eq "sed_inplace edits the file the symlink points to" "gamma" "$(cat "$REAL_FILE")"

# --- sed_inplace: a failing mv must not leak the temp file -------------------
# The sed-failure path already cleans up (asserted above); the mv-failure
# path must too. Override `mv` as a shell function so the failure is
# deterministic and portable (no filesystem trickery required).
MVFAIL_FILE="$SANDBOX/mvfail.txt"
printf 'alpha\n' > "$MVFAIL_FILE"
mv() { return 1; }
assert_fails "sed_inplace reports mv failure" sed_inplace "$MVFAIL_FILE" -e 's/alpha/gamma/'
unset -f mv
assert_eq "sed_inplace leaves no temp file after mv failure" "" "$(find "$SANDBOX" -name 'mvfail.txt.*' 2>/dev/null)"
assert_eq "sed_inplace leaves the original intact after mv failure" "alpha" "$(cat "$MVFAIL_FILE")"

summary
