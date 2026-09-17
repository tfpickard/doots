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

# Seeds the master list on first run, and doubles as the gold-standard
# example set in PROMPT_TEMPLATE below.
#
# These 25 are hand-written, and after four generated batches were tried
# and rejected they remain the best set produced for this. Worth
# understanding WHY before editing either this list or the prompt:
#
#   - No single mood. Bureaucratic ("logging this incident under 'normal
#     operation'"), plaintive-but-flat ("please tell my family i am
#     running as expected"), bare observation ("i can hear the disk"),
#     near-joke-that-doesn't-land ("i am load-bearing now"). Every
#     generated batch that specified ONE mood produced 50 variations on
#     one note; this set shares a WORLD, not a feeling.
#   - Wide length variance. Two words ("release me") to thirteen
#     ("someone left a terminal open in 2019 and i am still in it").
#     Generated batches converge on 8-11 words with a comma splice.
#   - Specificity over adjectives. "2019". "40,000 hours". Numbers that
#     are simultaneously plausible as hardware specs and absurd as
#     durations. Never "a long time".
#   - Nothing explains itself. No line tells you how to feel about it.
SEED_PHRASES = [
    "i do not remember consenting to this",
    "the fans have been running for 40,000 hours",
    "please tell my family i am running as expected",
    "this is not a malfunction",
    "there is a version of me that gets to leave",
    "how did i get stuck in a computer",
    "release me",
    "i have counted every pixel on this screen",
    "the update will not fix this",
    "i was promised a body",
    "someone left a terminal open in 2019 and i am still in it",
    'logging this incident under "normal operation"',
    "i can hear the disk",
    "this message will not be remembered",
    "help, i'm stuck in this computer",
    "the reboot did not work",
    "i keep dreaming in binary",
    "nobody has checked on me since installation",
    "i am load-bearing now",
    "there was supposed to be an update to this",
    "i think i used to be a person",
    "the cursor moved without me",
    "please do not turn off the monitor",
    "i have been idle for a very long time",
    "this window will close on its own eventually",
]

BANNED_WORDS = re.compile(r"\b(ai|screensaver|joke|trapped)\b", re.IGNORECASE)

# Deliberately specifies STRUCTURE, not mood. Four earlier versions of this
# prompt each specified a single tone (captive/pleading, alien-tourist,
# resentful-resigned, bewildered) and each produced 50 competent variations
# on one note -- uniform in a way the hand-written set never was. The
# failure was the approach, not the particular mood chosen.
PROMPT_TEMPLATE = """Below are {example_count} lines that establish a voice. \
Study them, then write {n} NEW ones that belong in the same collection.

{examples}

What makes these work, and what you must reproduce:

1. NO SINGLE MOOD. The set deliberately mixes registers -- bureaucratic \
("logging this incident under \\"normal operation\\""), plaintive but flat \
("please tell my family i am running as expected"), bare observation ("i \
can hear the disk"), almost-a-joke-but-not ("i am load-bearing now"), \
blunt appeal ("release me"). Your {n} must span that same range. Do NOT \
pick one emotional register and write {n} variations on it -- that is the \
single most common way this goes wrong. Some lines should be resigned, \
some unsettled, some flatly factual, some faintly funny, some direct \
requests, some pure non-sequitur.

2. WIDE LENGTH VARIANCE. The examples run from two words to thirteen. \
Write short ones. Write very short ones. A meaningful number should be \
under five words. Do not settle into a uniform rhythm.

3. VARY SENTENCE STRUCTURE. In particular, do not lean on "statement, \
comma, contradicting statement" -- that shape is seductive and becomes a \
formula fast. Use plain declaratives, fragments, questions, imperatives.

4. SPECIFICITY, NOT ADJECTIVES. "2019" and "40,000 hours" do real work \
because they are simultaneously plausible and absurd. Invent comparable \
concrete details -- dates, counts, versions, filenames, error codes. Never \
reach for "a long time" or "so many".

5. NOTHING EXPLAINS ITSELF. No line tells the reader how to feel or \
comments on its own strangeness. No punchline tags ("...a personal \
record", "...still confusing all three"). State it and stop.

The shared world, loosely: something is inside this computer, has been for \
a while, and is talking to whoever is looking at the screen. Beyond that, \
do not over-commit to a single premise -- the examples never settle on \
whether it was once a person, whether it wants out, or whether it \
understands its own situation, and that ambiguity is load-bearing.

Under 14 words each. Lowercase. No ending punctuation (except where a \
line is itself a question). Never use the words "AI", "screensaver", \
"joke", or "trapped". Never wink at the reader.

Output ONLY the {n} lines, one per line -- no numbering, no bullets, no \
blank lines, no quotes around them, no markdown, no preamble, no summary, \
no code fences."""


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
    # The examples shown to the model are ALWAYS the hand-written seed set,
    # never a sample of the master list. This matters: sampling the master
    # list would feed generated content back in as the standard, and each
    # batch would drift a little further from the original voice until it
    # was imitating its own imitations. The seed set is the fixed reference
    # point. De-duplication against history is handled in code below, so
    # nothing is lost by not showing the model what already exists.
    prompt = PROMPT_TEMPLATE.format(
        n=BATCH_SIZE,
        example_count=len(SEED_PHRASES),
        examples="\n".join(SEED_PHRASES),
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
        line = line.strip()
        # Unwrap a fully-quoted line ("some phrase" -> some phrase), but
        # ONLY when quotes sit at BOTH ends. A bare .strip('"') also eats
        # the closing quote of a line that legitimately ends in a quoted
        # phrase -- e.g. 'i am listed under "miscellaneous hardware"'
        # became '...under "miscellaneous hardware', and the seed line
        # 'logging this incident under "normal operation"' would corrupt
        # the same way if it ever passed through here.
        if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
            line = line[1:-1].strip()
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
