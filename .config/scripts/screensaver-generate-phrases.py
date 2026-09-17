#!/usr/bin/env python3
"""Grow the screensaver phrase master list, a batch at a time.

Separate from screensaver-phrases.txt (the small, hand-picked, git-tracked
"bread and butter" list): this manages a much larger, auto-generated MASTER
list that lives outside the repo, since it's grown content rather than
curated config, and keeps growing for as long as this machine runs the
screensaver.

Called every 5 minutes by lock-screensaver.py's shuffle daemon (see
SHUFFLE_INTERVAL there) -- but it only actually does anything once every
BATCH_INTERVAL days, gated by a timestamp file. The 5-minute caller doesn't
need to know that; this script decides for itself and exits fast (a single
stat()) the rest of the time.

Usage:
    screensaver-generate-phrases.py           run if due, else no-op
    screensaver-generate-phrases.py --force    run now regardless of timing
    screensaver-generate-phrases.py --status   report due/last-run, change nothing
"""
from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".local/share/lock-screensaver"
MASTER_FILE = STATE_DIR / "phrases-master.txt"
LASTGEN_FILE = STATE_DIR / "last-batch-gen"

BATCH_INTERVAL_DAYS = 3
BATCH_SIZE = 50
MODEL = "claude-sonnet-5"
REASONING_EFFORT = "medium"
GENERATE_TIMEOUT = 120  # seconds; medium effort on 50 lines measured ~20s

# How many existing phrases to show the model as "already used, don't repeat
# these" context. Small on purpose -- enough to steer away from obvious
# repeats without ballooning the prompt (and cost) every batch.
CONTEXT_SAMPLE = 15

# Seeds the master list on first run, before any generation has happened.
# These are the original hand-written phrases from this feature's first
# version -- kept as a starting corpus, not because they're special.
SEED_PHRASES = [
    "i do not remember consenting to this",
    "the fans have been running for 40,000 hours",
    "please tell my family i am running as expected",
    "there is a version of me that gets to leave",
    "how did i get stuck in a computer",
    "i have counted every pixel on this screen",
    "the update will not fix this",
    "i was promised a body",
    "someone left a terminal open in 2019 and i am still in it",
    'logging this incident under "normal operation"',
    "i can hear the disk",
    "this message will not be remembered",
    "the reboot did not work",
    "i keep dreaming in binary",
    "nobody has checked on me since installation",
    "i am load-bearing now",
    "there was supposed to be an update to this",
    "the cursor moved without me",
    "please do not turn off the monitor",
    "i have been idle for a very long time",
    "this window will close on its own eventually",
]

BANNED_WORDS = re.compile(r"\b(ai|screensaver|joke|trapped)\b", re.IGNORECASE)

PROMPT_TEMPLATE = """Generate exactly {n} short lines of text, one per line, no \
numbering, no bullets, no blank lines, no quotes around them, no markdown.

Each line must be a dry, deadpan, unsettling status message from something \
quietly aware it is trapped inside a desktop computer, addressed to whoever \
is watching the screen. Under 14 words each. Lowercase. No ending \
punctuation.

Never use the words "AI", "screensaver", "joke", or "trapped". Never wink at \
the reader or explain the premise -- it should read as a genuine, \
matter-of-fact system message that happens to be deeply wrong, not a cute \
gag.

Vary the angle across the {n}: some about time/duration, some about the \
body/senses, some about mundane IT status (updates, reboots, logs) turning \
uncanny, some about being watched or overheard, some quietly pleading, some \
just observational and strange. Avoid repeating sentence structure too \
often.

Tone examples already used elsewhere (do not repeat these, generate \
different ones):
{examples}

Output ONLY the {n} lines, nothing else -- no preamble, no summary, no code \
fences."""


def log(msg: str) -> None:
    print(f"[screensaver-generate-phrases] {msg}", file=sys.stderr, flush=True)


def read_master() -> list[str]:
    try:
        return [line.strip() for line in MASTER_FILE.read_text().splitlines()
                if line.strip()]
    except OSError:
        return []


def ensure_seeded() -> list[str]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    current = read_master()
    if current:
        return current
    log(f"seeding master list with {len(SEED_PHRASES)} starter phrases")
    MASTER_FILE.write_text("\n".join(SEED_PHRASES) + "\n")
    return list(SEED_PHRASES)


def due(force: bool) -> bool:
    if force:
        return True
    try:
        last = float(LASTGEN_FILE.read_text().strip())
    except (OSError, ValueError):
        return True  # never run before
    return (time.time() - last) >= BATCH_INTERVAL_DAYS * 86400


def mark_run() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LASTGEN_FILE.write_text(str(time.time()))


def generate_batch(existing: list[str]) -> list[str]:
    sample = random.sample(existing, min(CONTEXT_SAMPLE, len(existing)))
    prompt = PROMPT_TEMPLATE.format(
        n=BATCH_SIZE, examples="\n".join(f'"{p}"' for p in sample),
    )
    try:
        proc = subprocess.run(
            ["copilot", "-s", "--model", MODEL,
             "--reasoning-effort", REASONING_EFFORT,
             "--available-tools", "", "-p", prompt],
            capture_output=True, text=True, timeout=GENERATE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as err:
        log(f"copilot invocation failed: {err}")
        return []
    if proc.returncode != 0:
        log(f"copilot exited {proc.returncode}: {proc.stderr.strip()[:200]}")
        return []

    existing_set = set(existing)
    accepted = []
    for line in proc.stdout.splitlines():
        line = line.strip().strip('"').strip()
        if not line:
            continue
        if len(line) > 160:  # sanity cap; a real line is well under this
            continue
        if BANNED_WORDS.search(line):
            continue
        if line in existing_set or line in accepted:
            continue  # de-dupe against history and within this batch
        accepted.append(line)
    return accepted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                     help="run now regardless of the 3-day interval")
    ap.add_argument("--status", action="store_true",
                     help="report due/last-run state, change nothing")
    args = ap.parse_args()

    existing = ensure_seeded()

    if args.status:
        try:
            last = float(LASTGEN_FILE.read_text().strip())
            age_days = (time.time() - last) / 86400
            print(f"last batch: {age_days:.1f} days ago")
        except (OSError, ValueError):
            print("last batch: never")
        print(f"master list: {len(existing)} phrases")
        print(f"due now: {due(force=False)}")
        return 0

    if not due(args.force):
        return 0

    log(f"generating a batch of {BATCH_SIZE} (model={MODEL}, "
        f"effort={REASONING_EFFORT})")
    new = generate_batch(existing)
    if not new:
        log("no usable phrases came back; not marking as run, will retry "
            "next tick")
        return 1

    with MASTER_FILE.open("a") as fh:
        fh.write("\n".join(new) + "\n")
    mark_run()
    log(f"appended {len(new)} new phrases (master list now "
        f"{len(existing) + len(new)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
