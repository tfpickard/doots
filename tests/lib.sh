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
