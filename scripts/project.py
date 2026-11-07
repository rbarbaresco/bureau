#!/usr/bin/env python3
"""A parent card and its children: desk/<parent>/<parent>-<id>/, one `task` card per row of the parent's tasks.md.

Usage: project.py spawn <parent-dir>    create the children (existing ones are left alone)
       project.py status <parent-dir>   print each child's step, awaiting and whether it is ready, waiting or merged

tasks.md is the only dependency record. Merge state is read from each child's PR (pr.md), not from a tracker.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import desk
import workflow

EDGES = ("-", "stated", "inferred")
CHILD_WORKFLOW = "task"


def parse(text):
    """Rows of the first table: [{id, title, repo, blocked, edge}]. Raises ValueError on a bad id, edge, blocker or cycle."""
    lines = [l.strip() for l in text.splitlines()]
    start = next((n for n, l in enumerate(lines) if l.startswith("|")), None)
    if start is None:
        raise ValueError("tasks.md has no table")
    table = []
    for l in lines[start:]:  # the first table only: notes and later tables below it are ignored
        if not l.startswith("|"):
            break
        table.append([c.strip() for c in l.strip("|").split("|")])
    if len(table) < 2 or not all(re.fullmatch(r":?-+:?", c) for c in table[1]):
        raise ValueError("tasks.md table needs a header row and a |---| separator row")
    if len(table) == 2:
        raise ValueError("tasks.md table has no task rows")
    tasks = []
    for r in table[2:]:
        if len(r) != 5:
            raise ValueError(f"tasks.md row needs 5 columns: {r}")
        i, title, repo, blocked, edge = r
        if not re.fullmatch(r"[\w.-]+", i):
            raise ValueError(f"tasks.md row {i!r}: bad id (letters, digits, . _ - only)")
        if not blocked:
            raise ValueError(f"task {i}: blocked by is empty, write - for none")
        blockers = [] if blocked == "-" else [b.strip() for b in blocked.split(",")]
        if edge not in EDGES or (edge == "-") != (not blockers):
            raise ValueError(f"task {i}: edge must be stated or inferred when it has blockers, - when it has none (got {edge!r})")
        tasks.append({"id": i, "title": title, "repo": repo, "blocked": blockers, "edge": edge})
    ids = [t["id"] for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("tasks.md has duplicate task ids")
    for t in tasks:
        for b in t["blocked"]:
            if b not in ids:
                raise ValueError(f"task {t['id']} is blocked by unknown task {b}")
    left = {t["id"]: set(t["blocked"]) for t in tasks}
    while left:
        free = [i for i, b in left.items() if not b]
        if not free:
            raise ValueError(f"cycle among tasks {sorted(left)}")
        left = {i: b - set(free) for i, b in left.items() if i not in free}
    return tasks


def _tasks(parent):
    with open(os.path.join(parent, "tasks.md")) as f:
        return parse(f.read())


def _child(parent, t):
    return os.path.join(parent, f"{os.path.basename(os.path.abspath(parent))}-{t['id']}")


def spawn(parent):
    pid = os.path.basename(os.path.abspath(parent))
    for t in _tasks(parent):
        kid = _child(parent, t)
        if os.path.exists(os.path.join(kid, "state.json")):
            continue
        os.makedirs(kid, exist_ok=True)
        with open(os.path.join(kid, "card.md"), "w") as f:
            f.write(f"# {t['title']}\n\nPart of {pid} (task {t['id']}, repo {t['repo']}). "
                    f"Blocked by: {', '.join(t['blocked']) or 'nothing'} ({t['edge']}).\n"
                    f"Details: ../card.md and ../tasks.md.\n")
        workflow.start(CHILD_WORKFLOW, kid)
        s = desk.load(kid)
        s["parent"] = pid
        desk.save(kid, s)


def is_merged(kid, run=subprocess.run):
    """The child's PR (the link under `## Opened` in pr.md) has a merge time."""
    try:
        with open(os.path.join(kid, "pr.md")) as f:
            m = re.search(r"^## Opened\n+(\S+)", f.read(), re.M)
    except FileNotFoundError:
        return False
    if not m:
        return False
    try:  # `next` calls this for every child: a missing or hanging gh means "not merged", never a crash
        r = run(["gh", "pr", "view", m[1], "--json", "mergedAt", "-q", ".mergedAt"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and bool(r.stdout.strip()) and r.stdout.strip() != "null"


def status(parent, merged=is_merged):
    tasks = _tasks(parent)
    done = {t["id"] for t in tasks if merged(_child(parent, t))}
    rows = []
    for t in tasks:
        kid = _child(parent, t)
        try:
            s = desk.load(kid)
        except FileNotFoundError:
            s = {"current": "not created"}
        except ValueError:  # unreadable state.json
            s = {"current": "unreadable"}
        wait = [b for b in t["blocked"] if b not in done]
        state = "merged" if t["id"] in done else f"waits on {', '.join(wait)}" if wait else "ready"
        rows.append({"id": t["id"], "child": os.path.basename(kid), "title": t["title"], "step": s.get("current", "?"),
                     "awaiting": s.get("awaiting") or "-", "state": state})
    return rows


def table(parent, merged=is_merged):
    return "\n".join(f"  {r['child']:<16}{r['step']:<12}awaiting {r['awaiting']:<10}{r['state']:<16}{r['title']}"
                     for r in status(parent, merged))


if __name__ == "__main__":
    a = sys.argv[1:]
    try:
        if a[:1] == ["spawn"] and len(a) == 2:
            spawn(a[1])
        elif a[:1] == ["status"] and len(a) == 2:
            print(table(a[1]))
        else:
            sys.exit(__doc__)
    except (ValueError, OSError) as e:
        sys.exit(f"error: {e}")
