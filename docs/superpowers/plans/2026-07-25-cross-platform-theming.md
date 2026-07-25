# Cross-Platform Theming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `theme-set` theme system run correctly on macOS and Linux, with no machine-specific state committed to git and both platforms verified in CI.

**Architecture:** `theme-set` gains a capability dispatch table pairing a probe command with a target path; an applier runs only when both resolve, so the script needs no `uname` branching. `themes/active` is demoted from a committed absolute symlink to gitignored per-machine state created relatively. Two GNU-only constructs are replaced with portable equivalents.

**Tech Stack:** POSIX-ish bash (must run on macOS bash 3.2), `jq`, GNU Make, GitHub Actions, `shellcheck`.

**Spec:** `docs/superpowers/specs/2026-07-25-cross-platform-theming-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **macOS ships bash 3.2.57 at `/bin/bash`, and `#!/usr/bin/env bash` resolves to it.** Verified on the target machine. This forbids, in every shell file this plan touches:
  - `declare -A` / associative arrays — fails with `declare: -A: invalid option`, exit 2
  - `mapfile` / `readarray` — fails with `command not found`, exit 127
  - `${var,,}` / `${var^^}` case modification — parse error, `bad substitution`
- **Never `cmd | while read ...` when the loop body mutates state.** bash 3.2 runs the right-hand side of a pipeline in a subshell, so mutations are lost. Use `while read ...; done <<< "$(cmd)"` instead. Verified: pipeline yields `n=0`, herestring yields `n=2`.
- **No GNU-only tool flags.** Specifically banned: `find -printf`, `sed -i`. BSD `find` exits with `find: -printf: unknown primary or operator`.
- **`mktemp "$file.XXXXXX"`** (template beside the target) is the required temp-file form. Verified working on BSD `mktemp`.
- **No new runtime dependencies.** `jq` is already required and present. `shellcheck` is a CI-only dependency.
- **Committed symlinks must have relative targets.** This is the defect that motivated the work; Task 10 adds a CI assertion for it.
- **Git tracks `Makefile` only.** `makefile` is the same inode on case-insensitive APFS — edit `Makefile`.
- **Theme colors do not change.** No task may alter a hex value in any `themes/*/` snippet.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `tests/lib.sh` | Assertion helpers + sandbox construction. No external deps. |
| `tests/test-theme-set.sh` | All `theme-set` behavioral tests. |
| `tests/run.sh` | Discovers and runs `tests/test-*.sh`, aggregates exit status. |
| `.config/themes/default/tmux.conf` | Fallback tmux colors for a fresh clone before `theme-set` runs. |
| `.config/fuzzel/fuzzel.ini` | Non-color fuzzel settings + `include=` of the active theme snippet. |
| `.config/gtk-4.0/gtk.css` | Symlink to `../themes/active/gtk.css`. |
| `.config/bottom/bottom.toml` | bottom config carrying the `theme-set:colors` marker block. |
| `.config/fastfetch/config.jsonc` | fastfetch config carrying `"keys"` / `"title"` ANSI values. |
| `.github/workflows/theme.yml` | CI matrix over `ubuntu-latest` + `macos-latest`. |

**Modified:**

| Path | Change |
|---|---|
| `.config/themes/theme-set` | Portable helpers, capability dispatch, `--check`, relative symlink. |
| `.gitignore` | Add `.config/themes/active`. |
| `.tmux.conf:280-283` | `if-shell` gains an else branch pointing at `themes/default`. |
| `Makefile` | Split `CONFIG_DIRS` by platform; add `theme` target; update `MAC_PACKAGES`. |

**Deleted from git (file becomes untracked, not removed from disk):**

| Path | Reason |
|---|---|
| `.config/themes/active` | Machine-specific generated state; absolute `/home/tom` target. |

---

## Task 1: Test harness

No test framework exists in this repo. Everything downstream is TDD, so the harness comes first. It must run on bash 3.2 with nothing installed.

**Files:**
- Create: `tests/lib.sh`
- Create: `tests/run.sh`
- Create: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `assert_eq DESC EXPECTED ACTUAL`, `assert_contains DESC HAYSTACK NEEDLE`, `assert_ok DESC CMD...`, `assert_fails DESC CMD...`, `assert_resolves DESC PATH`, `assert_relative_link DESC PATH`, `summary` (returns non-zero if any test failed), `make_sandbox` (echoes a temp root containing `themes/` and `home/`; caller removes it). `$REPO_ROOT` is exported by `tests/run.sh`.

- [ ] **Step 1: Write the assertion library**

Create `tests/lib.sh`:

```bash
#!/usr/bin/env bash
# Assertion helpers for the dotfiles test suite.
#
# Deliberately dependency-free: these run on macOS's bash 3.2 and on Linux
# bash 5 with nothing installed beyond coreutils. See the plan's Global
# Constraints before adding anything here.

TESTS_RUN=0
TESTS_FAILED=0

_pass() {
    TESTS_RUN=$((TESTS_RUN + 1))
    printf '  ok   %s\n' "$1"
}

_fail() {
    TESTS_RUN=$((TESTS_RUN + 1))
    TESTS_FAILED=$((TESTS_FAILED + 1))
    printf '  FAIL %s\n' "$1"
    printf '       %s\n' "$2"
}

assert_eq() { # desc expected actual
    if [ "$2" = "$3" ]; then _pass "$1"; else _fail "$1" "expected [$2] got [$3]"; fi
}

assert_contains() { # desc haystack needle
    case "$2" in
        *"$3"*) _pass "$1" ;;
        *)      _fail "$1" "expected [$3] within [$2]" ;;
    esac
}

assert_not_contains() { # desc haystack needle
    case "$2" in
        *"$3"*) _fail "$1" "did not expect [$3] within [$2]" ;;
        *)      _pass "$1" ;;
    esac
}

assert_ok() { # desc cmd...
    local desc=$1; shift
    if "$@" >/dev/null 2>&1; then _pass "$desc"; else _fail "$desc" "command failed: $*"; fi
}

assert_fails() { # desc cmd...
    local desc=$1; shift
    if "$@" >/dev/null 2>&1; then _fail "$desc" "expected failure: $*"; else _pass "$desc"; fi
}

assert_resolves() { # desc path
    if [ -e "$2" ]; then
        _pass "$1"
    else
        _fail "$1" "does not resolve: $2 -> $(readlink "$2" 2>/dev/null || echo '(not a symlink)')"
    fi
}

assert_relative_link() { # desc path
    local target
    target=$(readlink "$2" 2>/dev/null || true)
    case "$target" in
        /*) _fail "$1" "absolute link target: $target" ;;
        "") _fail "$1" "not a symlink: $2" ;;
        *)  _pass "$1" ;;
    esac
}

# Copy the themes tree into a temp root alongside an empty fake HOME, so tests
# never touch the real repo or the real ~/.config. Echoes the root.
make_sandbox() {
    local root
    root=$(mktemp -d "${TMPDIR:-/tmp}/theme-set-test.XXXXXX")
    mkdir -p "$root/home"
    cp -R "$REPO_ROOT/.config/themes" "$root/themes"
    rm -f "$root/themes/active"
    printf '%s\n' "$root"
}

summary() {
    printf '\n  %d run, %d failed\n' "$TESTS_RUN" "$TESTS_FAILED"
    [ "$TESTS_FAILED" -eq 0 ]
}
```

- [ ] **Step 2: Write the runner**

Create `tests/run.sh`:

```bash
#!/usr/bin/env bash
# Run every tests/test-*.sh. Exit non-zero if any file reports a failure.
set -uo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT=$(pwd)
export REPO_ROOT

rc=0
for t in tests/test-*.sh; do
    printf '%s\n' "$t"
    bash "$t" || rc=1
done
exit "$rc"
```

- [ ] **Step 3: Write the first failing test**

Create `tests/test-theme-set.sh`. This asserts the harness itself works, and
that `theme-set --list` succeeds — which currently fails on macOS with
`find: -printf: unknown primary or operator`.

```bash
#!/usr/bin/env bash
# Behavioral tests for .config/themes/theme-set
set -uo pipefail
. "$REPO_ROOT/tests/lib.sh"

SANDBOX=$(make_sandbox)
trap 'rm -rf "$SANDBOX"' EXIT
THEME_SET="$SANDBOX/themes/theme-set"

# --- harness sanity ---------------------------------------------------------
assert_eq "harness compares equal strings" "a" "a"

# --- --list -----------------------------------------------------------------
assert_ok "--list exits zero" bash "$THEME_SET" --list

summary
```

- [ ] **Step 4: Run it to verify it fails**

```bash
chmod +x tests/run.sh tests/test-theme-set.sh
./tests/run.sh
```

Expected on macOS: `ok   harness compares equal strings`, then
`FAIL --list exits zero`, then `1 failed`, exit status 1.

- [ ] **Step 5: Commit the harness (still red)**

```bash
git add tests/
git commit -m "test: add dependency-free shell test harness

Runs on macOS bash 3.2 and Linux bash 5 with nothing installed. The
--list test fails on macOS today because theme-set uses GNU find -printf;
Task 2 fixes that."
```

---

## Task 2: Portable `list_themes`

**Files:**
- Modify: `.config/themes/theme-set:18-20`
- Test: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: `assert_ok`, `assert_contains`, `assert_not_contains`, `make_sandbox` from Task 1.
- Produces: `list_themes()` — prints one theme directory name per line, sorted, excluding the `active` symlink.

- [ ] **Step 1: Write the failing tests**

Replace the `--list` section of `tests/test-theme-set.sh` with:

```bash
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
./tests/run.sh
```

Expected on macOS: all four `--list includes` assertions FAIL, because `find -printf` errors before printing anything.

- [ ] **Step 3: Implement the portable version**

In `.config/themes/theme-set`, replace lines 18-20 with:

```bash
# List theme directory names. `active` is a symlink-to-directory and must be
# excluded: `find -type d` did that implicitly (find does not follow symlinks),
# but the glob below matches it, so the -L guard is load-bearing.
list_themes() {
    local d
    for d in "$THEMES_DIR"/*/; do
        d=${d%/}
        [ -L "$d" ] && continue
        [ -d "$d" ] || continue
        printf '%s\n' "${d##*/}"
    done | sort
}
```

- [ ] **Step 4: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: all five `--list` assertions pass, `0 failed`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add .config/themes/theme-set tests/test-theme-set.sh
git commit -m "fix(theme-set): replace GNU find -printf with a portable glob

BSD find rejects -printf, so --list and the fuzzel picker were both dead
on macOS. The -L guard preserves the old behavior of excluding the
active symlink, which find gave us for free."
```

---

## Task 3: Portable `sed_inplace`

**Files:**
- Modify: `.config/themes/theme-set` (add helper after `list_themes`)
- Test: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `sed_inplace FILE SED_ARGS...` — applies `sed` to `FILE` in place; returns non-zero and leaves `FILE` untouched if `sed` fails.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test-theme-set.sh`, before `summary`:

```bash
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
./tests/run.sh
```

Expected: FAIL with `command failed: sed_inplace ...` — the function does not exist yet, and `THEME_SET_LIB=1 . "$THEME_SET"` will run the whole script.

- [ ] **Step 3: Implement**

In `.config/themes/theme-set`, add after `list_themes`:

```bash
# In-place sed that works with both BSD and GNU sed, which disagree on -i.
# The temp file is created beside the target so the rename stays on one
# filesystem: a cross-filesystem mv degrades to copy+unlink, changing the
# inode and clobbering permissions.
sed_inplace() {
    local f=$1; shift
    local t
    t=$(mktemp "$f.XXXXXX") || return 1
    if sed "$@" "$f" >"$t" 2>/dev/null; then
        mv "$t" "$f"
    else
        rm -f "$t"
        return 1
    fi
}
```

Add the library guard at the **end of the function definitions, immediately before the `case "${1:-}"` dispatch block**, so every function is defined before the early return:

```bash
# Sourcing with THEME_SET_LIB=1 defines the helpers and stops here, so the
# test suite can exercise them directly.
if [ -n "${THEME_SET_LIB:-}" ]; then
    return 0 2>/dev/null || true
fi
```

- [ ] **Step 4: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: all five `sed_inplace` assertions pass, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add .config/themes/theme-set tests/test-theme-set.sh
git commit -m "fix(theme-set): add BSD/GNU-portable sed_inplace helper

BSD sed -i requires a backup-suffix argument and GNU sed -i forbids one,
so the two are mutually incompatible. Writing to a sibling temp file and
renaming works on both, and keeps the replace atomic."
```

---

## Task 4: Relative `active` symlink, gitignored

**Files:**
- Modify: `.config/themes/theme-set:37` (the `ln -sfn` line)
- Modify: `.gitignore`
- Delete from index: `.config/themes/active`
- Test: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: Task 1 helpers, `list_themes` from Task 2.
- Produces: after `theme-set NAME`, `$THEMES_DIR/active` is a symlink whose target is the bare theme name.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test-theme-set.sh`, before `summary`:

```bash
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
./tests/run.sh
```

Expected: `FAIL active symlink is relative — absolute link target: /Users/.../themes/cyberdream`.

- [ ] **Step 3: Implement the relative link**

In `.config/themes/theme-set`, replace line 37:

```bash
ln -sfn "$THEMES_DIR/$theme" "$THEMES_DIR/active"
```

with:

```bash
# 1. Flip the master symlink. Everything else hangs off it. The link is
#    created *relative* so it stores no machine identity and resolves
#    identically under /home/tom and /Users/tom.
( cd "$THEMES_DIR" && ln -sfn "$theme" active )
```

- [ ] **Step 4: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: all five `active symlink` assertions pass.

- [ ] **Step 5: Untrack the committed symlink and ignore it**

```bash
git rm --cached .config/themes/active
```

Add to `.gitignore`, directly beneath the existing `os/active` entry:

```gitignore
# Active theme selection, created by `make theme` / `theme-set` (per-machine)
.config/themes/active
```

- [ ] **Step 6: Verify the working tree is clean and the link still works**

```bash
git status --short .config/themes/
readlink .config/themes/active
```

Expected: `git status` shows only the `.gitignore` and `theme-set` modifications — no `.config/themes/active` entry. `readlink` still prints whatever the local machine last selected.

- [ ] **Step 7: Commit**

```bash
git add .gitignore .config/themes/theme-set tests/test-theme-set.sh
git commit -m "fix(theme-set): make active a relative, gitignored symlink

It was committed as -> /home/tom/doots/..., which cannot resolve under
/Users/tom, so it and the three symlinks chained through it all dangled
on macOS. Demoting it to per-machine generated state matches how
.config/ghostty/os/active is already handled, and stops theme switches
from dirtying the worktree."
```

---

## Task 5: Capability dispatch and `--check`

The core restructure. Existing apply steps become named appliers behind a table.

**Files:**
- Modify: `.config/themes/theme-set` (steps 2-9 become applier functions; add table + dispatch)
- Test: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: `sed_inplace` (Task 3), relative-link behavior (Task 4).
- Produces:
  - `appliers_table()` — emits `name|probe|target|function` lines, one per applier.
  - `applier_skip_reason PROBE TARGET` — echoes empty if usable, else a reason string.
  - `check_appliers()` — prints `apply`/`skip` per applier; changes nothing; exits 0.
  - `run_appliers()` — runs each usable applier, prints `ok`/`skip`/`ERROR`.
  - `pal KEY` — echoes `.KEY` from `$PALETTE`.
  - Applier functions: `apply_ghostty`, `apply_tmux`, `apply_bottom`, `apply_fastfetch`, `apply_niri`, `apply_waybar`, `apply_mako`, `apply_fuzzel`, `apply_gtk`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test-theme-set.sh`, before `summary`:

```bash
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
```

- [ ] **Step 2: Run to verify it fails**

```bash
./tests/run.sh
```

Expected: `FAIL --check exits zero` — `--check` is not a recognized argument, so the script treats it as a theme name and exits 1 with `No such theme: --check`.

- [ ] **Step 3: Rewrite `theme-set` around the dispatch table**

Replace the entire contents of `.config/themes/theme-set` with:

```bash
#!/usr/bin/env bash
# theme-set — global theme switcher.
#
# Colors live in themes/<name>/. Switching is: flip the themes/active symlink,
# then poke each application that can pick the change up.
#
# Applications are *discovered*, not assumed. The APPLIERS table pairs a probe
# command with a target path, and an applier runs only when both are present.
# That is why this script contains no uname branching: macOS simply resolves
# fewer appliers than a Wayland desktop does.
#
# Usage:
#   theme-set            fuzzel picker of available themes
#   theme-set aura       switch directly
#   theme-set --list     list theme names
#   theme-set --check    report which appliers resolve here; change nothing
#
# Portability: must run on macOS's bash 3.2. No associative arrays, no
# mapfile, no ${var,,}, no GNU-only find/sed flags. Loops that mutate state
# use herestrings, never pipelines (bash 3.2 subshells the RHS of a pipe).
set -euo pipefail

THEMES_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# ------------------------------------------------------------------ helpers --

# List theme directory names. `active` is a symlink-to-directory and must be
# excluded: `find -type d` did that implicitly (find does not follow symlinks),
# but the glob below matches it, so the -L guard is load-bearing.
list_themes() {
    local d
    for d in "$THEMES_DIR"/*/; do
        d=${d%/}
        [ -L "$d" ] && continue
        [ -d "$d" ] || continue
        printf '%s\n' "${d##*/}"
    done | sort
}

pick_theme() {
    list_themes | fuzzel --dmenu --prompt="theme> " --lines=8
}

# In-place sed that works with both BSD and GNU sed, which disagree on -i.
# The temp file is created beside the target so the rename stays on one
# filesystem: a cross-filesystem mv degrades to copy+unlink, changing the
# inode and clobbering permissions.
sed_inplace() {
    local f=$1; shift
    local t
    t=$(mktemp "$f.XXXXXX") || return 1
    if sed "$@" "$f" >"$t" 2>/dev/null; then
        mv "$t" "$f"
    else
        rm -f "$t"
        return 1
    fi
}

hex2ansi() { # "#rrggbb" -> "38;2;r;g;b"
    local h="${1#\#}"
    printf '38;2;%d;%d;%d' "0x${h:0:2}" "0x${h:2:2}" "0x${h:4:2}"
}

pal() { jq -r ".$1" "$PALETTE"; }

# ----------------------------------------------------------------- appliers --
# Applications that read themes/active directly need no poking; flipping the
# symlink is the entire operation for them.
apply_ghostty() { :; }   # reload with ctrl+shift+, or open a new window
apply_fuzzel()  { :; }   # include= is re-read on next launch
apply_gtk()     { :; }   # symlink is re-read on next launch

apply_mako()   { makoctl reload 2>/dev/null || true; }
apply_waybar() { pkill -USR2 -x waybar 2>/dev/null || true; }

apply_tmux() {
    local sock
    for sock in $(find "/tmp/tmux-$(id -u)" -type s 2>/dev/null); do
        tmux -S "$sock" source-file "$THEMES_DIR/active/tmux.conf" 2>/dev/null || true
    done
}

# niri has no include mechanism, so its color lines carry // THEME: markers
# that get rewritten in place.
apply_niri() {
    local accent overlay red grad grad_line
    accent=$(pal accent)
    overlay=$(pal overlay)
    red=$(pal red)

    # A theme opts into a focus-ring gradient by adding a "focus_gradient"
    # object to palette.json. The tagged line becomes either a live
    # active-gradient node or a comment.
    grad=$(jq -r '
        if .focus_gradient then
            "active-gradient from=\"\(.focus_gradient.from)\" to=\"\(.focus_gradient.to)\" angle=\(.focus_gradient.angle // 45) relative-to=\"workspace-view\" in=\"oklch longer hue\""
        else "" end' "$PALETTE")
    if [ -n "$grad" ]; then
        grad_line="        $grad // THEME:focus-gradient"
    else
        grad_line="        // no focus gradient for this theme // THEME:focus-gradient"
    fi

    sed_inplace "$HOME/.config/niri/config.kdl" \
        -e "s|\(active-color \)\"[^\"]*\"\( // THEME:focus-active\)|\1\"$accent\"\2|" \
        -e "s|\(inactive-color \)\"[^\"]*\"\( // THEME:focus-inactive\)|\1\"$overlay\"\2|" \
        -e "s|\(urgent-color \)\"[^\"]*\"\( // THEME:focus-urgent\)|\1\"$red\"\2|" \
        -e "s|^.*// THEME:focus-gradient\$|$grad_line|"
    niri msg action load-config-file >/dev/null 2>&1 || true
}

# bottom has no include mechanism either; regenerate its [colors] block
# between the theme-set markers.
apply_bottom() {
    local cfg="$HOME/.config/bottom/bottom.toml" block t
    grep -q "# >>> theme-set:colors" "$cfg" || return 0
    block=$(jq -r '
        "table_header_color = \"\(.accent)\"",
        "widget_title_color = \"\(.text)\"",
        "avg_cpu_color = \"\(.red)\"",
        "cpu_core_colors = [\"\(.accent)\", \"\(.accent2)\", \"\(.green)\", \"\(.orange)\", \"\(.blue)\", \"\(.pink)\", \"\(.yellow)\", \"\(.subtext)\"]",
        "ram_color = \"\(.accent)\"",
        "swap_color = \"\(.orange)\"",
        "gpu_core_colors = [\"\(.green)\", \"\(.blue)\", \"\(.pink)\"]",
        "rx_color = \"\(.accent2)\"",
        "tx_color = \"\(.green)\"",
        "border_color = \"\(.surface)\"",
        "highlighted_border_color = \"\(.accent)\"",
        "text_color = \"\(.text)\"",
        "selected_text_color = \"\(.bg)\"",
        "selected_bg_color = \"\(.accent)\"",
        "graph_color = \"\(.overlay)\"",
        "high_battery_color = \"\(.green)\"",
        "medium_battery_color = \"\(.orange)\"",
        "low_battery_color = \"\(.red)\""
    ' "$PALETTE")
    t=$(mktemp "$cfg.XXXXXX") || return 1
    awk -v block="$block" '
        /# >>> theme-set:colors/ { print; print "[colors]"; print block; skip=1; next }
        /# <<< theme-set:colors/ { skip=0; print; next }
        !skip { print }
    ' "$cfg" >"$t" && mv "$t" "$cfg"
}

apply_fastfetch() {
    local cfg="$HOME/.config/fastfetch/config.jsonc" keys_ansi title_ansi
    keys_ansi=$(hex2ansi "$(pal accent)")
    title_ansi=$(hex2ansi "$(pal green)")
    sed_inplace "$cfg" -E \
        -e "s|(\"keys\"[[:space:]]*:[[:space:]]*\")[0-9;]*(\")|\1$keys_ansi\2|" \
        -e "s|(\"title\"[[:space:]]*:[[:space:]]*\")[0-9;]*(\")|\1$title_ansi\2|"
}

# ----------------------------------------------------------------- dispatch --
# name|probe command ("-" = no command probe)|target path|apply function
appliers_table() {
    cat <<EOF
ghostty|ghostty|$HOME/.config/ghostty|apply_ghostty
tmux|tmux|$HOME/.tmux.conf|apply_tmux
bottom|btm|$HOME/.config/bottom/bottom.toml|apply_bottom
fastfetch|fastfetch|$HOME/.config/fastfetch/config.jsonc|apply_fastfetch
niri|niri|$HOME/.config/niri/config.kdl|apply_niri
waybar|waybar|$HOME/.config/waybar|apply_waybar
mako|makoctl|$HOME/.config/mako|apply_mako
fuzzel|fuzzel|$HOME/.config/fuzzel|apply_fuzzel
gtk|-|$HOME/.config/gtk-4.0|apply_gtk
EOF
}

# Echo nothing if the applier is usable here, else a human-readable reason.
applier_skip_reason() { # probe target
    if [ "$1" != "-" ] && ! command -v "$1" >/dev/null 2>&1; then
        printf '%s not installed' "$1"
    elif [ ! -e "$2" ]; then
        printf '%s missing' "$2"
    fi
}

check_appliers() {
    local name probe target fn reason
    while IFS='|' read -r name probe target fn; do
        [ -z "$name" ] && continue
        reason=$(applier_skip_reason "$probe" "$target")
        if [ -z "$reason" ]; then
            printf '  apply  %-10s\n' "$name"
        else
            printf '  skip   %-10s (%s)\n' "$name" "$reason"
        fi
    done <<< "$(appliers_table)"
}

run_appliers() {
    local name probe target fn reason
    while IFS='|' read -r name probe target fn; do
        [ -z "$name" ] && continue
        reason=$(applier_skip_reason "$probe" "$target")
        if [ -n "$reason" ]; then
            printf '  skip   %-10s (%s)\n' "$name" "$reason"
            continue
        fi
        if "$fn"; then
            printf '  ok     %-10s\n' "$name"
        else
            printf '  ERROR  %-10s\n' "$name" >&2
        fi
    done <<< "$(appliers_table)"
}

# Sourcing with THEME_SET_LIB=1 defines the helpers and stops here, so the
# test suite can exercise them directly.
if [ -n "${THEME_SET_LIB:-}" ]; then
    return 0 2>/dev/null || true
fi

# --------------------------------------------------------------------- main --
case "${1:-}" in
    --list)  list_themes; exit 0 ;;
    --check) check_appliers; exit 0 ;;
    "")      theme="$(pick_theme)" || exit 1 ;;
    *)       theme="$1" ;;
esac

[ -d "$THEMES_DIR/$theme" ] || { echo "No such theme: $theme" >&2; exit 1; }
PALETTE="$THEMES_DIR/$theme/palette.json"
[ -f "$PALETTE" ] || { echo "Theme $theme has no palette.json" >&2; exit 1; }

# Flip the master symlink. Everything else hangs off it. Created *relative* so
# it stores no machine identity and resolves under /home/tom and /Users/tom.
( cd "$THEMES_DIR" && ln -sfn "$theme" active )

run_appliers

command -v notify-send >/dev/null 2>&1 && \
    notify-send "Theme switched" "Now using: $theme" || true
echo "Theme set to: $theme"
```

- [ ] **Step 4: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: every assertion passes, `0 failed`, exit 0.

- [ ] **Step 5: Verify `--check` against the real machine**

```bash
.config/themes/theme-set --check
```

Expected on macOS: `apply` for `ghostty` and `tmux`; `skip` with reasons for `bottom`, `fastfetch`, `niri`, `waybar`, `mako`, `fuzzel`, `gtk`. (`bottom` and `fastfetch` flip to `apply` after Task 8.)

- [ ] **Step 6: Commit**

```bash
git add .config/themes/theme-set tests/test-theme-set.sh
git commit -m "refactor(theme-set): capability dispatch instead of assumed apps

Each applier declares a probe command and a target path and runs only
when both resolve, so the script needs no uname branching: macOS gets
four appliers, a Wayland desktop nine, a headless box two.

--check prints the same table without applying, so the diagnostic cannot
drift from the behavior and CI can assert it directly."
```

---

## Task 6: tmux fallback theme

Today `~/.tmux.conf` guards its theme source with `if-shell [ -e ]` and no else
branch, so macOS silently gets stock tmux colors.

**Files:**
- Create: `.config/themes/default/tmux.conf`
- Modify: `.tmux.conf:280-283`
- Test: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: `list_themes` (Task 2).
- Produces: `themes/default/` — a fallback directory containing only `tmux.conf`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test-theme-set.sh`, before `summary`:

```bash
# --- default fallback theme -------------------------------------------------
assert_resolves "default tmux fallback exists" "$REPO_ROOT/.config/themes/default/tmux.conf"

TMUXCONF=$(cat "$REPO_ROOT/.tmux.conf")
assert_contains "tmux sources the active theme"   "$TMUXCONF" "themes/active/tmux.conf"
assert_contains "tmux falls back to the default"  "$TMUXCONF" "themes/default/tmux.conf"

# `default` is a fallback, not a selectable theme: it ships only tmux.conf and
# has no palette.json, so `theme-set default` would fail. It must not be
# offered by --list or the fuzzel picker, and Task 10's CI applies every listed
# theme, so listing it would break CI.
LIST=$(bash "$THEME_SET" --list 2>&1)
assert_not_contains "--list excludes the default fallback" "$LIST" "default"
assert_fails "default is not selectable" \
    env HOME="$SANDBOX/home" bash "$THEME_SET" default
```

- [ ] **Step 2: Run to verify it fails**

```bash
./tests/run.sh
```

Expected: `FAIL default tmux fallback exists` and `FAIL tmux falls back to the default`. The two `--list` assertions pass vacuously for now — `default/` does not exist yet — and will start failing the moment Step 3 creates it, which Step 4a then fixes.

- [ ] **Step 3: Create the fallback theme**

Create `.config/themes/default/tmux.conf`. These are the colors the branch
deleted from `.tmux.conf` (the former `SLEEZ_*` palette), preserved so a fresh
clone is styled rather than stock:

```tmux
# default — tmux fallback colors, used when themes/active does not exist yet
# (fresh clone, before `make theme` or `theme-set` has run). Kept deliberately
# minimal: tmux is the only consumer that needs a pre-theme-set default.
set -g status-style "bg=#1a0d2e,fg=#c9a9dd"
set -g pane-border-style "fg=#352040"
set -g pane-active-border-style "fg=#00e5ff"
set -g message-style "bg=#00e5ff,fg=#1a0d2e"
set -g message-command-style "bg=#69ff94,fg=#1a0d2e"
setw -g window-status-style "fg=#ce93d8,bg=#2d1b3d"
setw -g window-status-current-style "bg=#ce93d8,fg=#1a0d2e,bold"
setw -g window-status-activity-style "bg=#ffeb3b,fg=#1a0d2e"
setw -g mode-style "bg=#00e5ff,fg=#1a0d2e"
set -g clock-mode-colour "#7dffb3"
set -g status-left "#{prefix_highlight} #[fg=#7dffb3,bg=#2d1b3d,bold] #S #[default]"
```

- [ ] **Step 4a: Teach `list_themes` what a theme is**

Creating `default/` just made `--list` offer an unselectable entry. Tighten the
definition: a theme is a directory that has a palette. In
`.config/themes/theme-set`, add one line to `list_themes`:

```bash
list_themes() {
    local d
    for d in "$THEMES_DIR"/*/; do
        d=${d%/}
        [ -L "$d" ] && continue
        [ -d "$d" ] || continue
        # A theme is a directory with a palette. This excludes `default/`,
        # which ships only a tmux fallback, and any stray directory.
        [ -f "$d/palette.json" ] || continue
        printf '%s\n' "${d##*/}"
    done | sort
}
```

- [ ] **Step 4b: Add the else branch**

In `.tmux.conf`, replace:

```tmux
if-shell '[ -e ~/.config/themes/active/tmux.conf ]' \
  'source-file ~/.config/themes/active/tmux.conf'
```

with:

```tmux
# Theme colors follow the active global theme. If it has not been selected on
# this machine yet, fall back to the committed default so a fresh clone is
# styled rather than dropping to stock tmux colors silently.
if-shell '[ -e ~/.config/themes/active/tmux.conf ]' \
  'source-file ~/.config/themes/active/tmux.conf' \
  'source-file ~/.config/themes/default/tmux.conf'
```

- [ ] **Step 5: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: all four fallback assertions pass.

- [ ] **Step 6: Verify tmux actually parses it**

```bash
tmux -f .tmux.conf -L themetest start-server \; show-options -g status-style \; kill-server
```

Expected: prints a `status-style` value (not an error). On this Mac, with
`~/.config/themes` absent, that value comes from the default fallback.

- [ ] **Step 7: Commit**

```bash
git add .config/themes/default/ .tmux.conf tests/test-theme-set.sh
git commit -m "fix(tmux): fall back to a committed default theme

The if-shell guard had no else branch, so on any machine without
~/.config/themes the branch's theme rework left tmux at stock colors
with no diagnostic. Restores the former palette as themes/default."
```

---

## Task 7: Wire the fuzzel and GTK orphans

`fuzzel.ini` and `gtk.css` ship for all four themes but nothing reads them.
Both snippet headers already document the intended mechanism.

**Files:**
- Create: `.config/fuzzel/fuzzel.ini`
- Create: `.config/gtk-4.0/gtk.css` (symlink)
- Test: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: relative-link behavior (Task 4).
- Produces: two consumers that resolve into `themes/active/`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test-theme-set.sh`, before `summary`:

```bash
# --- orphan snippets are wired ----------------------------------------------
assert_relative_link "gtk.css is a relative symlink" "$REPO_ROOT/.config/gtk-4.0/gtk.css"
assert_eq "gtk.css points into themes/active" "../themes/active/gtk.css" \
    "$(readlink "$REPO_ROOT/.config/gtk-4.0/gtk.css")"

FUZZEL=$(cat "$REPO_ROOT/.config/fuzzel/fuzzel.ini")
assert_contains "fuzzel includes the active theme" "$FUZZEL" \
    "include=../themes/active/fuzzel.ini"

# Every theme must ship both snippets, or switching to one breaks a consumer.
for t in aura catppuccin-mocha cyberdream dreamcore-pastel; do
    assert_resolves "theme $t ships fuzzel.ini" "$REPO_ROOT/.config/themes/$t/fuzzel.ini"
    assert_resolves "theme $t ships gtk.css"    "$REPO_ROOT/.config/themes/$t/gtk.css"
done
```

- [ ] **Step 2: Run to verify it fails**

```bash
./tests/run.sh
```

Expected: `FAIL gtk.css is a relative symlink — not a symlink` and
`FAIL fuzzel includes the active theme`. The eight per-theme snippet
assertions pass, since those files already exist.

- [ ] **Step 3: Create the fuzzel consumer**

Create `.config/fuzzel/fuzzel.ini`. Colors are deliberately absent — they come
from the include:

```ini
# fuzzel — launcher. Colors are NOT set here; they come from the active global
# theme via the include below, which `theme-set` repoints by flipping the
# themes/active symlink.
font=JetBrainsMono Nerd Font:size=12
dpi-aware=no
prompt=">  "
icon-theme=Papirus-Dark
terminal=ghostty
layer=overlay
lines=12
width=45
horizontal-pad=24
vertical-pad=16
inner-pad=8

[border]
width=2
radius=12

include=../themes/active/fuzzel.ini
```

- [ ] **Step 4: Create the GTK consumer**

```bash
mkdir -p .config/gtk-4.0
ln -sfn ../themes/active/gtk.css .config/gtk-4.0/gtk.css
```

- [ ] **Step 5: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: all twelve assertions in this section pass.

- [ ] **Step 6: Verify the chain resolves end to end**

```bash
.config/themes/theme-set cyberdream >/dev/null
ls -l .config/gtk-4.0/gtk.css
test -e .config/gtk-4.0/gtk.css && echo "gtk.css resolves"
```

Expected: prints `gtk.css resolves`.

- [ ] **Step 7: Commit**

```bash
git add .config/fuzzel/ .config/gtk-4.0/ tests/test-theme-set.sh
git commit -m "feat(themes): wire the fuzzel and gtk snippets to consumers

Both snippets shipped for all four themes with nothing reading them --
8 committed files that were dead weight. Each snippet header already
documented its intended mechanism (fuzzel include=, gtk-4.0 symlink);
this just connects them."
```

---

## Task 8: Ship bottom and fastfetch configs

The appliers patch `~/.config/bottom/bottom.toml` and
`~/.config/fastfetch/config.jsonc`, but neither file exists in the repo, so on
macOS there is nothing to theme.

**Files:**
- Create: `.config/bottom/bottom.toml`
- Create: `.config/fastfetch/config.jsonc`
- Modify: `Makefile` (`MAC_PACKAGES`)
- Test: `tests/test-theme-set.sh`

**Interfaces:**
- Consumes: `apply_bottom`, `apply_fastfetch`, `pal`, `hex2ansi` (Task 5).
- Produces: two configs carrying the markers the appliers already expect.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test-theme-set.sh`, before `summary`:

```bash
# --- bottom / fastfetch configs ---------------------------------------------
BOTTOM_SRC="$REPO_ROOT/.config/bottom/bottom.toml"
FF_SRC="$REPO_ROOT/.config/fastfetch/config.jsonc"
assert_resolves "bottom config ships"    "$BOTTOM_SRC"
assert_resolves "fastfetch config ships" "$FF_SRC"
assert_contains "bottom has an opening marker" "$(cat "$BOTTOM_SRC")" "# >>> theme-set:colors"
assert_contains "bottom has a closing marker"  "$(cat "$BOTTOM_SRC")" "# <<< theme-set:colors"
assert_contains "fastfetch has a keys field"   "$(cat "$FF_SRC")" "\"keys\""
assert_contains "fastfetch has a title field"  "$(cat "$FF_SRC")" "\"title\""

# Applying a theme into a populated sandbox HOME must rewrite both.
mkdir -p "$SANDBOX/home/.config/bottom" "$SANDBOX/home/.config/fastfetch"
cp "$BOTTOM_SRC" "$SANDBOX/home/.config/bottom/bottom.toml"
cp "$FF_SRC"     "$SANDBOX/home/.config/fastfetch/config.jsonc"
HOME="$SANDBOX/home" bash "$THEME_SET" cyberdream >/dev/null 2>&1 || true

# cyberdream accent is #bd5eff -> 189;94;255
assert_contains "fastfetch keys got the accent ANSI" \
    "$(cat "$SANDBOX/home/.config/fastfetch/config.jsonc")" "38;2;189;94;255"
assert_contains "bottom got the accent hex" \
    "$(cat "$SANDBOX/home/.config/bottom/bottom.toml")" "#bd5eff"
assert_contains "bottom markers survive rewriting" \
    "$(cat "$SANDBOX/home/.config/bottom/bottom.toml")" "# <<< theme-set:colors"
```

- [ ] **Step 2: Run to verify it fails**

```bash
./tests/run.sh
```

Expected: `FAIL bottom config ships` and `FAIL fastfetch config ships`, plus the marker and rewrite assertions.

- [ ] **Step 3: Create the bottom config**

Create `.config/bottom/bottom.toml`. The `[colors]` block between the markers is
regenerated by `theme-set`; do not hand-edit it:

```toml
# bottom — system monitor.
#
# Everything between the theme-set markers below is REGENERATED by
# `theme-set`; edits there are overwritten on the next theme switch. Put
# durable settings outside the markers.

[flags]
group_processes = false
case_sensitive = false
whole_word = false
regex = true
temperature_type = "c"
rate = 1000
tree = false
mem_as_value = false
battery = true

# >>> theme-set:colors
[colors]
# <<< theme-set:colors
```

- [ ] **Step 4: Create the fastfetch config**

Create `.config/fastfetch/config.jsonc`. The two ANSI strings are rewritten by
`theme-set`:

```jsonc
{
  "$schema": "https://github.com/fastfetch-cli/fastfetch/raw/dev/doc/json_schema.json",
  // "keys" and "title" colors are rewritten by theme-set from the active
  // palette. Other display settings are durable.
  "display": {
    "separator": "  ",
    "color": {
      "keys": "38;2;189;94;255",
      "title": "38;2;94;255;108"
    }
  },
  "modules": [
    "title",
    "separator",
    "os",
    "host",
    "kernel",
    "uptime",
    "shell",
    "terminal",
    "cpu",
    "memory",
    "disk",
    "break",
    "colors"
  ]
}
```

- [ ] **Step 5: Add both to `MAC_PACKAGES`**

In `Makefile`, add `bottom` to line 14 (after `bat`) and replace `neofetch`
with `fastfetch` on line 16. The branch already aliases `neofetch=fastfetch` in
`.zshrc:414`, and neofetch is archived upstream.

Line 14 — replace:

```make
MAC_PACKAGES := 1password-cli alacritty awscli bat docker docker-buildx \
```

with:

```make
MAC_PACKAGES := 1password-cli alacritty awscli bat bottom docker docker-buildx \
```

Line 16 — replace:

```make
				ghostty gzip haha lolcat lazygit lua-lang uage-server neofetch neovim nmap \
```

with:

```make
				ghostty gzip haha lolcat lazygit lua-lang uage-server fastfetch neovim nmap \
```

Leave the other entries on that line exactly as they are. Several are already
mangled (`lua-lang uage-server`, `ef`, `fg`, `haha`); fixing them is a separate
concern and changing them here would broaden this task's blast radius.

- [ ] **Step 6: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: all nine assertions in this section pass.

- [ ] **Step 7: Verify `--check` now resolves them**

```bash
mkdir -p ~/.config/bottom ~/.config/fastfetch
cp .config/bottom/bottom.toml ~/.config/bottom/
cp .config/fastfetch/config.jsonc ~/.config/fastfetch/
.config/themes/theme-set --check
```

Expected: `bottom` and `fastfetch` now show `skip ... btm not installed` /
`fastfetch not installed` rather than `... missing` — the target resolved, the
binary did not. After `brew install bottom fastfetch` they show `apply`.

- [ ] **Step 8: Commit**

```bash
git add .config/bottom/ .config/fastfetch/ Makefile tests/test-theme-set.sh
git commit -m "feat(themes): ship bottom and fastfetch configs

theme-set patched ~/.config/bottom/bottom.toml and
~/.config/fastfetch/config.jsonc in place, but neither was tracked, so
on a fresh machine there was nothing for the appliers to act on. Adds
both with the markers the appliers already expect, and swaps the
archived neofetch for fastfetch in MAC_PACKAGES."
```

---

## Task 9: Platform-aware deploy

`CONFIG_DIRS` deploys Wayland configs onto macOS and omits every directory this
branch added. `alacritty` and `rofi` are listed but do not exist in the repo.

**Files:**
- Modify: `Makefile` (`CONFIG_DIRS`, new `theme` target, `all`)
- Test: `tests/test-makefile.sh` (new)

**Interfaces:**
- Consumes: `theme-set` (Task 5).
- Produces: `make theme [THEME=name]`; `CONFIG_DIRS` resolved per platform.

- [ ] **Step 1: Write the failing tests**

Create `tests/test-makefile.sh`:

```bash
#!/usr/bin/env bash
# Deploy-logic tests. These only inspect resolved make variables and dry-run
# output; nothing is symlinked into the real HOME.
set -uo pipefail
. "$REPO_ROOT/tests/lib.sh"

cd "$REPO_ROOT"

darwin_dirs() { make -s show-config-dirs UNAME_S=Darwin 2>/dev/null; }
linux_dirs()  { make -s show-config-dirs UNAME_S=Linux  2>/dev/null; }

D=$(darwin_dirs)
L=$(linux_dirs)

assert_contains "darwin deploys ghostty"   "$D" "ghostty"
assert_contains "darwin deploys themes"    "$D" "themes"
assert_contains "darwin deploys scripts"   "$D" "scripts"
assert_contains "darwin deploys bottom"    "$D" "bottom"
assert_contains "darwin deploys fastfetch" "$D" "fastfetch"

assert_not_contains "darwin skips niri"   "$D" "niri"
assert_not_contains "darwin skips waybar" "$D" "waybar"
assert_not_contains "darwin skips mako"   "$D" "mako"
assert_not_contains "darwin skips hypr"   "$D" "hypr"

assert_contains "linux deploys niri"   "$L" "niri"
assert_contains "linux deploys waybar" "$L" "waybar"
assert_contains "linux deploys mako"   "$L" "mako"
assert_contains "linux deploys gtk-4.0" "$L" "gtk-4.0"

# Dropped: neither directory exists in the repo.
assert_not_contains "alacritty is dropped" "$L" "alacritty"
assert_not_contains "rofi is dropped"      "$L" "rofi"

# Every deployed dir must actually exist, or make symlinks silently skips it.
for d in $L; do
    assert_resolves "deployed dir $d exists" "$REPO_ROOT/.config/$d"
done

assert_ok "make theme target exists" make -n theme

summary
```

- [ ] **Step 2: Run to verify it fails**

```bash
chmod +x tests/test-makefile.sh
./tests/run.sh
```

Expected: every assertion fails — `show-config-dirs` is not a target yet, so both variables are empty.

- [ ] **Step 3: Split `CONFIG_DIRS` and add the targets**

In `Makefile`, replace the `CONFIG_DIRS := ...` line with:

```make
# Config dirs deployed everywhere, and those that only make sense on Linux.
# Wayland compositors and their satellites (niri, waybar, mako, fuzzel, GTK)
# have no macOS equivalent, so shipping them there just clutters ~/.config.
# alacritty and rofi were listed historically but no longer exist in the repo.
COMMON_CONFIG_DIRS := nvim ghostty themes scripts bottom fastfetch
LINUX_CONFIG_DIRS  := hypr niri waybar mako fuzzel gtk-4.0 dunst
CONFIG_DIRS := $(COMMON_CONFIG_DIRS) \
               $(if $(filter Darwin,$(UNAME_S)),,$(LINUX_CONFIG_DIRS))
```

Add these targets (and add `theme` to `.PHONY`):

```make
# Materialize .config/themes/active. It is gitignored per-machine state, so a
# fresh clone has no active theme until this runs.
theme:
	@echo "🎨 Setting theme..."
	@$(DOTFILES_DIR)/.config/themes/theme-set $(or $(THEME),cyberdream)

# Introspection hook for tests/test-makefile.sh.
show-config-dirs:
	@echo $(CONFIG_DIRS)
```

Update the `all` target so the theme exists before ghostty is wired:

```make
all: deps backup symlinks theme ghostty nvim
```

- [ ] **Step 4: Run to verify it passes**

```bash
./tests/run.sh
```

Expected: all assertions in `tests/test-makefile.sh` pass.

- [ ] **Step 5: Verify the real dry run**

```bash
make -n theme
make -s show-config-dirs
```

Expected: `make -n theme` echoes the `theme-set cyberdream` invocation without
running it. `show-config-dirs` on this Mac prints exactly
`nvim ghostty themes scripts bottom fastfetch` with no Wayland entries.

- [ ] **Step 6: Commit**

```bash
git add Makefile tests/test-makefile.sh
git commit -m "build: deploy config dirs per platform, add make theme

CONFIG_DIRS pushed Wayland configs (hypr, waybar) onto macOS while
omitting every directory this branch added -- themes, niri, mako,
scripts -- so make symlinks deployed none of the theme system anywhere.
Drops alacritty and rofi, which no longer exist in the repo."
```

---

## Task 10: CI matrix

**Files:**
- Create: `.github/workflows/theme.yml`

**Interfaces:**
- Consumes: `tests/run.sh` (Task 1), `theme-set --check` (Task 5).
- Produces: required status checks on PRs into `master`.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/theme.yml`:

```yaml
name: theme

on:
  pull_request:
  push:
    branches: [master]

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - name: Install shellcheck (macOS)
        if: runner.os == 'macOS'
        run: brew install shellcheck

      - name: Install shellcheck (Linux)
        if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y shellcheck

      - name: Report bash version
        # macOS runners ship bash 3.2 as /bin/bash. If this ever reports 4+,
        # the portability constraints in the plan need revisiting.
        run: bash --version | head -1

      - name: Shellcheck
        run: |
          shellcheck .config/themes/theme-set
          shellcheck tests/*.sh
          shellcheck .config/scripts/*.sh

      - name: No absolute symlink targets committed
        # The regression that motivated this work: .config/themes/active was
        # committed as -> /home/tom/doots/..., which cannot resolve on macOS.
        run: |
          bad=$(git ls-tree -r HEAD | awk '$1 == "120000" { print $4 }' | while read -r f; do
            t=$(git show "HEAD:$f")
            case "$t" in /*) printf '%s -> %s\n' "$f" "$t" ;; esac
          done)
          if [ -n "$bad" ]; then
            echo "Absolute symlink targets are not portable:" >&2
            echo "$bad" >&2
            exit 1
          fi
          echo "All committed symlinks are relative."

      - name: Test suite
        run: ./tests/run.sh

      - name: theme-set --check runs clean
        run: .config/themes/theme-set --check

      - name: Every theme applies and leaves links resolvable
        run: |
          for t in $(.config/themes/theme-set --list); do
            echo "--- $t"
            .config/themes/theme-set "$t"
            test -e .config/themes/active/palette.json \
              || { echo "active/palette.json unresolved after $t" >&2; exit 1; }
            test -e .config/ghostty/theme/active \
              || { echo "ghostty/theme/active unresolved after $t" >&2; exit 1; }
            test -e .config/gtk-4.0/gtk.css \
              || { echo "gtk-4.0/gtk.css unresolved after $t" >&2; exit 1; }
          done
```

- [ ] **Step 2: Verify the workflow parses**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/theme.yml')); print('valid yaml')"
```

Expected: `valid yaml`.

- [ ] **Step 3: Run the CI steps locally where possible**

```bash
./tests/run.sh
.config/themes/theme-set --check
git ls-tree -r HEAD | awk '$1 == "120000" { print $4 }' | while read -r f; do
  t=$(git show "HEAD:$f"); case "$t" in /*) echo "ABSOLUTE: $f -> $t";; esac
done; echo "symlink audit done"
```

Expected: tests pass, `--check` exits 0, and the audit prints only
`symlink audit done` with no `ABSOLUTE:` lines.

- [ ] **Step 4: Commit and push**

```bash
git add .github/workflows/theme.yml
git commit -m "ci: verify theming on ubuntu and macos

PR #5 had no status checks at all. Runs shellcheck, the test suite, and
theme-set --check on both platforms, applies every theme, and asserts no
committed symlink has an absolute target -- the exact regression that
broke macOS.

Note: the runners have neither niri nor waybar, so those appliers are
skipped rather than exercised. CI proves the dispatch and portability
layers; the Wayland apply functions still need a manual run on Linux."
git push
```

- [ ] **Step 5: Confirm the checks run green**

```bash
gh pr checks 5 --watch
```

Expected: both `test (ubuntu-latest)` and `test (macos-latest)` pass.

---

## Post-Implementation Verification

Run on macOS, then repeat on the Linux machine:

```bash
./tests/run.sh                              # all green
.config/themes/theme-set --list             # 4 themes; `default` excluded
.config/themes/theme-set --check            # sensible apply/skip per platform
.config/themes/theme-set cyberdream         # applies, no errors
readlink .config/themes/active              # "cyberdream" — no leading slash
git status --short                          # clean except the deferred niri case
test -e .config/ghostty/theme/active && echo ghostty-ok
test -e .config/gtk-4.0/gtk.css && echo gtk-ok
```

Against the spec's success criteria:

1. `--list` / `<name>` succeed on both — Tasks 2, 4, verified by Task 10 CI.
2. `--check` reports correctly per platform — Task 5.
3. No committed symlink is absolute — Task 4, asserted by Task 10 CI.
4. Fresh clone + `make` yields themed ghostty and tmux — Tasks 6, 9.
5. CI green on both runners — Task 10.
6. Theme switching leaves the worktree clean — Task 4.

**Known gap, by design:** switching themes on Linux still dirties
`.config/niri/config.kdl`, because `apply_niri` rewrites a tracked file. This is
the spec's deferred work and needs its own issue — extract the four `// THEME:`
lines into a gitignored `.config/niri/theme.kdl` include, once niri's include
support is confirmed on the Linux box.
