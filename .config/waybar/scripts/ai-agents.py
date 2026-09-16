#!/usr/bin/env python3
"""Waybar module: background AI agent (GitHub Copilot) activity.

There is no `gh copilot status` / `copilot status` command, so this reads the
state the Copilot agent already writes to disk:

    ~/.copilot/session-state/<session-id>/
        inuse.<pid>.lock   present only while a host process owns the session
        workspace.yaml     cwd + the session's display name
        events.jsonl       append-only event stream for the session

A session is *live* when its `inuse.<pid>.lock` names a process that is still
running. Its state is then derived by replaying the tail of `events.jsonl`:

    permission.requested without permission.completed -> blocked (needs you)
    open `ask_user` tool call                         -> blocked (needs you)
    assistant.turn_start without assistant.turn_end   -> working
    session.task_complete since the last user.message -> done
    otherwise                                         -> idle

Open `task` tool calls are counted separately as sub-agents, since those are
background agents doing work of their own.

Bar text:  {robot} {state glyph}{count}
Tooltip:   one line per live session with its state, repo/dir and current tool
Classes:   blocked > done > working > idle (styled in the waybar theme CSS)

The bar text is deliberately a fixed shape -- one icon, one state glyph and a
two-column count -- so the module never changes width as the state changes.
Nerd Font glyphs are not all the same advance width, so the theme CSS pins a
`min-width` too; between them the bar stays still.

Output is a single line of Waybar JSON: {text, tooltip, class}.
"""
import glob
import html
import json
import os
import re
import time
from datetime import datetime, timezone

COPILOT_HOME = os.environ.get(
    "COPILOT_HOME", os.path.expanduser("~/.copilot")
)
SESSION_DIR = os.path.join(COPILOT_HOME, "session-state")

# How much of the tail of events.jsonl to replay. Tool results are inlined in
# the stream, so a single line can be megabytes; start small and grow until a
# turn boundary is in view.
TAIL_BYTES = 256 * 1024
TAIL_BYTES_MAX = 8 * 1024 * 1024

# A turn that has not produced an event in this long is treated as abandoned
# (host killed mid-turn, leaving no turn_end behind).
STALE_TURN_SEC = 20 * 60

# How long a finished task keeps flagging itself for attention.
DONE_TTL_SEC = 60 * 60

# Sessions that have been dormant this long are still open in the IDE but are
# not news; drop them so the count reflects what is actually in flight.
IDLE_TTL_SEC = 8 * 60 * 60

# Most a tooltip should list before it stops being scannable.
TOOLTIP_MAX = 6

# Stale `inuse.<pid>.lock` files outlive their host by design (a crashed IDE
# never cleans up), and PIDs get recycled, so the owning process must actually
# look like a Copilot host before its lock is believed.
HOST_HINT = "copilot"

ICON_AGENT = "\U000f0bc9"     # space-invaders -- deliberately not md-robot,
                              # which custom/ai (Ask AI) already uses
ICON_BLOCKED = "\U000f0026"   # alert
ICON_DONE = "\U000f012c"      # check
ICON_IDLE = "\U000f04b2"      # sleep
ICON_WORKING = "\U000f051f"   # timer-sand (tooltip only)
SPINNER = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"

STATE_ICONS = {
    "blocked": ICON_BLOCKED,
    "done": ICON_DONE,
    "working": ICON_WORKING,
    "idle": ICON_IDLE,
}
# Most attention-worthy first.
#
# `working` deliberately outranks `done`: "done" is a sticky past event that
# lingers for DONE_TTL_SEC, and letting it win meant the bar showed a green
# tick while agents were visibly still working. A live state should never be
# masked by a finished one -- the finished ones stay in the tooltip, and
# surface on the bar once nothing is running.
STATE_ORDER = ("blocked", "working", "done", "idle")

RE_TYPE = re.compile(r'"type"\s*:\s*"([^"]+)"')
RE_TOOL_CALL_ID = re.compile(r'"toolCallId"\s*:\s*"([^"]+)"')
RE_TOOL_NAME = re.compile(r'"toolName"\s*:\s*"([^"]+)"')
RE_REQUEST_ID = re.compile(r'"requestId"\s*:\s*"([^"]+)"')
RE_TIMESTAMP = re.compile(r'"timestamp"\s*:\s*"([^"]+)"')

# Lines below this get a real JSON parse (for tool arguments etc.); anything
# larger is a bulk tool result and only needs its type and ids.
FULL_PARSE_MAX = 128 * 1024


def pid_alive(pid):
    """True if `pid` is running and looks like a Copilot agent host."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    return HOST_HINT in cmdline


def parse_line(line):
    """Extract the fields we need from one events.jsonl line.

    Small lines are parsed as JSON; oversized ones (inlined tool output) fall
    back to regex over the head and tail of the line, where every field we
    care about lives -- `data` keys we read come first, `timestamp` last.
    """
    if len(line) <= FULL_PARSE_MAX:
        try:
            ev = json.loads(line)
        except ValueError:
            return None
        data = ev.get("data") or {}
        return {
            "type": ev.get("type"),
            "timestamp": ev.get("timestamp"),
            "toolCallId": data.get("toolCallId"),
            "toolName": data.get("toolName"),
            "requestId": data.get("requestId"),
            "data": data,
        }

    head, tail = line[:800], line[-300:]
    m = RE_TYPE.search(head)
    if not m:
        return None

    def grab(rx, s):
        g = rx.search(s)
        return g.group(1) if g else None

    return {
        "type": m.group(1),
        "timestamp": grab(RE_TIMESTAMP, tail),
        "toolCallId": grab(RE_TOOL_CALL_ID, head),
        "toolName": grab(RE_TOOL_NAME, head),
        "requestId": grab(RE_REQUEST_ID, head),
        "data": {},
    }


def read_tail(path, nbytes):
    """Yield whole lines from the last `nbytes` of `path`."""
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > nbytes:
            f.seek(size - nbytes)
            f.readline()  # discard the partial first line
        for raw in f:
            line = raw.decode("utf-8", "replace").strip()
            if line:
                yield line


def parse_ts(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def replay(path):
    """Replay the tail of an event stream into a session state summary."""
    tail = TAIL_BYTES
    while True:
        state = {
            "turn_open": False,
            "open_tools": {},        # toolCallId -> toolName
            "pending_perms": {},     # requestId -> description
            "task_complete_at": None,
            "shutdown": False,
            "error": None,
            "last_ts": None,
            "saw_boundary": False,
        }
        try:
            lines = list(read_tail(path, tail))
        except OSError:
            return state

        for line in lines:
            ev = parse_line(line)
            if not ev:
                continue
            etype = ev["type"]
            ts = ev["timestamp"]
            if ts:
                state["last_ts"] = ts
            data = ev["data"]

            if etype in ("assistant.turn_start", "session.start", "session.resume"):
                state["saw_boundary"] = True

            if etype in ("session.start", "session.resume"):
                # Reopening clears a previous shutdown. Without this a session
                # that was closed and later resumed stays flagged as dead for
                # as long as the old shutdown sits inside the replay window,
                # and never appears in the bar however busy it is.
                state["shutdown"] = False

            if etype == "assistant.turn_start":
                state["turn_open"] = True
                state["error"] = None
            elif etype in ("assistant.turn_end", "abort"):
                state["turn_open"] = False
                state["open_tools"].clear()
                state["pending_perms"].clear()
            elif etype == "tool.execution_start":
                if ev["toolCallId"]:
                    state["open_tools"][ev["toolCallId"]] = {
                        "name": ev["toolName"] or "tool",
                        "args": data.get("arguments") or {},
                        "ts": ts,
                    }
            elif etype == "tool.execution_complete":
                state["open_tools"].pop(ev["toolCallId"], None)
            elif etype == "permission.requested":
                if ev["requestId"]:
                    req = data.get("permissionRequest") or {}
                    state["pending_perms"][ev["requestId"]] = {
                        "kind": req.get("kind") or "tool",
                        "detail": (
                            req.get("fullCommandText")
                            or req.get("path")
                            or req.get("url")
                            or ""
                        ),
                        "ts": ts,
                    }
            elif etype == "permission.completed":
                state["pending_perms"].pop(ev["requestId"], None)
            elif etype == "session.task_complete":
                state["task_complete_at"] = ts
                state["turn_open"] = False
                state["open_tools"].clear()
            elif etype == "user.message":
                state["task_complete_at"] = None
                state["error"] = None
            elif etype == "session.shutdown":
                state["shutdown"] = True
            elif etype == "session.error":
                state["error"] = data.get("message") or "session error"

        # A window with no turn boundary in it cannot be trusted to know
        # whether a turn is still open; widen it and replay again.
        if state["saw_boundary"] or tail >= TAIL_BYTES_MAX:
            return state
        tail = min(tail * 8, TAIL_BYTES_MAX)


def read_workspace(path):
    """Minimal reader for the handful of scalars we need from workspace.yaml.

    Handles the three forms the agent actually writes: a bare scalar, a
    double-quoted string, and a block scalar (`name: |-` with the text on the
    following indented lines), which is what a multi-line first message
    produces. Without the block-scalar case the name reads as a literal "|-".
    """
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line or line.startswith((" ", "\t", "#")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key not in ("cwd", "name", "client_name"):
            continue

        if value[:1] in ("|", ">"):
            block = []
            while i < len(lines) and (
                not lines[i].strip() or lines[i].startswith((" ", "\t"))
            ):
                block.append(lines[i].strip())
                i += 1
            value = " ".join(b for b in block if b)
        elif value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                value = value.strip('"')
        out[key] = value
    return out


def classify(state, now):
    if state["shutdown"]:
        return None
    if state["pending_perms"]:
        return "blocked"
    if any(t["name"] == "ask_user" for t in state["open_tools"].values()):
        return "blocked"

    last = parse_ts(state["last_ts"])
    age = (now - last).total_seconds() if last else None

    if state["turn_open"]:
        # No events for a long while means the host died mid-turn.
        if age is not None and age > STALE_TURN_SEC:
            return "idle"
        return "working"
    if state["task_complete_at"]:
        done = parse_ts(state["task_complete_at"])
        if done and (now - done).total_seconds() < DONE_TTL_SEC:
            return "done"
    return "idle"


def short_age(seconds):
    if seconds is None:
        return ""
    seconds = int(max(seconds, 0))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def truncate(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


RE_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def location(cwd):
    """A readable place name for a session.

    Sidebar chats run with a cwd of ~/.copilot/chats/<uuid>, so the usual
    basename is an opaque UUID rather than anywhere recognisable.
    """
    base = os.path.basename((cwd or "").rstrip("/"))
    if not base:
        return "?"
    if RE_UUID.match(base):
        return "chat"
    return base


def blocked_reason(state):
    for perm in state["pending_perms"].values():
        detail = truncate(perm["detail"], 60)
        kind = perm["kind"]
        return f"approve {kind}" + (f": {detail}" if detail else "")
    for tool in state["open_tools"].values():
        if tool["name"] == "ask_user":
            question = tool["args"].get("question") if tool["args"] else ""
            return "asked you: " + truncate(question, 70) if question else "waiting on your answer"
    return "waiting on you"


def activity(state):
    tools = [t for t in state["open_tools"].values() if t["name"] != "task"]
    subagents = [t for t in state["open_tools"].values() if t["name"] == "task"]
    parts = []
    if tools:
        parts.append(", ".join(sorted({t["name"] for t in tools})))
    if subagents:
        parts.append(f"{len(subagents)} sub-agent{'s' if len(subagents) > 1 else ''}")
    return " + ".join(parts) or "thinking"


def collect(now):
    sessions = []
    for lock in glob.glob(os.path.join(SESSION_DIR, "*", "inuse.*.lock")):
        match = re.search(r"inuse\.(\d+)\.lock$", lock)
        if not match or not pid_alive(int(match.group(1))):
            continue

        sdir = os.path.dirname(lock)
        events = os.path.join(sdir, "events.jsonl")
        if not os.path.exists(events):
            continue

        state = replay(events)
        status = classify(state, now)
        if status is None:
            continue

        meta = read_workspace(os.path.join(sdir, "workspace.yaml"))
        last = parse_ts(state["last_ts"])
        age = (now - last).total_seconds() if last else None
        if status == "idle" and age is not None and age > IDLE_TTL_SEC:
            continue

        sessions.append({
            "id": os.path.basename(sdir),
            "status": status,
            "name": meta.get("name") or os.path.basename(sdir)[:8],
            "cwd": meta.get("cwd") or "",
            "client": meta.get("client_name") or "",
            "age": age,
            "activity": activity(state),
            "reason": blocked_reason(state) if status == "blocked" else "",
            "error": state["error"],
            "subagents": sum(
                1 for t in state["open_tools"].values() if t["name"] == "task"
            ),
        })

    sessions.sort(key=lambda s: (STATE_ORDER.index(s["status"]), s["age"] or 0))
    return sessions


def build_tooltip(sessions, counts, subagents):
    lines = []
    summary = []
    if counts["working"]:
        summary.append(f"{counts['working']} working")
    if counts["blocked"]:
        summary.append(f"{counts['blocked']} blocked")
    if counts["done"]:
        summary.append(f"{counts['done']} done")
    if counts["idle"]:
        summary.append(f"{counts['idle']} idle")
    if subagents:
        summary.append(f"{subagents} sub-agent{'s' if subagents > 1 else ''}")
    lines.append(f"<b>Copilot agents</b> \u2014 {', '.join(summary) or 'none'}")

    for s in sessions[:TOOLTIP_MAX]:
        lines.append("")
        where = location(s["cwd"])
        head = f"{STATE_ICONS[s['status']]} <b>{html.escape(where)}</b>"
        age = short_age(s["age"])
        if age:
            head += f"  <span alpha='60%'>{age} ago</span>"
        lines.append(head)
        lines.append(f"   {html.escape(truncate(s['name'], 64))}")
        if s["status"] == "blocked":
            lines.append(f"   \u21b3 {html.escape(truncate(s['reason'], 80))}")
        elif s["status"] == "working":
            lines.append(f"   \u21b3 {html.escape(s['activity'])}")
        elif s["status"] == "done":
            lines.append("   \u21b3 task complete")
        if s["error"]:
            lines.append(f"   \u21b3 {html.escape(truncate(s['error'], 80))}")

    if len(sessions) > TOOLTIP_MAX:
        extra = len(sessions) - TOOLTIP_MAX
        lines.append("")
        lines.append(f"<span alpha='60%'>+{extra} more dormant</span>")

    lines.append("")
    lines.append("<i>Left: focus the IDE \u00b7 Right: session summary</i>")
    return "\n".join(lines)


def main():
    now = datetime.now(timezone.utc)
    sessions = collect(now)

    counts = {state: 0 for state in STATE_ORDER}
    for s in sessions:
        counts[s["status"]] += 1
    subagents = sum(s["subagents"] for s in sessions)

    if not sessions:
        print(json.dumps({
            "text": f"{ICON_AGENT} {ICON_IDLE} 0",
            "tooltip": "<b>Copilot agents</b> \u2014 none running",
            "class": "none",
        }))
        return

    # Highest-priority state drives the icon, the colour and the number, so the
    # text keeps one fixed shape: icon, glyph, two-column count.
    state = next(s for s in STATE_ORDER if counts[s])
    if state == "working":
        # One frame per refresh: the divisor tracks the module's interval.
        glyph = SPINNER[int(time.time() / 3) % len(SPINNER)]
        shown = counts["working"] + subagents
    else:
        glyph = STATE_ICONS[state]
        shown = counts[state]

    classes = [state]
    if subagents:
        classes.append("subagents")

    print(json.dumps({
        "text": f"{ICON_AGENT} {glyph}{min(shown, 99):>2}",
        "tooltip": build_tooltip(sessions, counts, subagents),
        "class": classes,
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never let the bar go blank on a parse hiccup
        print(json.dumps({
            "text": f"{ICON_AGENT} {ICON_BLOCKED} \u2013",
            "tooltip": f"ai-agents error: {html.escape(str(e))}",
            "class": "error",
        }))
