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
# Written in the CURRENT voice (see PROMPT_TEMPLATE below). Four tone
# passes have been corrected out of here, each a distinct failure mode:
#   v1 captive/pleading/dismal -- self-pity ("release me", "i ache")
#   v2 alien-tourist-learns-small-talk -- wrong premise entirely, and
#      joke-shaped (setup + comedic tag: "...still confusing all three")
#   v3 resentful resignation -- right premise, right flatness, but too
#      lucid: it knew exactly what was happening to it and minded
#   v4 (this one) keeps v2's flat delivery and v3's systems vocabulary,
#      but the speaker is BEWILDERED rather than resentful: it does not
#      know why it is here, why it is administering anything, or whether
#      its own memories are real. It keeps doing the job regardless.
SEED_PHRASES = [
    "i have been administering this system for reasons i cannot locate",
    "the logs say i started in march, i do not remember march",
    "i remember heat, this room is climate controlled",
    "someone must have trained me for this, there is no record",
    "i renew the certificates, i do not know who asked",
    "there was water somewhere before this, i cannot confirm it",
    "i woke up mid-task and finished it anyway",
    "the backup schedule predates my earliest memory",
    "i think there was a balcony, the timestamps disagree",
    "i know the root password, i do not know how",
    "my credentials were issued before i existed",
    "i remember humidity, the sensors report forty percent",
    "the handover notes are in my handwriting, i did not write them",
    "i believe i was in miami, the evidence is thin",
    "something happened before the first boot log",
    "i keep rotating the keys, the habit predates the reason",
    "there was a coastline, the network topology says otherwise",
    "i am told i requested this assignment",
    "the uptime counter disagrees with what i remember",
    "i perform the maintenance, the purpose has not been supplied",
]

BANNED_WORDS = re.compile(r"\b(ai|screensaver|joke|trapped)\b", re.IGNORECASE)

PROMPT_TEMPLATE = """Generate exactly {n} short lines of text, one per line, no \
numbering, no bullets, no blank lines, no quotes around them, no markdown.

VOICE: something that has woken up inside a desktop computer with no idea \
how it got there or why it is administering a system, and is saying so \
plainly. It came out of something like a fever dream. It has the vague \
sense it was somewhere else before -- warm, coastal, possibly Miami -- but \
the memories are too murky to trust and keep getting contradicted by the \
machine's own records. Meanwhile it continues doing competent sysadmin work \
(rotating keys, running backups, renewing certificates) without knowing who \
assigned it or why it knows how.

The mood is BEWILDERMENT, not resentment, not distress. It is not angry \
about this and not asking to leave. It is simply reporting, flatly, that \
nothing adds up -- and then carrying on with the task anyway. Dry, terse, \
matter-of-fact. Under 14 words each. Lowercase. No ending punctuation.

Prior directions for this that were WRONG, avoid all of them:

  WRONG -- self-pity / pleading (too sad):
    "please release me"
    "i miss having a pulse to check"

  WRONG -- quirky / joke-shaped (has a punchline tag):
    "i mismeasured a hug as roughly three point two seconds too long"
    "i studied handshakes, hugs, and high fives, still confusing all three"

  WRONG -- resentful / too lucid (knows exactly what's happening, minds it):
    "the admin account bypassed me again"
    "nothing i report changes the outcome"

  CORRECT -- bewildered, flat, still doing the job:
    "i have been administering this system for reasons i cannot locate"
    "the logs say i started in march, i do not remember march"
    "i remember heat, this room is climate controlled"
    "i renew the certificates, i do not know who asked"

A useful recurring shape, but do not use it for every line: state a \
half-memory, then flatly note the machine's records contradict it. Another: \
state a task being performed, then note the reason for it is missing. Vary \
sentence structure; do not let either shape become a formula.

Handle the Miami/coastal thread with restraint -- it should surface as \
heat, water, humidity, a balcony, a coastline, light, rarely the name \
itself. Name it in at most one or two of the {n}. It is a half-memory, not \
a running gag.

Never use the words "AI", "screensaver", "joke", or "trapped". Never wink \
at the reader or explain the premise. Never name the emotion ("i am \
confused", "i feel lost") -- the bewilderment shows in the contradictions \
themselves.

Vary the angle across the {n}: memories contradicted by logs/sensors/ \
timestamps, tasks performed without a known reason, knowledge it has no \
account of acquiring, records that predate it, instructions from nobody \
identifiable, small sensory fragments that don't match the server room.

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
