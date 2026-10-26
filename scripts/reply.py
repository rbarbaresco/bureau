#!/usr/bin/env python3
"""Push the PR branch and post the replies for a card whose `reply` step the human approved.

Usage: reply.py <card-dir>
Pushes the worktree's branch (never force), then posts each entry of desk/<card>/reply.json:
[{"in_reply_to": <review comment id or null>, "body": "..."}]. An id replies in that review thread;
null adds a PR comment. Posted entries are marked in reply.json, so a re-run skips them.
Never resolves threads (the reviewer does). Exits non-zero on any failure; safe to run again.
"""
import json
import os
import sys

from pr import load, run


def post_replies(card):
    card = os.path.abspath(card)
    state = load(os.path.join(card, "state.json"))
    ids = [s["id"] for s in state.get("steps", [])]
    # a done card is allowed too, like pr.py: it repairs a push or post that failed after the card moved on
    if not (state.get("awaiting") == "reply" or (state.get("current") == "done" and "reply" in ids)):
        sys.exit(f"{card}: step 'reply' is not awaiting (awaiting={state.get('awaiting')}); nothing to post.")
    if not load(os.path.join(card, "approvals.json")).get("reply"):
        sys.exit("step 'reply' is not approved; the human must run /approve.")
    root = os.path.join(card, "worktrees")
    trees = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))) if os.path.isdir(root) else []
    if len(trees) != 1:  # shortcut: one worktree per card
        sys.exit(f"expected exactly one worktree under {card}/worktrees, found {len(trees)}.")
    wt = os.path.join(root, trees[0])
    path = os.path.join(card, "reply.json")
    try:
        with open(path) as f:
            replies = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        sys.exit(f"{path} missing or invalid ({e}): write the replies first.")
    if run(["git", "-C", wt, "status", "--porcelain"]):
        sys.exit(f"uncommitted changes in {wt}: commit them first.")
    run(["git", "-C", wt, "push"])
    number = run(["gh", "pr", "view", "--json", "number", "--jq", ".number"], cwd=wt)
    repo = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=wt)
    for r in replies:
        if r.get("posted"):
            continue
        if r.get("in_reply_to"):
            run(["gh", "api", f"repos/{repo}/pulls/{number}/comments/{r['in_reply_to']}/replies",
                 "-f", f"body={r['body']}"], cwd=wt)
        else:
            run(["gh", "pr", "comment", number, "--body-file", "-"], cwd=wt, input=r["body"])
        r["posted"] = True
        with open(path, "w") as f:  # after each post, so a failure half-way does not repeat the earlier ones
            json.dump(replies, f, indent=2)
    return f"pushed; {sum(1 for r in replies if r.get('posted'))} replies posted on PR #{number}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(post_replies(sys.argv[1]))
