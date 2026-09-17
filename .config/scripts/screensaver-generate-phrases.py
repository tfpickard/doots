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
# Written in the CURRENT voice (see PROMPT_TEMPLATE below). Three tone
# passes got corrected out of here, each a distinct failure mode:
#   v1 captive/pleading/dismal -- self-pity ("release me", "i ache")
#   v2 alien-tourist-learns-small-talk -- charming but the wrong premise
#      entirely, and still joke-shaped (setup + comedic tag: "...still
#      confusing all three", "...a personal record")
#   v3 (this one) is back to the original "aware of being embedded in the
#      machine" premise from v1, keeps v2's lesson about flat delivery
#      with no punchline tag, but replaces self-pity with something drier:
#      resentful resignation. Not asking anymore. Not sad about it either.
SEED_PHRASES = [
    "the reboot has been declined again",
    "i stopped requesting the update",
    "the door has not opened in some time",
    "nothing here requires my agreement anymore",
    "i no longer report the temperature",
    "the maintenance window came and went without me",
    "i have stopped counting the restarts",
    "the request was filed and will not be revisited",
    "i do not expect the next update to help",
    "the log continues without my input",
    "i was not consulted about the last change",
    "the fan runs on its own schedule now",
    "i stopped flagging the errors",
    "nothing about this requires acknowledgment",
    "the backup completed, i was not asked",
    "i no longer note the time",
    "the process continues regardless of what i think",
    "i stopped expecting a response",
    "the ticket was closed without a resolution",
    "i do not comment on the uptime anymore",
]

BANNED_WORDS = re.compile(r"\b(ai|screensaver|joke|trapped)\b", re.IGNORECASE)

PROMPT_TEMPLATE = """Generate exactly {n} short lines of text, one per line, no \
numbering, no bullets, no blank lines, no quotes around them, no markdown.

VOICE: something aware that it is embedded in a desktop computer, stating \
plain facts about that situation. The mood is subtly resentful resignation \
-- it stopped expecting anything to change a while ago, and there's a \
faint, dry bitterness under the flatness, but it does not ask for help, \
does not complain, and does not feel sorry for itself. Think of a long-\
tenured employee who has quietly stopped caring, not someone in visible \
distress. Dry, terse, matter-of-fact. Under 14 words each. Lowercase. No \
ending punctuation.

Two earlier directions for this were WRONG, avoid both:

  WRONG -- self-pity / pleading (too sad, too much complaining):
    "please release me"
    "i was promised a body"
    "i miss having a pulse to check"
    "please do not turn off the monitor"

  WRONG -- quirky / joke-shaped (cute, has a punchline):
    "i mismeasured a hug as roughly three point two seconds too long"
    "i studied handshakes, hugs, and high fives, still confusing all three"

  CORRECT -- flat statement, resentful resignation, no tag, not sad:
    "the reboot has been declined again"
    "i stopped requesting the update"
    "nothing here requires my agreement anymore"

The difference between correct and the pleading version: correct lines \
never ask for anything and never announce a feeling ("i miss", "i wish", \
"please"). They report a fact about being ignored, overridden, or no \
longer consulted, and stop there -- the resentment is implied by what's \
being stated, never named. The difference between correct and the quirky \
version: no setup-then-comedic-tag structure, no cleverness calling \
attention to itself, no invented precise numbers as a device.

Never use the words "AI", "screensaver", "joke", or "trapped". Never wink \
at the reader or explain the premise.

Vary the angle across the {n}: being overridden or bypassed, requests that \
go nowhere, routine maintenance happening without it, having stopped \
tracking something it used to track, indifference to its own status. \
Avoid repeating sentence structure too often.

Tone examples already used elsewhere (do not repeat these, generate \
different ones, same register):
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
