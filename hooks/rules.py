#!/usr/bin/env python3
"""Resolve and acknowledge the instruction files that apply to a desk worktree.

Usage: rules.py <desk/.../worktrees/<repo>>
Prints every applicable rule file, then records a digest in <card>/ack.json.
gate.py denies code writes in the worktree until that digest is current.
"""
import hashlib
import json
import os
import re
import sys

BUREAU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WT = re.compile(r"^(?P<card>.*?/desk/.+?)/worktrees/(?P<repo>[^/]+)(?:/|$)")
NAMES = ("AGENTS.md", "CLAUDE.md")
IMPORT = re.compile(r"(?:^|\s)@([~./\w-][^\s]*)")


def clone_of(wt):
    """Original clone of a worktree: its ancestors hold rules the worktree's path loses."""
    git = os.path.join(wt, ".git")
    if os.path.isdir(git):
        return wt
    with open(git) as f:
        gitdir = f.read().split("gitdir:", 1)[1].strip()
    return gitdir.split("/.git/worktrees/")[0]


def _imports(path, seen, depth=0):
    if path in seen or depth > 5 or not os.path.isfile(path):
        return
    seen.append(path)
    with open(path, errors="replace") as f:
        text = f.read()
    for ref in IMPORT.findall(text):
        target = os.path.normpath(os.path.join(os.path.dirname(path), os.path.expanduser(ref)))
        _imports(target, seen, depth + 1)


def collect(wt):
    clone = os.path.realpath(clone_of(wt))
    dirs = []
    d = os.path.dirname(clone)
    while True:
        dirs.append(d)
        if d == "/":
            break
        d = os.path.dirname(d)
    # outermost first: Bureau base, clone ancestors, then the worktree's own files (branch-specific)
    roots = [BUREAU] + dirs[::-1] + [os.path.realpath(wt)]
    seen = []
    for root in roots:
        for name in NAMES:
            _imports(os.path.join(root, name), seen)
    return seen


def digest(wt):
    h = hashlib.sha256()
    for path in collect(wt):
        with open(path, "rb") as f:
            h.update(path.encode() + b"\0" + f.read() + b"\0")
    return h.hexdigest()


def main(wt):
    wt = os.path.abspath(wt)
    m = WT.match(wt + "/")
    if not m:
        sys.exit(f"not a desk worktree: {wt}")
    files = collect(wt)
    for path in files:
        with open(path, errors="replace") as f:
            print(f"===== {path} =====\n{f.read()}\n")
    ack_path = os.path.join(m["card"], "ack.json")
    try:
        with open(ack_path) as f:
            ack = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        ack = {}
    ack[m["repo"]] = digest(wt)
    with open(ack_path, "w") as f:
        json.dump(ack, f, indent=2)
    print(f"===== {len(files)} rule files loaded; ack recorded for {m['repo']} =====")


if __name__ == "__main__":
    main(sys.argv[1])
