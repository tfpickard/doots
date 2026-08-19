#!/usr/bin/env bash
# Wallpaper control: static (swaybg), animated (awww), or video (mpvpaper).
#
# All three draw to the same wlr-layer-shell background layer, so they are
# mutually exclusive -- whichever starts last wins, and leaving two running
# just burns a GPU. This script stops the others before starting the one you
# asked for.
#
#   wallpaper.sh                     show what's running
#   wallpaper.sh static [PATH]       swaybg, the default (set at login)
#   wallpaper.sh anim PATH           awww: GIF / animated image, with transition
#   wallpaper.sh video PATH          mpvpaper: any video mpv can play
#   wallpaper.sh off                 stop everything, bare background colour
#
# awww is the maintained successor to swww (renamed Oct 2025, now on Codeberg;
# the old GitHub repo is archived). Installed to ~/.local/bin.
#
# NOTE: niri's spawn-sh-at-startup still launches swaybg at login. If you
# settle on an animated wallpaper, change that line in the niri config.

set -u

DEFAULT_WALLPAPER="$HOME/Pictures/Wallpaper/default"
AWWW="$HOME/.local/bin/awww"
AWWW_DAEMON="$HOME/.local/bin/awww-daemon"

have() { command -v "$1" >/dev/null 2>&1 || [ -x "$1" ]; }

stop_all() {
    for name in swaybg mpvpaper awww-daemon; do
        for pid in $(pgrep -x "$name" 2>/dev/null); do
            kill "$pid" 2>/dev/null
        done
    done
    sleep 0.3
}

status() {
    found=0
    for name in swaybg mpvpaper awww-daemon; do
        if pgrep -x "$name" >/dev/null 2>&1; then
            echo "running: $name"
            found=1
        fi
    done
    [ "$found" -eq 0 ] && echo "no wallpaper daemon is running"
    return 0
}

case "${1:-status}" in
    status|"")
        status
        ;;

    off)
        stop_all
        echo "wallpaper stopped"
        ;;

    static)
        img="${2:-$DEFAULT_WALLPAPER}"
        [ -e "$img" ] || { echo "no such file: $img" >&2; exit 1; }
        stop_all
        setsid swaybg -i "$img" -m fill >/dev/null 2>&1 &
        sleep 0.5
        status
        ;;

    anim)
        img="${2:-}"
        [ -n "$img" ] || { echo "usage: $(basename "$0") anim <image-or-gif>" >&2; exit 1; }
        [ -e "$img" ] || { echo "no such file: $img" >&2; exit 1; }
        have "$AWWW_DAEMON" || { echo "awww-daemon not installed (~/.local/bin)" >&2; exit 1; }
        stop_all
        setsid "$AWWW_DAEMON" >/dev/null 2>&1 &
        # The daemon needs to be up and listening before the client talks to it.
        for _ in $(seq 1 30); do
            "$AWWW" query >/dev/null 2>&1 && break
            sleep 0.1
        done
        "$AWWW" img "$img" \
            --transition-type grow \
            --transition-pos 0.5,0.5 \
            --transition-duration 1.5 \
            --transition-fps 60
        status
        ;;

    video)
        vid="${2:-}"
        [ -n "$vid" ] || { echo "usage: $(basename "$0") video <video-file>" >&2; exit 1; }
        [ -e "$vid" ] || { echo "no such file: $vid" >&2; exit 1; }
        have mpvpaper || { echo "mpvpaper is not installed" >&2; exit 1; }
        stop_all
        # '*' = every output. Muted and looping, because a wallpaper that makes
        # noise or stops after one play is a bad wallpaper.
        setsid mpvpaper -o "no-audio loop panscan=1.0" '*' "$vid" >/dev/null 2>&1 &
        sleep 0.5
        status
        ;;

    *)
        echo "usage: $(basename "$0") [status|static PATH|anim PATH|video PATH|off]" >&2
        exit 1
        ;;
esac
