#!/usr/bin/env bash
# screenshot-describe: ask Copilot what a screenshot shows, then append that
# description to the filename.
#
#   screenshot-describe.sh <file>...
#   screenshot-describe.sh --latest      # most recent undescribed screenshot
#
# "Screenshot from 2026-08-03 11-30-00.png"
#   -> "Screenshot from 2026-08-03 11-30-00 -- dark copilot chat window.png"
#
# The model output is untrusted text on its way into a filename, so it is
# aggressively sanitised: lowercased, stripped to [a-z0-9 -], collapsed, word-
# capped and length-capped. If nothing survives, the file is left alone.
#
# Model defaults to gpt-5-mini, which costs roughly 0.5 AI credits per image
# versus ~17 for the default model. Override with SHOTDESC_MODEL.

set -uo pipefail

export PATH="$HOME/.local/bin:$PATH"

model="${SHOTDESC_MODEL:-gpt-5-mini}"
max_words="${SHOTDESC_MAX_WORDS:-6}"
max_chars="${SHOTDESC_MAX_CHARS:-60}"
sep="${SHOTDESC_SEP:- -- }"
timeout_secs="${SHOTDESC_TIMEOUT:-90}"
notify_ok="${SHOTDESC_NOTIFY:-1}"

notify() { [[ "$notify_ok" == "1" ]] && notify-send -a "Screenshot" "$@" >/dev/null 2>&1; return 0; }

command -v copilot >/dev/null 2>&1 || { notify "Describe failed" "copilot CLI not found"; exit 1; }

# --latest picks the newest screenshot that has not been described yet, so the
# keybind can be pressed straight after a capture.
if [[ "${1:-}" == "--latest" ]]; then
    shotdir="${SCREENSHOT_DIR:-$HOME/Pictures/Screenshots}"
    mapfile -t found < <(
        find "$shotdir" -maxdepth 1 -type f \
             \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' \) \
             ! -name "*$sep*" -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-
    )
    if [[ ${#found[@]} -eq 0 || -z "${found[0]:-}" ]]; then
        notify "Nothing to describe" "No undescribed screenshot in $shotdir"
        exit 0
    fi
    set -- "${found[0]}"
fi

[[ $# -gt 0 ]] || { echo "usage: ${0##*/} <file>... | --latest" >&2; exit 2; }

read -r -d '' prompt <<'EOF'
Look at the attached image, which is a screenshot of a computer screen.
Reply with a 3-6 word description of what it shows, suitable for use in a
filename. Name the specific application and subject where you can.
Do not include random identifiers, hashes, UUIDs, timestamps or version
numbers, even if they are visible.
Reply with ONLY those words, lowercase, no punctuation, no quotes, no
explanation, no trailing period.
EOF

rc=0
for src in "$@"; do
    if [[ ! -f "$src" || ! -s "$src" ]]; then
        echo "skip (not a file): $src" >&2
        rc=1
        continue
    fi

    dir=$(dirname -- "$src")
    base=$(basename -- "$src")
    ext="${base##*.}"
    stem="${base%.*}"
    [[ "$ext" == "$base" ]] && ext=""

    raw=$(timeout "$timeout_secs" copilot -s \
            --model "$model" \
            --attachment "$src" \
            --log-level none --no-color \
            --disable-builtin-mcps --no-custom-instructions --no-ask-user \
            -p "$prompt" 2>/dev/null) || raw=""

    if [[ -z "$raw" ]]; then
        notify "Describe failed" "No description for $base"
        rc=1
        continue
    fi

    # Keep the first non-empty line, then reduce to a safe filename fragment.
    # tr handles the character class; awk enforces the word cap.
    slug=$(printf '%s' "$raw" \
        | grep -m1 -v '^[[:space:]]*$' \
        | tr '[:upper:]' '[:lower:]' \
        | tr -c 'a-z0-9 -' ' ' \
        | tr -s ' -' ' -' \
        | awk -v n="$max_words" '{ for (i = 1; i <= NF && i <= n; i++) printf "%s%s", (i > 1 ? " " : ""), $i }' \
        | cut -c "1-$max_chars" \
        | sed -E 's/^[ -]+//; s/[ -]+$//')

    if [[ -z "$slug" ]]; then
        notify "Describe failed" "Empty description for $base"
        rc=1
        continue
    fi

    dest="$dir/$stem$sep$slug${ext:+.$ext}"

    # Never clobber: fall back to a counter suffix.
    if [[ -e "$dest" ]]; then
        for i in $(seq 2 99); do
            cand="$dir/$stem$sep$slug ($i)${ext:+.$ext}"
            [[ -e "$cand" ]] || { dest="$cand"; break; }
        done
    fi

    if mv -n -- "$src" "$dest"; then
        printf '%s\n' "$dest"
        notify "Screenshot described" "$slug"
    else
        notify "Describe failed" "Could not rename $base"
        rc=1
    fi
done

exit $rc
