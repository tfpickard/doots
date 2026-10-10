#!/usr/bin/env bash
# Print one random screensaver phrase and exit.
#
# Called as the --program for phosphor/apple2 (see lock-screensaver.py's
# EXTRA_PROVIDERS). Each of those relaunches its --program a few seconds
# after it exits, so returning immediately after one line is what gives the
# rotation -- there is no loop in here on purpose.
#
# The active pool mixes three sources every time this runs, so it's mostly
# fresh, with some legacy and some fixed, per how this was actually asked
# for:
#   - screensaver-phrases.txt      a handful of fixed favourites, always in
#                                   (this file, git-tracked, hand-curated)
#   - the most recent $RECENT_N    from the auto-generated master list --
#     lines of the master list      "mostly new"
#   - $RANDOM_N random lines from  so old ones can still resurface, not just
#     the WHOLE master list          the most recent batch
#
# The master list itself is grown separately, in batches, by
# screensaver-generate-phrases.py (see that file for the schedule/model).
# This script only ever READS it -- never blocks on generation, never calls
# an AI itself.
set -euo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
FIXED_FILE="$SCRIPT_DIR/screensaver-phrases.txt"
MASTER_FILE="$HOME/.local/share/lock-screensaver/phrases-master.txt"

RECENT_N=75
RANDOM_N=5

pool=()

if [ -f "$FIXED_FILE" ]; then
    while IFS= read -r line; do
        [ -n "$line" ] && pool+=("$line")
    done < "$FIXED_FILE"
fi

if [ -f "$MASTER_FILE" ]; then
    while IFS= read -r line; do
        [ -n "$line" ] && pool+=("$line")
    done < <(tail -n "$RECENT_N" "$MASTER_FILE")

    while IFS= read -r line; do
        [ -n "$line" ] && pool+=("$line")
    done < <(shuf -n "$RANDOM_N" "$MASTER_FILE" 2>/dev/null || true)
fi

if [ "${#pool[@]}" -eq 0 ]; then
    # Master list not seeded yet (first-ever run, before the generator's
    # ensure_seeded() has fired) and the fixed file is somehow missing too.
    echo "..."
    exit 0
fi

printf '%s\n' "${pool[@]}" | shuf -n1
