#!/usr/bin/env bash
# screenshot-watch: watch the screenshot directory and describe new captures.
#
# Runs as a systemd user service (screenshot-describe.service) and hands every
# new screenshot to screenshot-describe.sh, which renames it to include a short
# AI-generated description.
#
# Only files still carrying niri's bare timestamp name are considered. Once a
# description has been appended the name no longer matches, so a renamed file
# can never be picked up a second time.
#
# Captures are processed one at a time -- inotifywait buffers events in the pipe
# meanwhile -- so a burst of screenshots cannot fire off parallel API calls.

set -uo pipefail

export PATH="$HOME/.local/bin:$PATH"

shotdir="${SCREENSHOT_DIR:-$HOME/Pictures/Screenshots}"
describe="${SHOTDESC_BIN:-$HOME/.config/scripts/screenshot-describe.sh}"
sep="${SHOTDESC_SEP:- -- }"

# niri's default screenshot-path, e.g. "Screenshot from 2026-08-03 11-30-00.png".
pattern='^Screenshot from [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}-[0-9]{2}-[0-9]{2}\.(png|jpg|jpeg)$'

command -v inotifywait >/dev/null 2>&1 || { echo "inotifywait not found" >&2; exit 1; }
[[ -x "$describe" ]] || { echo "not executable: $describe" >&2; exit 1; }

mkdir -p "$shotdir" || exit 1
echo "watching $shotdir"

# Block until nothing holds the file open, so a screenshot being annotated in
# satty is never renamed out from under it.
wait_until_closed() {
    local f=$1
    for _ in $(seq 1 600); do
        fuser -s -- "$f" 2>/dev/null || return 0
        sleep 0.5
    done
    return 1
}

# close_write covers ordinary writes; moved_to covers files staged elsewhere and
# moved in (which is how the satty flow delivers its result).
inotifywait -m -q -e close_write -e moved_to --format '%f' "$shotdir" |
while IFS= read -r name; do
    [[ "$name" =~ $pattern ]] || continue

    file="$shotdir/$name"
    [[ -f "$file" && -s "$file" ]] || continue

    # Let the writer finish, then confirm the size has settled.
    wait_until_closed "$file" || { echo "still open, skipping: $name" >&2; continue; }
    prev=""
    for _ in $(seq 1 40); do
        size=$(stat -c %s "$file" 2>/dev/null) || break
        [[ "$size" == "$prev" ]] && break
        prev="$size"
        sleep 0.05
    done

    # Re-check: a concurrent run may have renamed it already.
    [[ -f "$file" ]] || continue

    "$describe" "$file" >/dev/null 2>&1 \
        || echo "describe failed: $name" >&2
done
