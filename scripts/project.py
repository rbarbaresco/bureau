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
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in text.splitlines() if l.strip().startswith("|")]
    tasks = []
    for r in rows[2:]:  # header and separator
        if len(r) != 5:
            raise ValueError(f"tasks.md row needs 5 columns: {r}")
        i, title, repo, blocked, edge = r
        if not re.fullmatch(r"[\w.-]+", i) or edge not in EDGES:
            raise ValueError(f"tasks.md row {i!r}: bad id, or edge {edge!r} is not one of {EDGES}")
        tasks.append({"id": i, "title": title, "repo": repo,
                      "blocked": [] if blocked == "-" else [b.strip() for b in blocked.split(",")], "edge": edge})
    ids = [t["id"] for t in tasks]
    if not tasks or len(set(ids)) != len(ids):
        raise ValueError("tasks.md needs rows with duplicate-free ids")
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
    r = run(["gh", "pr", "view", m[1], "--json", "mergedAt", "-q", ".mergedAt"], capture_output=True, text=True)
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
        wait = [b for b in t["blocked"] if b not in done]
        state = "merged" if t["id"] in done else f"waits on {', '.join(wait)}" if wait else "ready"
        rows.append({"id": t["id"], "child": os.path.basename(kid), "title": t["title"], "step": s["current"],
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
