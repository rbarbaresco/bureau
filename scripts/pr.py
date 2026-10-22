#!/usr/bin/env python3
"""Open the draft PR for a card whose `pr` step the human approved.

Usage: pr.py <card-dir>
Pushes bureau/<card-id> from the card's only worktree, opens a draft PR (or reuses the branch's open one)
from desk/<card>/pr.md (first line = title, rest = body), and appends the link to pr.md.
Exits non-zero without touching the card state on any failure; safe to run again.
"""
import json
import os
import subprocess
import sys

import worktree

OPENED = "\n## Opened\n"


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, **kw)
    if r.returncode:
        sys.exit(f"{' '.join(args[:4])} failed: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def open_pr(card):
    card = os.path.abspath(card)
    state = load(os.path.join(card, "state.json"))
    if state.get("awaiting") != "pr":
        sys.exit(f"{card}: step 'pr' is not awaiting (awaiting={state.get('awaiting')}); nothing to open.")
    if not load(os.path.join(card, "approvals.json")).get("pr"):
        sys.exit("step 'pr' is not approved; the human must run /approve.")
    trees = sorted(os.listdir(os.path.join(card, "worktrees"))) if os.path.isdir(os.path.join(card, "worktrees")) else []
    if len(trees) != 1:  # shortcut: one worktree per card, no multi-repo PRs
        sys.exit(f"expected exactly one worktree under {card}/worktrees, found {len(trees)}.")
    repo, wt = trees[0], os.path.join(card, "worktrees", trees[0])
    with open(os.path.join(card, "pr.md")) as f:
        draft = f.read().split(OPENED)[0]
    title, _, body = draft.strip().partition("\n")
    title = title.lstrip("# ").strip()
    if not title:
        sys.exit(f"{card}/pr.md is empty: first line is the PR title.")
    if run(["git", "-C", wt, "status", "--porcelain"]):
        sys.exit(f"uncommitted changes in {wt}: commit them first.")
    base = worktree.read_repos(os.environ.get("BUREAU_REPOS", os.path.join(worktree.BUREAU, "repos.yaml")))[repo].get("base", "main")
    branch = "bureau/" + os.path.basename(card)
    run(["git", "-C", wt, "push", "-u", "origin", branch])
    url = run(["gh", "pr", "list", "--head", branch, "--json", "url", "--jq", ".[0].url // empty"], cwd=wt)
    if not url:
        url = run(["gh", "pr", "create", "--draft", "--base", base, "--head", branch, "--title", title,
                   "--body-file", "-"], cwd=wt, input=body.strip() + "\n")
    with open(os.path.join(card, "pr.md"), "w") as f:
        f.write(f"{draft.rstrip()}\n{OPENED}\n{url}\n")
    return url


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(open_pr(sys.argv[1]))
