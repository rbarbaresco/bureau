#!/usr/bin/env python3
"""Create a card's worktree from a registered clone.

Usage: worktree.py <card-dir> <repo-name> [--repos repos.yaml] [--branch name]
Creates <card-dir>/worktrees/<repo-name> on branch bureau/<card-id>, from a freshly fetched origin/<base>
(local <base> if the fetch fails); the clone's local <base> is fast-forwarded when that is safe.
With --branch <name> it checks out the existing remote branch <name> instead (a PR's head), tracking origin.
"""
import os
import re
import subprocess
import sys

BUREAU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_repos(path):
    # shortcut: only the two-level layout of repos.yaml.sample, no '#' inside values; use PyYAML if it grows
    repos, cur = {}, None
    if not os.path.exists(path):  # still an OSError, so hooks/gate.py keeps denying
        raise FileNotFoundError(f"{path} not found; create it with: cp {os.path.join(BUREAU, 'repos.yaml.sample')} {path}")
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


def fresh_base(clone, base):
    """Fetch origin's <base> and fast-forward the local <base> when safe; return the ref a new card branches from."""
    git = lambda *a: subprocess.run(["git", "-C", clone, *a], capture_output=True, text=True)
    remote = "origin/" + base
    r = git("fetch", "origin", f"+refs/heads/{base}:refs/remotes/{remote}")
    if r.returncode:  # offline, auth, or no origin: still let the card start
        print(f"warning: fetch of origin {base} failed, branching from the local {base} (may be stale): "
              f"{r.stderr.strip()}", file=sys.stderr)
        return base
    if git("symbolic-ref", "-q", "--short", "HEAD").stdout.strip() == base:
        ok = not git("status", "--porcelain", "--untracked-files=no").stdout and \
            not git("merge", "-q", "--ff-only", remote).returncode
    else:  # only fast-forwards; refused if <base> is checked out in another worktree
        ok = not git("fetch", "-q", ".", f"{remote}:{base}").returncode
    if not ok:
        print(f"warning: local {base} in {clone} left as is (uncommitted changes, diverged, or checked out "
              f"elsewhere); the card still starts from {remote}", file=sys.stderr)
    return remote


def add(card_dir, name, repos_file, branch=None):
    try:
        repos = read_repos(repos_file)
    except FileNotFoundError as e:
        sys.exit(str(e))
    if name not in repos:
        sys.exit(f"unknown repo '{name}'; known: {', '.join(repos) or 'none'}")
    clone, base = repos[name]["path"], repos[name].get("base", "main")
    wt = os.path.join(os.path.abspath(card_dir), "worktrees", name)
    track = []
    if branch:
        base, track = "origin/" + branch, ["--track"]
        subprocess.run(["git", "-C", clone, "fetch", "origin", branch], check=True)
    else:
        branch = "bureau/" + os.path.basename(os.path.abspath(card_dir))
    exists = subprocess.run(["git", "-C", clone, "rev-parse", "--verify", "-q", branch],
                            capture_output=True).returncode == 0
    if not track and not exists:
        base, track = fresh_base(clone, base), ["--no-track"]  # the card branch's upstream comes from pr.py's push -u
    cmd = ["git", "-C", clone, "worktree", "add"] + ([wt, branch] if exists else track + ["-b", branch, wt, base])
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
    print(add(a[0], a[1], repos_file, a[a.index("--branch") + 1] if "--branch" in a else None))
