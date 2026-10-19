#!/usr/bin/env python3
"""Print the next line of the screensaver voice's journal, and exit.

Called as the -program for phosphor/apple2 (see lock-screensaver.py's
EXTRA_PROVIDERS). Each relaunches its program a few seconds after it exits,
so printing exactly one line and returning is what drives the display --
there is no loop in here on purpose. The journal itself is written by
screensaver-journal.py; this only ever reads it, never blocks on generation,
and never calls a model.

Most calls print the NEXT line of the journal, from a cursor that persists
between calls (and between screensaver sessions), so consecutive lines on
screen are consecutive thoughts. Reading order:

  - unseen entries first: the moment the stream finishes an entry, it jumps
    to the oldest entry it has never shown (but no further back than the
    last RECENT_HOURS -- after a long absence it skips to what's current
    rather than replaying the whole week);
  - otherwise chronological, entry after entry;
  - caught up with the newest entry: it reopens the journal at a random
    older entry and reads forward from there, like flipping back through a
    diary. Wrapping to the start of a recent window instead would loop the
    same few dozen lines several times in one 35-minute session.

Interrupting that, without moving the cursor, so the stream resumes where it
left off:

  - P_REFRAIN: one of the fixed core phrases (screensaver-phrases.txt) --
    the things it keeps coming back to;
  - P_MEMORY: an old line surfacing out of order, from anywhere in the
    journal or from the fragments before it (phrases-master.txt).

With no journal yet it falls back to v1's behaviour: a random line from the
core phrases and the fragments.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

STATE_DIR = Path(os.environ.get(
    "SCREENSAVER_STATE_DIR",
    Path.home() / ".local/share/lock-screensaver"))
JOURNAL_FILE = STATE_DIR / "journal.jsonl"
CURSOR_FILE = STATE_DIR / "cursor.json"
LEGACY_FILE = STATE_DIR / "phrases-master.txt"
CORE_FILE = Path(__file__).resolve().parent / "screensaver-phrases.txt"

P_REFRAIN = 0.06
P_MEMORY = 0.06
# Of the memories, this share comes from the journal, the rest from the
# fragments that predate it.
P_MEMORY_FROM_JOURNAL = 0.6
# After a long absence, catch up from no further back than this.
RECENT_HOURS = 24
# A cursor untouched for this long means a new screensaver session.
SESSION_GAP = timedelta(minutes=45)


def read_lines(path: Path) -> list[str]:
    try:
        return [l.strip() for l in path.read_text().splitlines() if l.strip()]
    except OSError:
        return []


def read_journal() -> list[dict]:
    entries = []
    try:
        with JOURNAL_FILE.open() as fh:
            for raw in fh:
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                if entry.get("lines") and entry.get("ts"):
                    entries.append(entry)
    except OSError:
        pass
    entries.sort(key=lambda e: datetime.fromisoformat(e["ts"]))
    return entries


def load_cursor() -> dict:
    try:
        return json.loads(CURSOR_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_cursor(cursor: dict) -> None:
    tmp = CURSOR_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cursor))
    os.replace(tmp, CURSOR_FILE)


def first_unseen(entries: list[dict], seen_upto: str | None) -> int | None:
    """Index of the oldest entry never shown, clamped to the recent window."""
    if seen_upto is None:
        unseen = 0
    else:
        seen = datetime.fromisoformat(seen_upto)
        unseen = next((i for i, e in enumerate(entries)
                       if datetime.fromisoformat(e["ts"]) > seen), None)
        if unseen is None:
            return None
    newest = datetime.fromisoformat(entries[-1]["ts"])
    window = next(i for i, e in enumerate(entries)
                  if datetime.fromisoformat(e["ts"])
                  >= newest - timedelta(hours=RECENT_HOURS))
    return max(unseen, window)


def next_position(entries: list[dict], cursor: dict,
                  rng: random.Random) -> tuple[int, int]:
    index = {e["ts"]: i for i, e in enumerate(entries)}
    at = index.get(cursor.get("ts"))
    unseen = first_unseen(entries, cursor.get("seen_upto"))
    stale = time.time() - cursor.get("at", 0) > SESSION_GAP.total_seconds()

    # Fresh install, a cursor whose entry is gone, or a new session with
    # something new to show: start on the new material.
    if at is None:
        return (unseen if unseen is not None else 0), 0
    if stale and unseen is not None:
        return unseen, 0

    line = cursor.get("line", 0) + 1
    if line < len(entries[at]["lines"]):
        return at, line
    # Entry finished: new material first, then onwards, then flip back.
    if unseen is not None:
        return unseen, 0
    if at + 1 < len(entries):
        return at + 1, 0
    if len(entries) == 1:
        return 0, 0
    return rng.randrange(len(entries) - 1), 0


def interjection(entries: list[dict], current_ts: str | None,
                 rng: random.Random) -> str | None:
    roll = rng.random()
    if roll < P_REFRAIN:
        core = read_lines(CORE_FILE)
        if core:
            return rng.choice(core)
    elif roll < P_REFRAIN + P_MEMORY:
        older = [l for e in entries if e["ts"] != current_ts for l in e["lines"]]
        legacy = read_lines(LEGACY_FILE)
        if older and (not legacy or rng.random() < P_MEMORY_FROM_JOURNAL):
            return rng.choice(older)
        if legacy:
            return rng.choice(legacy)
    return None


def main() -> int:
    rng = random.Random()
    entries = read_journal()

    if not entries:
        pool = read_lines(CORE_FILE) + read_lines(LEGACY_FILE)
        print(rng.choice(pool) if pool else "...")
        return 0

    cursor = load_cursor()
    aside = interjection(entries, cursor.get("ts"), rng)
    if aside is not None:
        print(aside)
        return 0

    at, line = next_position(entries, cursor, rng)
    entry = entries[at]
    print(entry["lines"][line])

    seen = cursor.get("seen_upto")
    if seen is None or datetime.fromisoformat(entry["ts"]) > datetime.fromisoformat(seen):
        seen = entry["ts"]
    try:
        save_cursor({"ts": entry["ts"], "line": line,
                     "seen_upto": seen, "at": time.time()})
    except OSError:
        pass  # a read-only state dir costs continuity, not the display
    return 0


if __name__ == "__main__":
    sys.exit(main())
