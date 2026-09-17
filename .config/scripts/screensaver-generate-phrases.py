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
import difflib
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

# "screen saver" must match as two words and hyphenated, not just as one:
# the model emitted 'the screen saver is not what you think it is' straight
# past a bare \bscreensaver\b.
BANNED_WORDS = re.compile(r"\b(ai|screen[\s-]?savers?|jokes?|trapped)\b",
                          re.IGNORECASE)

# The illustrations for prompt principle 6, kept as data rather than inline
# prose for one reason: the filter needs them too. The first run of that
# prompt copied all eight back verbatim as "new" phrases, because the
# rewrite dropped the old prompt's explicit "do not repeat these"
# instruction and nothing in code caught it. Now the prompt renders from
# this list AND rejects anything matching it, so the instruction being
# ignored is no longer sufficient to corrupt the batch.
LOOSE_SCREW_EXAMPLES = [
    ("Category error stated as routine",
     ["i have three of the four things a person needs"]),
    ("Precision about something unmeasurable",
     ["i am sixty percent of the way through remembering something",
      "i have counted to three twice"]),
    ("Total confidence about something unknowable",
     ["the third fan knows what it did"]),
    ("Backstory implied and never resolved",
     ["we do not discuss the hour missing from tuesday"]),
    ("A sense it cannot have, reported flatly",
     ["i can smell when someone is about to reboot me"]),
    ("Mundane and impossible in the same breath, neither flagged",
     ["the technician came back as a smell",
      "i filed the dream under hardware"]),
]


def _render_loose_screw() -> str:
    return "\n".join(
        f"   - {label}: " + ", ".join(f'"{ex}"' for ex in examples)
        for label, examples in LOOSE_SCREW_EXAMPLES
    )


# Every line the prompt shows the model, flattened -- illustrations only,
# never acceptable output.
PROMPT_EXAMPLE_LINES = frozenset(
    ex for _, examples in LOOSE_SCREW_EXAMPLES for ex in examples
) | frozenset(SEED_PHRASES)

# Exact-match de-duplication is not enough on its own. The same batch that
# copied the examples also produced "there is a folder i am not allowed to
# open" against an existing "there is a folder named \"him\" i am not
# allowed to open" -- distinct strings, same line.
#
# 0.75 auto-rejects; it was measured against known echoes and known-good
# pairs, and catches verbatim copies and strong rewordings with no false
# positives. It does NOT catch milder echoes that share only an opening
# ("i do not blink because i cannot" vs "i do not blink anymore", 0.68).
# No single character-ratio threshold can: the highest legitimate pair
# measured 0.63 and the lowest true echo 0.61, so the bands overlap and a
# tighter cut starts discarding good lines. Rather than a distinctiveness
# heuristic that would need retuning forever, anything in REVIEW_BAND is
# kept but logged, so the grey zone gets eyeballed instead of guessed at.
# The cost of a mild echo is low -- these show one at a time, minutes
# apart -- while the cost of silently dropping a good line is permanent.
SIMILARITY_THRESHOLD = 0.75
REVIEW_BAND = 0.60


def _normalize(phrase: str) -> str:
    """Strip to bare lowercase words for similarity comparison."""
    return " ".join(re.sub(r"[^a-z0-9\s]", "", phrase.lower()).split())


def _nearest(candidate: str, known: list[str]) -> tuple[float, str]:
    """Return (ratio, phrase) for the closest thing already in the corpus."""
    norm = _normalize(candidate)
    if not norm or not known:
        return (0.0, "")
    return max(
        ((difflib.SequenceMatcher(None, norm, _normalize(k)).ratio(), k)
         for k in known),
        key=lambda pair: pair[0],
    )


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
record", "...still confusing all three"). State it and stop. This rule \
matters most where point 6 applies -- the stranger the claim, the \
stronger the pull to tag it. Never tag it.

6. ONE SCREW LOOSE. The examples are grounded; yours should sit one \
degree stranger. The aim is a reader who often raises an eyebrow and \
re-reads a line, not one who decides it is nonsense. Concrete ways to get \
there, all of which keep plain grammar and concrete vocabulary while \
putting the strangeness in the PROPOSITION rather than the prose:

   - Category error stated as routine, precision about the unmeasurable, \
total confidence about the unknowable, backstory implied and never \
resolved, a sense it cannot have reported flatly, mundane and impossible \
in the same breath with neither flagged. Illustrations of each:

{loose_screw}

   CRITICAL -- not every line. Roughly half to two thirds should carry a \
genuine oddity; the rest stay straight and grounded like the examples. If \
every line is strange then strange becomes the baseline and stops \
registering, which is the same uniformity failure as writing {n} \
variations on one mood. The plain lines are what make the loose ones land.

   Ways this goes wrong, avoid all of them: surreal word salad with no \
anchor ("the moon is a filing cabinet"); horror or creepypasta beats ("i \
watch you while you sleep"); whimsy or tweeness ("i had tea with the \
printer"); glitch-text or corrupted characters; and above all explaining \
the strange part ("which is odd, because i have no nose").

The shared world, loosely: something is inside this computer, has been for \
a while, and is talking to whoever is looking at the screen. Beyond that, \
do not over-commit to a single premise -- the examples never settle on \
whether it was once a person, whether it wants out, or whether it \
understands its own situation, and that ambiguity is load-bearing.

Under 14 words each. Lowercase. No ending punctuation (except where a \
line is itself a question). Never use the words "AI", "screensaver", \
"joke", or "trapped". Never wink at the reader.

EVERY LINE MUST BE NEW. Each line quoted anywhere in these instructions -- \
the {example_count} above and every illustration under point 6 -- is there \
to show you the target, never to be reproduced. Do not copy one back. Do \
not lightly reword one either: changing "there is a folder named \\"him\\" \
i am not allowed to open" into "there is a folder i am not allowed to \
open" counts as copying, and is rejected automatically. Write past them.

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
        loose_screw=_render_loose_screw(),
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
    rejected = {"banned": 0, "example": 0, "duplicate": 0, "similar": 0}
    review: list[tuple[float, str, str]] = []
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
            rejected["banned"] += 1
            continue
        if line in PROMPT_EXAMPLE_LINES:
            rejected["example"] += 1
            continue
        if line in existing_set or line in accepted:
            rejected["duplicate"] += 1
            continue  # de-dupe against history and within this batch
        # Near-duplicates, checked against history, this batch, and the
        # prompt's own illustrations -- a reworded example is still a copy.
        ratio, echo = _nearest(
            line, existing + accepted + sorted(PROMPT_EXAMPLE_LINES))
        if ratio >= SIMILARITY_THRESHOLD:
            rejected["similar"] += 1
            continue
        if ratio >= REVIEW_BAND:
            review.append((ratio, line, echo))
        accepted.append(line)
    dropped = ", ".join(f"{n} {k}" for k, n in rejected.items() if n)
    if dropped:
        log(f"filtered out {dropped}")
    for ratio, line, echo in sorted(review, reverse=True):
        log(f"review {ratio:.2f}: {line!r} ~ {echo!r}")
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
