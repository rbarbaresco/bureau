#!/usr/bin/env python3
"""Move a finished card out of desk/ into archive/ (next to desk/) and remove its worktrees.

Usage: archive.py <card-dir> [--force]
Refuses, moving nothing, unless the card is directly under desk/, `done`, not held by another live
session, not already archived, and every worktree is clean with its branch pushed. Local branches are kept.
A dirty or unpushed worktree is refused with a list of what would be lost; --force archives anyway
(uncommitted changes are discarded, unpushed commits stay on the local branch). The caller confirms with the human first.
Ignored files in a worktree (a local .env) are deleted with it. Worktrees go first, so a failure
partway can leave the card on the desk with some worktrees already removed; running it again finishes the job.
Archive dir: $BUREAU_ARCHIVE, else archive/ next to desk/ (scripts/ui.py reads the same).
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


def archive(card, desk=sessions.DESK, force=False):
    card = os.path.realpath(card)
    cid = os.path.basename(card)
    if os.path.dirname(card) != os.path.realpath(desk) or not re.fullmatch(r"[\w.-]+", cid):
        sys.exit(f"{card}: not a card directly under {desk}.")
    try:
        with open(os.path.join(card, "state.json")) as f:
            current = json.load(f).get("current")
    except (FileNotFoundError, json.JSONDecodeError):
        sys.exit(f"{cid}: no readable state.json; only a done card can be archived.")
    if current != "done":
        sys.exit(f"{cid} is at step '{current}', not done; only a done card can be archived.")
    dest = os.path.join(os.environ.get("BUREAU_ARCHIVE") or os.path.join(os.path.dirname(desk), "archive"), cid)
    if os.path.exists(dest):
        sys.exit(f"{dest} already exists.")
    e = sessions.last(card)
    if e and sessions.status(card, None) == "held" and e["pid"] != sessions.my_pid():  # my own claim is not a holder
        sys.exit(f"{cid} is held by live session {e['session']} (pid {e['pid']}); close it first.")
    root = os.path.join(card, "worktrees")
    trees = sorted(os.path.join(root, d) for d in os.listdir(root)) if os.path.isdir(root) else []
    lost = []
    for wt in trees:
        if os.path.realpath(git(wt, "rev-parse", "--show-toplevel").stdout.strip()) != os.path.realpath(wt):
            sys.exit(f"{wt} is not a git worktree.")
        if git(wt, "status", "--porcelain").stdout.strip():
            lost.append(f"{wt}: uncommitted changes would be discarded")
        ahead = git(wt, "rev-list", "--count", "@{u}..HEAD")
        if ahead.returncode or ahead.stdout.strip() != "0":
            lost.append(f"{wt}: branch is not fully pushed (no upstream, or commits ahead of it); the commits stay on the local branch")
    if lost and not force:
        sys.exit("\n".join(lost) + "\nPush or commit first, or re-run with --force to archive anyway.")
    for wt in trees:
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        r = subprocess.run(["git", "-C", os.path.dirname(common), "worktree", "remove", *(["--force"] if force else []), wt], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"git worktree remove {wt} failed: {r.stderr.strip()}")
    if trees:
        try:
            os.rmdir(root)
        except OSError:  # stray files: they move with the card
            pass
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(card, dest)
    return dest


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    if len(args) != 1:
        sys.exit(__doc__)
    print(archive(args[0], force="--force" in sys.argv))
