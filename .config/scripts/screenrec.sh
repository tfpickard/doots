#!/usr/bin/env bash
# Toggle screen recording on niri.
#
#   screenrec.sh region   # slurp-selected area
#   screenrec.sh screen   # focused output
#
# Re-running while a recording is active stops it. The recorder is sent SIGINT
# so it can write the container trailer -- SIGKILL would leave a corrupt file.
#
# Primary backend is wl-screenrec (VAAPI hardware encoding); wf-recorder is used
# as a fallback if it is unavailable.

set -uo pipefail

export PATH="$HOME/.cargo/bin:$PATH"

mode="${1:-region}"
outdir="${RECORDING_DIR:-$HOME/Videos/Recordings}"
runtime="${XDG_RUNTIME_DIR:-/tmp}"
pidfile="$runtime/screenrec.pid"
namefile="$runtime/screenrec.name"
logfile="$runtime/screenrec.log"

notify() { notify-send -a "Screen Recorder" "$@" >/dev/null 2>&1 || true; }
die() { notify "Recording failed" "$1"; exit 1; }

# ------------------------------------------------------------- stop branch ---
if [[ -r "$pidfile" ]]; then
    pid=$(<"$pidfile")
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid" 2>/dev/null

        # Give the encoder up to 15s to flush and finalise.
        for _ in $(seq 1 150); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null

        file=$(cat "$namefile" 2>/dev/null)
        rm -f "$pidfile" "$namefile"

        if [[ -n "$file" && -s "$file" ]]; then
            printf '%s' "$file" | wl-copy
            notify "Recording saved" "$(basename "$file") — path copied to clipboard"
        else
            notify "Recording stopped" "No data was written"
        fi
        exit 0
    fi
    # Stale pidfile from a crashed recorder.
    rm -f "$pidfile" "$namefile"
fi

# ------------------------------------------------------------ start branch ---
mkdir -p "$outdir" || die "Cannot create $outdir"
file="$outdir/Recording $(date '+%Y-%m-%d %H-%M-%S').mp4"

# Resolve the capture target before spawning anything. Both wl-screenrec and
# wf-recorder accept -g <geometry> and -o <output>.
declare -a target
case "$mode" in
    region)
        geom=$(slurp -d 2>/dev/null) || exit 0
        [[ -n "$geom" ]] || exit 0
        target=(-g "$geom")
        label="Region"
        ;;
    screen)
        name=$(niri msg --json focused-output 2>/dev/null | jq -r '.name // empty')
        [[ -n "$name" ]] || die "Could not determine the focused output"
        target=(-o "$name")
        label="Full screen ($name)"
        ;;
    *)
        die "Unknown mode '$mode' (expected 'region' or 'screen')"
        ;;
esac

if command -v wl-screenrec >/dev/null 2>&1; then
    # --low-power=off skips a probe that always fails on this Intel iGPU.
    wl-screenrec --low-power=off "${target[@]}" -f "$file" >"$logfile" 2>&1 &
elif command -v wf-recorder >/dev/null 2>&1; then
    wf-recorder "${target[@]}" -f "$file" >"$logfile" 2>&1 &
else
    die "Neither wl-screenrec nor wf-recorder is installed"
fi
pid=$!

# Confirm the recorder survived startup before reporting success.
sleep 0.5
if ! kill -0 "$pid" 2>/dev/null; then
    die "$(tail -n 3 "$logfile" 2>/dev/null)"
fi

printf '%s' "$pid"  >"$pidfile"
printf '%s' "$file" >"$namefile"
notify "Recording started" "$label — press the same keys again to stop"
