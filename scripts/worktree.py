#!/usr/bin/env python3
"""Create a card's worktree from a registered clone.

Usage: worktree.py <card-dir> <repo-name> [--repos repos.yaml]
Creates <card-dir>/worktrees/<repo-name> on branch bureau/<card-id>, from the repo's `base`.
"""
import os
import re
import subprocess
import sys

BUREAU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_repos(path):
    # shortcut: only the two-level layout of repos.yaml.sample, no '#' inside values; use PyYAML if it grows
    repos, cur = {}, None
    with open(path) as f:
        for line in f:
            line = line.split("#")[0].rstrip()
            if not line.strip() or line.strip() == "repos:":
                continue
            if re.match(r"^  \S[^:]*:$", line):
                cur = line.strip()[:-1]
                repos[cur] = {}
            elif cur and ":" in line:
                k, v = line.strip().split(":", 1)
                repos[cur][k] = os.path.expanduser(v.strip())
    return repos


def add(card_dir, name, repos_file):
    repos = read_repos(repos_file)
    if name not in repos:
        sys.exit(f"unknown repo '{name}'; known: {', '.join(repos) or 'none'}")
    clone, base = repos[name]["path"], repos[name].get("base", "main")
    wt = os.path.join(os.path.abspath(card_dir), "worktrees", name)
    branch = "bureau/" + os.path.basename(os.path.abspath(card_dir))
    exists = subprocess.run(["git", "-C", clone, "rev-parse", "--verify", "-q", branch],
                            capture_output=True).returncode == 0
    cmd = ["git", "-C", clone, "worktree", "add"] + ([wt, branch] if exists else ["-b", branch, wt, base])
    subprocess.run(cmd, check=True)
    # a killed pytest run leaves .coverage.* behind and the untracked files block the push; the exclude file is
    # shared by the whole clone, so this also hides them in the clone's other worktrees
    path = subprocess.run(["git", "-C", wt, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
                          check=True, capture_output=True, text=True).stdout.strip()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    have = open(path).read().splitlines() if os.path.exists(path) else []
    with open(path, "a") as f:
        f.writelines(p + "\n" for p in (".coverage", ".coverage.*") if p not in have)
    return wt


if __name__ == "__main__":
    a = sys.argv[1:]
    repos_file = a[a.index("--repos") + 1] if "--repos" in a else os.path.join(BUREAU, "repos.yaml")
    if len(a) < 2:
        sys.exit(__doc__)
    print(add(a[0], a[1], repos_file))
