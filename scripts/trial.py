#!/usr/bin/env python3
"""Make a checkout of a Bureau branch, PR or commit to run real tickets on before it is merged.

Usage: trial.py <branch|pr-number|commit> [dir]
Creates a detached worktree (default: ../bureau-trial-<ref> next to this checkout) and links its desk/ and
repos.yaml to this checkout's, so cards, config and claims are the real ones. Start Claude Code in <dir>.
Remove it with: git worktree remove <dir>
"""
import os
import re
import shutil
import subprocess
import sys

BUREAU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def add(ref, bureau=BUREAU, dest=None):
    real = os.path.realpath(bureau)
    git = lambda *a, **k: subprocess.run(["git", "-C", real, *a], capture_output=True, text=True, **k)
    dest = os.path.abspath(dest or os.path.join(real, "..", "bureau-trial-" + re.sub(r"[^\w.-]+", "-", ref)))
    if ref.startswith("-"):  # would reach git as an option
        sys.exit(f"unknown ref '{ref}'")
    if os.path.exists(dest):
        sys.exit(f"{dest} already exists; remove it with: git worktree remove {dest}")
    if ref.isdigit():  # a PR: its head is not a branch we have
        r = git("fetch", "origin", f"pull/{ref}/head")
        if r.returncode:
            sys.exit(f"cannot fetch PR {ref}: {r.stderr.strip()}")
        ref = "FETCH_HEAD"
    else:
        git("fetch", "-q", "origin", ref)  # best effort: a local branch or sha needs no remote
    sha = git("rev-parse", "--verify", "-q", ref + "^{commit}")
    if sha.returncode:
        sha = git("rev-parse", "--verify", "-q", "origin/" + ref + "^{commit}")
    if sha.returncode:
        sys.exit(f"unknown ref '{ref}'")
    r = git("worktree", "add", "--detach", dest, sha.stdout.strip())
    if r.returncode:
        sys.exit(r.stderr.strip())
    shutil.rmtree(os.path.join(dest, "desk"), ignore_errors=True)  # the branch tracks only desk/.gitkeep
    for name in ("desk", "repos.yaml"):
        os.symlink(os.path.realpath(os.path.join(real, name)),  # from a trial: the real file, not its link
                   os.path.join(dest, name))
    return dest


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    print(add(*sys.argv[1:]) if len(sys.argv) == 2 else add(sys.argv[1], dest=sys.argv[2]))
