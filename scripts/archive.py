#!/usr/bin/env python3
"""Move a finished card out of desk/ into archive/ (next to desk/) and remove its worktrees.

Usage: archive.py <card-dir>
Refuses, moving nothing, unless the card is `done`, is not held by another live session, is not
already archived, and every worktree is clean with its branch pushed. Local branches are kept.
Worktrees go first, so a failure leaves the card on the desk; running it again finishes the job.
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
import sessions  # noqa: E402


def git(wt, *args):
    return subprocess.run(["git", "-C", wt, *args], capture_output=True, text=True)


def archive(card):
    card = os.path.abspath(card)
    cid, desk = os.path.basename(card), os.path.dirname(card)
    if not re.fullmatch(r"[\w.-]+", cid) or cid in (".", ".."):
        sys.exit(f"{card}: not a card directory.")
    try:
        with open(os.path.join(card, "state.json")) as f:
            current = json.load(f).get("current")
    except (FileNotFoundError, json.JSONDecodeError):
        sys.exit(f"{cid}: no readable state.json; only a done card can be archived.")
    if current != "done":
        sys.exit(f"{cid} is at step '{current}', not done; only a done card can be archived.")
    dest = os.path.join(os.path.dirname(desk), "archive", cid)
    if os.path.exists(dest):
        sys.exit(f"{dest} already exists.")
    e = sessions.last(card)
    if e and sessions.status(card, None) == "held" and e["pid"] != sessions.my_pid():  # my own claim is not a holder
        sys.exit(f"{cid} is held by live session {e['session']} (pid {e['pid']}); close it first.")
    root = os.path.join(card, "worktrees")
    trees = sorted(os.path.join(root, d) for d in os.listdir(root)) if os.path.isdir(root) else []
    for wt in trees:
        if git(wt, "status", "--porcelain").stdout.strip():
            sys.exit(f"uncommitted changes in {wt}: commit and push, or discard them.")
        ahead = git(wt, "rev-list", "--count", "@{u}..HEAD")
        if ahead.returncode or ahead.stdout.strip() != "0":
            sys.exit(f"{wt}: branch is not fully pushed (no upstream, or commits ahead of it); push it first.")
    for wt in trees:
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        r = subprocess.run(["git", "-C", os.path.dirname(common), "worktree", "remove", wt], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"git worktree remove {wt} failed: {r.stderr.strip()}")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(card, dest)
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(archive(sys.argv[1]))
