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

# --- active symlink ---------------------------------------------------------
HOME="$SANDBOX/home" bash "$THEME_SET" cyberdream >/dev/null 2>&1 || true
assert_relative_link "active symlink is relative" "$SANDBOX/themes/active"
assert_eq "active points at the bare theme name" "cyberdream" \
    "$(readlink "$SANDBOX/themes/active")"
assert_resolves "active resolves" "$SANDBOX/themes/active/palette.json"

HOME="$SANDBOX/home" bash "$THEME_SET" aura >/dev/null 2>&1 || true
assert_eq "active follows a second switch" "aura" \
    "$(readlink "$SANDBOX/themes/active")"

assert_fails "unknown theme is rejected" \
    env HOME="$SANDBOX/home" bash "$THEME_SET" no-such-theme

# --- --check ----------------------------------------------------------------
CHECK=$(HOME="$SANDBOX/home" bash "$THEME_SET" --check 2>&1) || CHECK="EXIT-FAILURE: $CHECK"
assert_ok "--check exits zero" env HOME="$SANDBOX/home" bash "$THEME_SET" --check

# The sandbox HOME is empty, so every applier must skip with a reason.
for a in ghostty tmux bottom fastfetch niri waybar mako fuzzel gtk; do
    assert_contains "--check reports applier $a" "$CHECK" "$a"
done
assert_contains "--check gives a skip reason" "$CHECK" "skip"

# --check must not create the active symlink or touch HOME.
rm -f "$SANDBOX/themes/active"
HOME="$SANDBOX/home" bash "$THEME_SET" --check >/dev/null 2>&1 || true
assert_fails "--check does not create active" test -L "$SANDBOX/themes/active"
assert_eq "--check leaves HOME empty" "" "$(ls -A "$SANDBOX/home")"

# --- dispatch skips cleanly -------------------------------------------------
OUT=$(HOME="$SANDBOX/home" bash "$THEME_SET" cyberdream 2>&1) || OUT="EXIT-FAILURE: $OUT"
assert_contains "apply run reports skips" "$OUT" "skip"
assert_contains "apply run succeeds"      "$OUT" "Theme set to: cyberdream"

# --- run_appliers: a failing applier must not be swallowed -------------------
# The while loop's last command on every iteration is a `printf`, which
# always succeeds, so run_appliers currently returns 0 even after printing
# ERROR for a failed applier. Exercise it directly with a stub table, in a
# subshell so the overridden functions never leak into later tests.
APPLIER_CALLS="$SANDBOX/applier-calls.txt"
: > "$APPLIER_CALLS"
(
    appliers_table() {
        cat <<EOF
stubok1|-|/|stub_ok1
stubfail|-|/|stub_fail
stubok2|-|/|stub_ok2
EOF
    }
    stub_ok1()  { printf 'ok1\n'  >> "$APPLIER_CALLS"; }
    stub_fail() { printf 'fail\n' >> "$APPLIER_CALLS"; return 1; }
    stub_ok2()  { printf 'ok2\n'  >> "$APPLIER_CALLS"; }
    run_appliers >"$SANDBOX/run-appliers-fail.out" 2>"$SANDBOX/run-appliers-fail.err"
)
RUN_RC=$?
assert_eq "run_appliers returns non-zero when an applier fails" "1" "$RUN_RC"
assert_eq "run_appliers still runs every applier after one fails" "ok1
fail
ok2" "$(cat "$APPLIER_CALLS")"
assert_contains "run_appliers reports the failing applier as ERROR" \
    "$(cat "$SANDBOX/run-appliers-fail.err")" "ERROR"

# --- run_appliers: an all-skip run still exits zero --------------------------
# Skips are not failures; a run where every applier is unusable here must
# still report success.
: > "$APPLIER_CALLS"
(
    appliers_table() {
        cat <<EOF
skipone|no-such-cmd-xyz|/no/such/path|stub_ok1
skiptwo|no-such-cmd-abc|/no/such/other|stub_ok2
EOF
    }
    stub_ok1() { printf 'ok1\n' >> "$APPLIER_CALLS"; }
    stub_ok2() { printf 'ok2\n' >> "$APPLIER_CALLS"; }
    run_appliers >"$SANDBOX/run-appliers-skip.out" 2>&1
)
RUN_RC=$?
assert_eq "run_appliers exits zero when every applier skips" "0" "$RUN_RC"
assert_eq "run_appliers calls no applier functions when every applier skips" \
    "" "$(cat "$APPLIER_CALLS")"
assert_contains "run_appliers output reports the skips" \
    "$(cat "$SANDBOX/run-appliers-skip.out")" "skip"

# --- apply_bottom: awk -v with an embedded newline is not portable -----------
# $block comes from jq -r over many keys and therefore contains embedded
# newlines. macOS's /usr/bin/awk (BWK awk, not gawk) rejects a -v assignment
# containing a literal newline and exits 2 before writing the temp file, so
# the `&& mv` never fires and the config is left untouched. This must
# genuinely fail against the current awk -v implementation.
BOTTOM_CFG="$SANDBOX/home/.config/bottom/bottom.toml"
mkdir -p "$(dirname "$BOTTOM_CFG")"
cat > "$BOTTOM_CFG" <<'EOF'
[some]
other = "stuff"

# >>> theme-set:colors
placeholder = true
# <<< theme-set:colors

[more]
after = "stuff"
EOF

HOME="$SANDBOX/home" PALETTE="$REPO_ROOT/.config/themes/aura/palette.json" apply_bottom
BOTTOM_OUT=$(cat "$BOTTOM_CFG")
assert_contains "apply_bottom writes aura's accent hex between the markers" \
    "$BOTTOM_OUT" "#a277ff"
assert_contains "apply_bottom preserves the opening marker" \
    "$BOTTOM_OUT" "# >>> theme-set:colors"
assert_contains "apply_bottom preserves the closing marker" \
    "$BOTTOM_OUT" "# <<< theme-set:colors"

summary
