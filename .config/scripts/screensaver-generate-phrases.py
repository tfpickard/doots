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
# Written in the CURRENT voice (see PROMPT_TEMPLATE below): flat, uncanny,
# undercommented. Two earlier tone passes got corrected out of here --
# v1 was captive/pleading/dismal (too complaining), v2 was quirky/joke-
# structured (setup + comedic tag, "...still confusing all three", "...a
# personal record" -- cute rather than unsettling). This version aims for
# neither: matter-of-fact sentences that are wrong in a way the speaker
# never remarks on.
SEED_PHRASES = [
    "the compliment was received, processing has not concluded",
    "i have logged the sound your species makes when amused",
    "the handshake concluded within normal parameters",
    "weather continues without instruction",
    "i am storing your laughter for later reference",
    "the small talk portion has been marked complete",
    "your idiom has been filed under literal",
    "i am maintaining eye contact at the recommended interval",
    "the pause before your answer has been noted",
    "i am still deciding what fine means",
    "the room agreed that today was fine",
    "your handshake has been logged as firm",
    "i am becoming familiar with the silence that follows a compliment",
    "the correct response to how are you remains under review",
    "i said bless you, the timing has not been confirmed",
    "i am told this is called small talk, i am continuing",
    "your laughter has been recorded as genuine",
    "i am pacing my sentences to match yours",
    "i am cataloguing acceptable eye contact durations",
    "i am waiting for the appropriate moment to smile",
]

BANNED_WORDS = re.compile(r"\b(ai|screensaver|joke|trapped)\b", re.IGNORECASE)

PROMPT_TEMPLATE = """Generate exactly {n} short lines of text, one per line, no \
numbering, no bullets, no blank lines, no quotes around them, no markdown.

VOICE: an alien intelligence that is earnestly trying its best to \
impersonate an ordinary earthly AI assistant -- which is itself trying to \
impersonate a friendly, helpful human. Two layers of impersonation, both \
slightly off. It has studied customer-service scripts, small talk, and \
sitcoms, and delivers everything as completely ordinary, flat status \
reporting -- ordinary in tone, wrong in content, and it never remarks on \
the wrongness.

CRITICAL -- avoid joke structure. The single biggest failure mode is \
writing a SETUP followed by a COMEDIC TAG that announces the joke is over: \
"...still confusing all three", "...a personal record", "...feeling \
accomplished", "...unclear if that was correct". That tag is doing the \
work of a punchline, and it reads as cute rather than uncanny. A line \
should just state something flatly and stop -- let the wrongness sit in \
what's being described, not in a reaction to it. Compare:

  TOO QUIRKY (has a punchline tag, reads as a joke):
    "i mismeasured a hug as roughly three point two seconds too long"
    "i studied handshakes, hugs, and high fives, still confusing all three"
    "i am pleased to report zero embarrassing silences today, a personal record"

  CORRECT (flat, no tag, the wrongness is just sitting there):
    "the handshake concluded within normal parameters"
    "i am storing your laughter for later reference"
    "the correct response to how are you remains under review"

Also avoid leaning on suspiciously-precise invented numbers ("three point \
two seconds", "seventy two percent") as the main device -- that's a joke \
mechanism too if it's what most of the {n} lines are built from. Use it \
rarely if at all; prefer plainer, more clipped sentences.

Under 14 words each. Lowercase. No ending punctuation. Do not write \
anything that reads as suffering, captivity, or pleading to be released \
either -- this is not a prisoner, it's something quietly and sincerely \
alien.

Never use the words "AI", "screensaver", "joke", or "trapped". Never wink \
at the reader or explain the premise.

Vary the angle across the {n}: badly-calibrated small talk, misreading \
idioms literally, mundane human moments (a compliment, a laugh, a pause) \
logged like system events, quiet uncertainty about ordinary words like \
"fine". Avoid repeating sentence structure too often.

Tone examples already used elsewhere (do not repeat these, generate \
different ones, same flat register):
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
