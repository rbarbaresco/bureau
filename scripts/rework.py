#!/usr/bin/env python3
"""Check that a finished card has an open PR with feedback to work on, then print that feedback as JSON.

Usage: rework.py <card-dir>
Exits non-zero, saying what to run instead, unless the card exists locally, is done with its PR opened,
still has a worktree (or a branch to recreate one from), the PR is open and has review feedback.
Prints {"pr", "repo", "threads", "comments"}; read-only, safe to run again.
"""
import json
import os
import subprocess
import sys

import pr
import worktree

THREADS = """query($owner:String!,$repo:String!,$n:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$n){
reviewThreads(first:100){totalCount nodes{isResolved isOutdated path line
comments(first:20){nodes{author{login} body url createdAt}}}}}}}"""


def gh_json(args, cwd):
    return json.loads(pr.run(["gh", *args], cwd=cwd) or "null")


def find_repo(card, branch):
    """The repo name to rework in: its worktree if present, else a registered clone that still has the branch."""
    root = os.path.join(card, "worktrees")
    trees = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))) if os.path.isdir(root) else []
    if trees:
        return trees[0], os.path.join(root, trees[0])
    repos_file = os.environ.get("BUREAU_REPOS", os.path.join(worktree.BUREAU, "repos.yaml"))
    try:
        repos = worktree.read_repos(repos_file)
    except OSError as e:
        sys.exit(str(e))
    for name, r in repos.items():
        if subprocess.run(["git", "-C", r["path"], "rev-parse", "--verify", "-q", branch], capture_output=True).returncode == 0:
            return name, r["path"]
    sys.exit(f"Worktree and branch {branch} are gone locally: there is nothing to apply changes to.")


def rework(card):
    card = os.path.abspath(card)
    name = os.path.basename(card)
    state = pr.load(os.path.join(card, "state.json"))
    if not state:
        sys.exit(f"No local card {name}. /rework only continues a card Bureau ran here; to start the item, run /work <ref>.")
    if state.get("current") != "done":
        sys.exit(f"Card {name} is at step '{state.get('current')}', not finished. Continue it with /work {name}.")
    try:
        with open(os.path.join(card, "pr.md")) as f:
            opened = pr.OPENED in f.read()
    except FileNotFoundError:
        opened = False
    if not opened:
        sys.exit(f"No PR was opened for {name}. Run /work {name}; it opens the PR.")
    branch = "bureau/" + name
    repo, cwd = find_repo(card, branch)
    prs = gh_json(["pr", "list", "--head", branch, "--state", "all", "--json", "url,number,state"], cwd)
    if not prs:
        sys.exit(f"No PR found on branch {branch} (via gh).")
    p = prs[0]
    if p["state"] != "OPEN":
        sys.exit(f"PR is {p['state']}: {p['url']}. Nothing to rework.")
    view = gh_json(["pr", "view", str(p["number"]), "--json", "author,commits,reviews,comments"], cwd)
    gql = gh_json(["api", "graphql", "-f", f"query={THREADS}", "-F", "owner={owner}", "-F", "repo={repo}",
                   "-F", f"n={p['number']}"], cwd)["data"]["repository"]["pullRequest"]["reviewThreads"]
    threads = [t for t in gql["nodes"] if not t["isResolved"]]
    # shortcut: only the last commit's date separates new top-level comments from old ones, so one made
    # before an earlier push of the same round is missed; upgrade if that bites
    pushed = max((c["committedDate"] for c in view["commits"]), default="")
    me = (view.get("author") or {}).get("login")
    comments = [{"author": c["author"]["login"], "body": c["body"], "at": c.get("createdAt") or c.get("submittedAt")}
                for c in view["reviews"] + view["comments"]
                if c["body"].strip() and (c.get("createdAt") or c.get("submittedAt") or "") > pushed
                and c["author"]["login"] != me]
    if not threads and not comments:
        sys.exit(f"No unresolved threads or new comments: no review to check on {p['url']}.")
    return {"pr": p, "repo": repo, "threads": threads, "comments": comments,
            "truncated": gql["totalCount"] > len(gql["nodes"])}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(json.dumps(rework(sys.argv[1]), indent=2))
