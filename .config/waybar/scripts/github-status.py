#!/usr/bin/env python3
"""Waybar module: GitHub review queue and pull-request activity.

Answers the two questions worth a glance at the bar:

    * are there PRs waiting on my review?
    * did anything happen on my PRs -- new comments, reviews, red CI?

Data comes from one GraphQL round trip per authenticated `gh` account, so a
work account and a personal account are both covered. Results are cached, and
the cache is what waybar reads: the module can be polled often (cheap, local)
while GitHub itself is only hit every FETCH_TTL seconds.

"New activity" is measured against what you have already acknowledged, not
against wall-clock time -- clicking the module marks the current comment and
review counts as seen, and only later ones count as new.

Bar text:  {github} {state glyph}{count}
Classes:   review > activity > cifail > ready > clear (+ stale / error)

Usage:
    github-status.py              print the waybar JSON (fetch if cache stale)
    github-status.py --refresh    force a fetch first
    github-status.py --open       acknowledge, then open the relevant page
    github-status.py --ack        acknowledge without opening anything
"""
import html
import json
import os
import subprocess
import sys
import time

CACHE_DIR = os.environ.get(
    "XDG_CACHE_HOME", os.path.expanduser("~/.cache")
)
CACHE = os.path.join(CACHE_DIR, "waybar-github-status.json")

FETCH_TTL = int(os.environ.get("WAYBAR_GH_TTL", "300"))
GH_TIMEOUT = 25

ICON_GITHUB = "\U000f02a4"    # github
ICON_REVIEW = "\U000f0208"    # eye        -- PRs waiting on me
ICON_ACTIVITY = "\U000f017a"  # comment    -- new noise on my PRs
ICON_CIFAIL = "\U000f0026"    # alert      -- my PR has red checks
ICON_READY = "\U000f012c"     # check      -- approved and green

# Most urgent first; the winner picks the glyph, the count and the CSS class.
# Review requests outrank red CI on purpose: a long-lived failing check on one
# of your own old PRs is chronic noise, a review request is a thing to do.
STATES = ("review", "activity", "cifail", "ready", "clear")
STATE_ICONS = {
    "cifail": ICON_CIFAIL,
    "review": ICON_REVIEW,
    "activity": ICON_ACTIVITY,
    "ready": ICON_READY,
    "clear": ICON_READY,
}

QUERY = """
query {
  viewer { login }
  reviewRequests: search(
    query: "is:open is:pr review-requested:@me archived:false"
    type: ISSUE
    first: 25
  ) {
    issueCount
    nodes {
      ... on PullRequest {
        number url title isDraft updatedAt
        repository { nameWithOwner }
        author { login }
      }
    }
  }
  mine: search(
    query: "is:open is:pr author:@me archived:false"
    type: ISSUE
    first: 25
  ) {
    issueCount
    nodes {
      ... on PullRequest {
        number url title isDraft updatedAt
        repository { nameWithOwner }
        reviewDecision
        comments { totalCount }
        reviews { totalCount }
        commits(last: 1) {
          nodes { commit { statusCheckRollup { state } } }
        }
      }
    }
  }
}
"""


def run(cmd, env=None, timeout=GH_TIMEOUT):
    full_env = dict(os.environ, **(env or {}))
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=full_env
    )


def accounts():
    """Authenticated github.com logins, active account first."""
    proc = run(["gh", "auth", "status", "--hostname", "github.com"], timeout=15)
    found, active = [], None
    current = None
    for line in (proc.stdout + proc.stderr).splitlines():
        stripped = line.strip()
        if "Logged in to" in stripped and " account " in stripped:
            current = stripped.split(" account ", 1)[1].split()[0]
            found.append(current)
        elif stripped.startswith("- Active account: true") and current:
            active = current
    if active:
        found.sort(key=lambda a: a != active)
    return found


def token_for(login):
    proc = run(["gh", "auth", "token", "--hostname", "github.com", "--user", login],
               timeout=15)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def rollup(pr):
    nodes = ((pr.get("commits") or {}).get("nodes") or [])
    if not nodes:
        return None
    check = (nodes[0].get("commit") or {}).get("statusCheckRollup")
    return (check or {}).get("state")


def fetch():
    """Query every authenticated account. Raises if none could be reached."""
    logins = accounts()
    if not logins:
        raise RuntimeError("no authenticated gh account")

    reviews, mine, errors = [], [], []
    for login in logins:
        token = token_for(login)
        if not token:
            errors.append(f"{login}: no token")
            continue
        # GH_TOKEN pins the request to this account regardless of which one
        # `gh auth switch` last made active.
        proc = run(
            ["gh", "api", "graphql", "-f", f"query={QUERY}"],
            env={"GH_TOKEN": token, "GH_HOST": "github.com"},
        )
        if proc.returncode != 0:
            errors.append(f"{login}: {proc.stderr.strip().splitlines()[-1:] or ''}")
            continue
        try:
            data = json.loads(proc.stdout)["data"]
        except (ValueError, KeyError, TypeError):
            errors.append(f"{login}: bad response")
            continue

        for pr in (data.get("reviewRequests") or {}).get("nodes") or []:
            if not pr:
                continue
            reviews.append({
                "account": login,
                "url": pr["url"],
                "repo": pr["repository"]["nameWithOwner"],
                "number": pr["number"],
                "title": pr["title"],
                "author": (pr.get("author") or {}).get("login") or "?",
                "draft": pr.get("isDraft", False),
            })

        for pr in (data.get("mine") or {}).get("nodes") or []:
            if not pr:
                continue
            mine.append({
                "account": login,
                "url": pr["url"],
                "repo": pr["repository"]["nameWithOwner"],
                "number": pr["number"],
                "title": pr["title"],
                "draft": pr.get("isDraft", False),
                "decision": pr.get("reviewDecision"),
                "comments": (pr.get("comments") or {}).get("totalCount", 0),
                "reviews": (pr.get("reviews") or {}).get("totalCount", 0),
                "checks": rollup(pr),
            })

    if errors and not reviews and not mine:
        raise RuntimeError("; ".join(errors) or "gh query failed")

    return {"fetched_at": time.time(), "reviews": reviews, "mine": mine,
            "errors": errors}


def load_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cache(cache):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, CACHE)
    except OSError:
        pass


def get_data(cache, force):
    """Return (payload, stale, error). Falls back to the last good payload."""
    payload = cache.get("payload")
    age = time.time() - (payload or {}).get("fetched_at", 0)
    if payload and not force and age < FETCH_TTL:
        return payload, False, None
    try:
        fresh = fetch()
    except Exception as e:
        return payload, True, str(e)
    cache["payload"] = fresh
    return fresh, False, None


def unseen(payload, cache):
    """My PRs that gained comments or reviews since the last acknowledgement."""
    seen = cache.get("seen") or {}
    out = []
    for pr in payload.get("mine") or []:
        mark = seen.get(pr["url"])
        if mark is None:
            continue  # never acknowledged: seeded on first run, not "new"
        delta = ((pr["comments"] - mark.get("comments", 0))
                 + (pr["reviews"] - mark.get("reviews", 0)))
        if delta > 0:
            out.append((pr, delta))
    return out


def seed_seen(payload, cache):
    """Record current counts for PRs we have never seen before.

    Without this every existing comment would read as new the first time the
    module ever runs.
    """
    seen = cache.setdefault("seen", {})
    for pr in payload.get("mine") or []:
        seen.setdefault(pr["url"],
                        {"comments": pr["comments"], "reviews": pr["reviews"]})
    live = {pr["url"] for pr in payload.get("mine") or []}
    for url in [u for u in seen if u not in live]:
        del seen[url]


def acknowledge(payload, cache):
    seen = cache.setdefault("seen", {})
    for pr in payload.get("mine") or []:
        seen[pr["url"]] = {"comments": pr["comments"], "reviews": pr["reviews"]}


def truncate(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def summarise(payload, cache):
    reviews = [pr for pr in payload.get("reviews") or [] if not pr["draft"]]
    activity = unseen(payload, cache)
    cifail = [pr for pr in payload.get("mine") or []
              if pr["checks"] in ("FAILURE", "ERROR")]
    ready = [pr for pr in payload.get("mine") or []
             if pr["decision"] == "APPROVED"
             and pr["checks"] in ("SUCCESS", None)
             and not pr["draft"]]
    return {"cifail": cifail, "review": reviews, "activity": activity,
            "ready": ready}


def build_tooltip(payload, groups, stale, error, multi_account):
    lines = ["<b>GitHub</b>"]

    def tag(pr):
        return f" <span alpha='60%'>[{html.escape(pr['account'])}]</span>" if multi_account else ""

    if groups["review"]:
        lines.append("")
        lines.append(f"{ICON_REVIEW} <b>Waiting on your review ({len(groups['review'])})</b>")
        for pr in groups["review"][:6]:
            lines.append(f"   {html.escape(pr['repo'])}#{pr['number']}"
                         f" <span alpha='60%'>@{html.escape(pr['author'])}</span>{tag(pr)}")
            lines.append(f"      {html.escape(truncate(pr['title'], 58))}")

    if groups["activity"]:
        lines.append("")
        lines.append(f"{ICON_ACTIVITY} <b>New on your PRs ({len(groups['activity'])})</b>")
        for pr, delta in groups["activity"][:6]:
            lines.append(f"   {html.escape(pr['repo'])}#{pr['number']}"
                         f" <span alpha='60%'>+{delta}</span>{tag(pr)}")
            lines.append(f"      {html.escape(truncate(pr['title'], 58))}")

    if groups["cifail"]:
        lines.append("")
        lines.append(f"{ICON_CIFAIL} <b>Checks failing ({len(groups['cifail'])})</b>")
        for pr in groups["cifail"][:6]:
            lines.append(f"   {html.escape(pr['repo'])}#{pr['number']}{tag(pr)}")

    if groups["ready"]:
        lines.append("")
        lines.append(f"{ICON_READY} <b>Approved and green ({len(groups['ready'])})</b>")
        for pr in groups["ready"][:6]:
            lines.append(f"   {html.escape(pr['repo'])}#{pr['number']}{tag(pr)}")

    if len(lines) == 1:
        lines.append("")
        lines.append("Nothing needs you \u2014 no reviews, no new comments.")

    total_mine = len(payload.get("mine") or [])
    lines.append("")
    lines.append(f"<span alpha='60%'>{total_mine} open PR(s) authored by you</span>")

    if stale or error:
        age = int(time.time() - payload.get("fetched_at", 0)) if payload else 0
        note = f"offline \u2014 showing data from {age // 60}m ago" if payload else "unavailable"
        lines.append(f"<span alpha='60%'>{html.escape(note)}</span>")
    if payload and payload.get("errors"):
        for err in payload["errors"][:2]:
            lines.append(f"<span alpha='60%'>{html.escape(str(err))}</span>")

    lines.append("")
    lines.append("<i>Left: open + mark seen \u00b7 Right: mark seen \u00b7 Middle: refresh</i>")
    return "\n".join(lines)


def open_url(url):
    try:
        subprocess.Popen(["xdg-open", url],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def main():
    args = set(sys.argv[1:])
    cache = load_cache()
    # A click must feel instant, so only --refresh goes to the network; the
    # other actions work off the cache (at most FETCH_TTL seconds old).
    payload, stale, error = get_data(cache, force="--refresh" in args)

    if payload is None:
        save_cache(cache)
        print(json.dumps({
            "text": f"{ICON_GITHUB} {ICON_CIFAIL} \u2013",
            "tooltip": f"GitHub unavailable: {html.escape(str(error))}",
            "class": "error",
        }))
        return

    seed_seen(payload, cache)
    groups = summarise(payload, cache)

    if args & {"--ack", "--open"}:
        if "--open" in args:
            target = None
            if groups["review"]:
                target = "https://github.com/pulls/review-requested"
            elif groups["activity"]:
                target = groups["activity"][0][0]["url"]
            elif groups["cifail"]:
                target = groups["cifail"][0]["url"]
            open_url(target or "https://github.com/pulls")
        acknowledge(payload, cache)
        groups = summarise(payload, cache)

    save_cache(cache)

    state = next((s for s in STATES if groups.get(s)), "clear")
    count = len(groups.get(state) or [])
    classes = [state]
    if stale or error:
        classes.append("stale")

    multi = len({pr["account"] for pr in (payload.get("mine") or [])
                 + (payload.get("reviews") or [])}) > 1

    print(json.dumps({
        "text": f"{ICON_GITHUB} {STATE_ICONS[state]}{min(count, 99):>2}",
        "tooltip": build_tooltip(payload, groups, stale, error, multi),
        "class": classes,
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({
            "text": f"{ICON_GITHUB} {ICON_CIFAIL} \u2013",
            "tooltip": f"github-status error: {html.escape(str(e))}",
            "class": "error",
        }))
