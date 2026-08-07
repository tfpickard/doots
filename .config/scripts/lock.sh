#!/usr/bin/env bash
# Lock the screen, picking the nicest locker that is actually installed.
#
# Bound to Super+Alt+L, and used by the swayidle line in the niri config.
#
#   lock.sh              use $LOCKER, else the first available (see ORDER)
#   lock.sh effects      swaylock-effects: blurred desktop + clock
#   lock.sh swaylock     plain swaylock (packaged, always present)
#   lock.sh gtklock      GTK lock, CSS-styled, clock, idle-hides the form
#   lock.sh -f           daemonize (what swayidle passes)
#
# Set a default without editing this file:
#   export LOCKER=swaylock        (in ~/.extra or ~/.exports)
#
# Whichever runs, the screensaver hack is stopped first: while the session is
# locked the compositor renders only the lock surface, so a running GL hack is
# invisible and just burns the GPU.

set -u

ORDER="effects swaylock gtklock"

have() { command -v "$1" >/dev/null 2>&1; }

stop_screensaver() {
    [ -x "$HOME/.config/scripts/lock-screensaver.py" ] && \
        "$HOME/.config/scripts/lock-screensaver.py" stop 2>/dev/null
    return 0
}

# --- Parse our own arguments ----------------------------------------------
# -f/--daemonize has to be RECOGNISED and FORWARDED, not swallowed: swayidle
# uses it for before-sleep and waits for that command to return before letting
# the system suspend. A locker left in the foreground would block suspend until
# you unlocked, which is exactly backwards.
daemonize=0
choice="${LOCKER:-}"

while [ $# -gt 0 ]; do
    case "$1" in
        -f|--daemonize)           daemonize=1 ;;
        effects|swaylock|gtklock) choice="$1" ;;
        *)                        break ;;
    esac
    shift
done

# --- Silicon Graphics backgrounds ------------------------------------------
#
# Populates $SGI_ARGS with one "-i <output>:<path>" pair per connected monitor.
# The images are generated at each output's exact resolution by
# lock-background.py, which is why they're passed per output rather than
# letting swaylock scale one picture across three differently-shaped screens.
#
# Set SGI_LOCK=0 to skip this and get the plain configured background (or, for
# swaylock-effects with `screenshots` uncommented, the blurred desktop).
SGI_ARGS=""

sgi_backgrounds() {
    SGI_ARGS=""
    [ "${SGI_LOCK:-1}" = "0" ] && return 0

    gen="$HOME/.config/scripts/lock-background.py"
    [ -x "$gen" ] || return 0

    # Cheap when everything is current: it only re-renders images that are
    # missing or older than the source wallpaper.
    "$gen" >/dev/null 2>&1 || return 0

    cache="$HOME/.cache/sgi-lock"
    [ -d "$cache" ] || return 0

    # Ask niri which outputs exist rather than globbing the cache, so a stale
    # image for a disconnected monitor is never passed to swaylock.
    have niri || return 0
    for out in $(niri msg --json outputs 2>/dev/null \
                 | python3 -c 'import json,sys
try:
    print("\n".join(json.load(sys.stdin).keys()))
except Exception:
    pass' 2>/dev/null); do
        [ -f "$cache/$out.png" ] && SGI_ARGS="$SGI_ARGS -i $out:$cache/$out.png"
    done
}

# gtklock needs a different approach to the same background.
#
# swaylock takes `-i <output>:<path>` and so gets an image rendered at each
# monitor's exact resolution. gtklock has no such option: its background comes
# from CSS, and it uses ONE `window` selector for every monitor -- it does not
# name its windows per output, so there is nothing to target per screen.
#
# So render a single image at the size of the LARGEST connected output and let
# `background-size: cover` crop it down on the smaller ones. That is only
# acceptable because the artwork is a logo on a flat field: cropping moves the
# logo a little, but the field colour is identical everywhere, and the CSS also
# sets background-color to the same blue so any rounding gap is invisible.
SGI_GTKLOCK_STYLE=""

sgi_gtklock_background() {
    SGI_GTKLOCK_STYLE=""
    [ "${SGI_LOCK:-1}" = "0" ] && return 0

    css="$HOME/.config/gtklock/style.css"
    gen="$HOME/.config/scripts/lock-background.py"
    [ -x "$gen" ] || return 0
    [ -r "$css" ] || return 0
    have niri || return 0

    # Largest connected output, by pixel area.
    size=$(niri msg --json outputs 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    best = max((o["logical"] for o in d.values() if o.get("logical")),
               key=lambda l: l["width"] * l["height"])
    print("%dx%d" % (best["width"], best["height"]))
except Exception:
    pass' 2>/dev/null)
    [ -n "$size" ] || return 0

    img="$HOME/.cache/sgi-lock/$size.png"
    [ -f "$img" ] || "$gen" --size "$size" >/dev/null 2>&1
    [ -f "$img" ] || return 0

    # Point the CSS at it, but only in a COPY under the cache -- rewriting the
    # tracked stylesheet would leave a machine-specific resolution in the
    # working tree after every lock, which shows up as a spurious git diff.
    # The tagged line is the only thing substituted.
    live="$HOME/.cache/sgi-lock/gtklock-style.css"
    python3 - "$css" "$img" "$live" <<'PY' 2>/dev/null || return 0
import re, sys
src, image, dst = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src) as fh:
    css = fh.read()
css = re.sub(
    r'(/\* SGI:background \*/\n\s*background-image:\s*url\(")[^"]*("\);)',
    lambda m: m.group(1) + image + m.group(2),
    css,
    count=1,
)
with open(dst, "w") as fh:
    fh.write(css)
PY
    [ -f "$live" ] && SGI_GTKLOCK_STYLE="$live"
}

run_effects() {
    [ -x "$HOME/.local/bin/swaylock-effects" ] || return 1
    set -- -C "$HOME/.config/swaylock-effects/config"
    [ "$daemonize" -eq 1 ] && set -- "$@" -f

    sgi_backgrounds
    # Unquoted on purpose: SGI_ARGS is a list of separate arguments.
    # shellcheck disable=SC2086
    [ -n "$SGI_ARGS" ] && set -- "$@" $SGI_ARGS

    "$HOME/.local/bin/swaylock-effects" "$@"
}

run_swaylock() {
    have swaylock || return 1
    set -- -C "$HOME/.config/swaylock/config"
    [ "$daemonize" -eq 1 ] && set -- "$@" -f

    sgi_backgrounds
    # shellcheck disable=SC2086
    [ -n "$SGI_ARGS" ] && set -- "$@" $SGI_ARGS

    swaylock "$@"
}

run_gtklock() {
    have gtklock || return 1

    sgi_gtklock_background

    # -i is REQUIRED on niri: gtklock 2.1.0 otherwise tries to use
    # wlr-input-inhibitor, which niri does not implement, and aborts with
    # "Your compositor doesn't support wlr-input-inhibitor".
    # gtklock spells daemonize -d, not -f.
    set -- -i -c "$HOME/.config/gtklock/config.ini"
    # -s overrides the `style` line in config.ini, pointing gtklock at the
    # generated copy with the right background baked in.
    [ -n "$SGI_GTKLOCK_STYLE" ] && set -- "$@" -s "$SGI_GTKLOCK_STYLE"
    [ "$daemonize" -eq 1 ] && set -- "$@" -d
    gtklock "$@"
}

stop_screensaver

if [ -n "$choice" ]; then
    case "$choice" in
        effects)  run_effects && exit 0 ;;
        swaylock) run_swaylock && exit 0 ;;
        gtklock)  run_gtklock && exit 0 ;;
        *) echo "unknown locker: $choice" >&2; exit 1 ;;
    esac
    echo "requested locker '$choice' unavailable, falling back" >&2
fi

# Fall through the preference order. Never leave the screen UNLOCKED just
# because a fancy locker is missing or broken.
for l in $ORDER; do
    case "$l" in
        effects)  run_effects && exit 0 ;;
        swaylock) run_swaylock && exit 0 ;;
        gtklock)  run_gtklock && exit 0 ;;
    esac
done

echo "no screen locker available!" >&2
exit 1
