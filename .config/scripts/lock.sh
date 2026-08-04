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

run_effects() {
    [ -x "$HOME/.local/bin/swaylock-effects" ] || return 1

    set -- -C "$HOME/.config/swaylock-effects/config"
    [ "$daemonize" -eq 1 ] && set -- "$@" -f

    # The config's `screenshots` option does NOT work on niri: swaylock-effects
    # grabs the screen *after* taking the session lock, and while locked niri
    # renders only the lock surface over a solid clear colour
    # (CLEAR_COLOR_LOCKED = [0.3, 0.1, 0.1], dark red -- src/niri.rs). You get
    # a blurred red rectangle instead of your desktop.
    #
    # So capture the desktop ourselves BEFORE locking and pass it in as a
    # background image, which the blur/vignette effects then work on.
    shot=""
    if have grim; then
        shot="$(mktemp -t lockshot-XXXXXX.png)"
        if grim "$shot" 2>/dev/null && [ -s "$shot" ]; then
            set -- "$@" --image "$shot" --scaling fill
        else
            rm -f "$shot"
            shot=""
        fi
    fi

    "$HOME/.local/bin/swaylock-effects" "$@"
    rc=$?

    # The capture is a plaintext picture of your unlocked desktop, so it must
    # not linger in /tmp. swaylock loads the image during startup, and with -f
    # it only returns once the lock surface is up, so removing it here is safe.
    [ -n "$shot" ] && rm -f "$shot"
    return $rc
}

run_swaylock() {
    have swaylock || return 1
    set -- -C "$HOME/.config/swaylock/config"
    [ "$daemonize" -eq 1 ] && set -- "$@" -f
    swaylock "$@"
}

run_gtklock() {
    have gtklock || return 1
    # -i is REQUIRED on niri: gtklock 2.1.0 otherwise tries to use
    # wlr-input-inhibitor, which niri does not implement, and aborts with
    # "Your compositor doesn't support wlr-input-inhibitor".
    # gtklock spells daemonize -d, not -f.
    set -- -i -c "$HOME/.config/gtklock/config.ini"
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
