#!/usr/bin/env bash
# Capture a screenshot via niri's own screenshot UI, then open it in satty.
#
# niri's UI is used rather than grim+slurp on purpose: it freezes the frame the
# instant the key is pressed and can snap the selection to a window. slurp grabs
# the pointer, which dismisses any open menu/tooltip, and cannot freeze.

set -uo pipefail

export PATH="$HOME/.cargo/bin:$PATH"

notify() { notify-send -a "Screenshot" "$@" >/dev/null 2>&1 || true; }

outdir="${SCREENSHOT_DIR:-$HOME/Pictures/Screenshots}"
mkdir -p "$outdir" || { notify "Screenshot failed" "Cannot create $outdir"; exit 1; }
file="$outdir/Screenshot from $(date '+%Y-%m-%d %H-%M-%S').png"

if ! command -v satty >/dev/null 2>&1; then
    notify "Screenshot failed" "satty is not installed"
    exit 1
fi

# The action returns immediately; the file only appears once the user confirms.
if ! niri msg action screenshot --path "$file" >/dev/null 2>&1; then
    notify "Screenshot failed" "niri rejected the screenshot action"
    exit 1
fi

# Wait up to 60s for a capture. No file means the user pressed Escape.
for _ in $(seq 1 600); do
    [[ -s "$file" ]] && break
    sleep 0.1
done
[[ -s "$file" ]] || exit 0

# Wait for the size to settle so satty never opens a half-written PNG.
prev=""
for _ in $(seq 1 40); do
    size=$(stat -c %s "$file" 2>/dev/null)
    [[ "$size" == "$prev" ]] && break
    prev="$size"
    sleep 0.05
done

exec satty --filename "$file" --output-filename "$file" \
           --copy-command wl-copy --early-exit all
