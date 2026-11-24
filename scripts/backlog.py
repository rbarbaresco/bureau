#!/usr/bin/env python3
"""Bureau's own open issues as a compact view, and a count of how often cards hit them (#129).

Usage:
  backlog.py                                   print the view
  backlog.py hit <n> <card-dir> '<what>'       log that a card hit known issue #n (refused if #n is not in the view)
  backlog.py summary                           open issues by hit count
The view (desk/backlog.md) holds each open issue's number, title, labels and short version: the `**Short:**` paragraph
at the top of its body (the issue skill writes it), at most 3 lines; an issue without one shows its title only. It is
rebuilt with `gh issue list` in Bureau's root (so the repo is this checkout's remote) when missing or over a day old;
if gh fails, the old view is printed with its age. A hit is always appended to desk/backlog-hits.jsonl; when the card's
issue_comments setting is on (/setup-bureau, the standing approval for that one write) it is also posted on the issue:
with the card id and what was hit for a Bureau card, the date only for a card from another repo (Bureau's may be public).
"""
import collections
import datetime
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desk  # noqa: E402
import sessions  # noqa: E402

DAY = 24 * 3600
SHORT = re.compile(r"\s*\*\*Short:\*\*[ \t]*(.*?)(?:\n[ \t]*\n|\Z)", re.S)  # only at the very top of the body
HEAD = re.compile(r"#(\d+) (.*?)(?: \[[^\]]*\])?")  # labels in [] are not part of the title


def short(body):
    m = SHORT.match((body or "").replace("\r\n", "\n"))
    lines = []
    for line in (m[1].splitlines() if m else []):
        if re.match(r"\s*(#|\*\*)", line):
            break  # a heading or the next bold section, with no blank line before it
        lines += [line.strip()] if line.strip() else []
    return "\n".join(lines[:3])[:400]


def gh(*args):
    r = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or f"gh exited {r.returncode}")
    return r.stdout


def refresh(path):
    issues = json.loads(gh("issue", "list", "--state", "open", "--limit", "200", "--json", "number,title,labels,body"))
    if not isinstance(issues, list) or not all(isinstance(i, dict) for i in issues):
        raise ValueError("gh issue list did not return a list of issues")
    out = [f"Bureau's open issues, {datetime.date.today()} (#, title, short version):"]
    for i in sorted(issues, key=lambda i: -i["number"]):
        labels = ",".join(lb["name"] for lb in i.get("labels") or [])
        out.append(f"#{i['number']} {i['title']}" + (f" [{labels}]" if labels else ""))
        out += ["  " + line for line in short(i.get("body")).splitlines()]
    tmp = f"{path}.{os.getpid()}.tmp"  # one per process: two sessions refreshing at once don't share it
    with open(tmp, "w") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, path)  # a failed write keeps the old view


def view(desk_dir=None, now=None):
    path = os.path.join(desk_dir or sessions.DESK, "backlog.md")
    age = (now or time.time()) - os.path.getmtime(path) if os.path.exists(path) else None
    note = ""
    if age is None or age > DAY:
        try:
            refresh(path)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as e:
            if age is None:
                return f"Bureau's backlog is unavailable: {e}\n"
            note = f"(this view is {int(age // DAY)} day(s) old; refreshing failed: {e})\n"
    with open(path) as f:
        return note + f.read()


def titles(text):
    return dict(m.groups() for m in map(HEAD.fullmatch, text.splitlines()) if m)


def hit(issue, card, what, desk_dir=None, today=None):
    n = int(str(issue).lstrip("#"))
    if not os.path.isdir(card):
        raise ValueError(f"{card} is not a card folder")
    text = view(desk_dir)
    if str(n) not in titles(text):
        raise ValueError(f"#{n} is not an open issue in the backlog view; check the number. {text.splitlines()[0]}")
    card_id = os.path.basename(os.path.realpath(card))
    state = os.path.join(card, "state.json")
    cfg = (desk.load(card).get("settings") or {}) if os.path.exists(state) else desk.settings()  # not started: today's
    date = str(today or datetime.date.today())
    with open(os.path.join(desk_dir or sessions.DESK, "backlog-hits.jsonl"), "a") as f:
        f.write(json.dumps({"issue": n, "card": card_id, "date": date, "what": what}) + "\n")
    if cfg.get("issue_comments") != "on":
        return f"Logged a hit on #{n}."
    # Bureau's repo may be public: a card from another repo (a Jira key, a private path) posts the date only
    own = card_id.startswith("bureau-") or os.path.isdir(os.path.join(card, "worktrees", "bureau"))
    body = f"Hit again on {card_id}: {what}" if own else f"Hit again ({date}) on a card outside Bureau."
    try:
        gh("issue", "comment", str(n), "--body", body)
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        return f"Logged a hit on #{n}; commenting on the issue failed: {e}"
    return f"Logged a hit on #{n} and commented on the issue."


def summary(desk_dir=None):
    d = desk_dir or sessions.DESK
    text = view(d)
    open_issues = titles(text)
    if not open_issues:
        return text.rstrip("\n")  # no view: say so rather than an empty ranking
    counts, last = collections.Counter(), {}
    try:
        with open(os.path.join(d, "backlog-hits.jsonl")) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    counts[str(e["issue"])] += 1
                    last[str(e["issue"])] = e["card"]
                except (ValueError, KeyError, TypeError):
                    continue  # a torn line from an interrupted write
    except FileNotFoundError:
        pass
    ranked = sorted((n for n in counts if n in open_issues), key=lambda n: (-counts[n], int(n)))
    out = [f"{counts[n]:>3}  #{n} {open_issues[n]} (last: {last[n]})" for n in ranked]
    out.append(f"{len(open_issues) - len(ranked)} open issue(s) with no hits logged.")
    return "\n".join(out)


def main(argv):
    if not argv:
        print(view(), end="")
    elif argv[0] == "summary" and len(argv) == 1:
        print(summary())
    elif argv[0] == "hit" and len(argv) == 4 and argv[1].lstrip("#").isdigit():
        try:
            print(hit(*argv[1:]))
        except (OSError, ValueError) as e:
            sys.exit(f"backlog.py: {e}")
    else:
        sys.exit("Usage: backlog.py | backlog.py hit <n> <card-dir> '<what>' | backlog.py summary")


if __name__ == "__main__":
    main(sys.argv[1:])
