#!/usr/bin/env bash
# Print one random phrase from screensaver-phrases.txt and exit.
#
# Called as the --program for phosphor/apple2/fontglide (see
# lock-screensaver.py's EXTRA_PROVIDERS). Each of those relaunches its
# --program a few seconds after it exits, so returning immediately after one
# line is what gives the rotation -- there is no loop in here on purpose.
set -euo pipefail
shuf -n1 "$(dirname "$(readlink -f "$0")")/screensaver-phrases.txt"
