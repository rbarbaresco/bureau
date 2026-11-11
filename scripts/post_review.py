#!/usr/bin/env python3
"""Post the review for a peer-review card whose `draft` step the human approved.

Usage: post_review.py <card-dir>
Posts desk/<card>/draft.json as one GitHub review:
{"repo": "o/r", "number": 7, "commit_id": "<head sha>", "event": "COMMENT|REQUEST_CHANGES|APPROVE",
 "body": "...", "comments": [{"path": "a.py", "line": 12, "body": "..."}]}
Refuses if the PR's head moved since the draft. One request, so GitHub takes the whole review or none of it.
Records "posted": <url> in draft.json, so a re-run posts nothing. Never pushes, never resolves threads.
"""
import json
import os
import sys

from pr import load, run

EVENTS = ("COMMENT", "REQUEST_CHANGES", "APPROVE")


def valid(d):
    def text(v):
        return isinstance(v, str) and v.strip() != ""
    if not isinstance(d, dict):
        return False
    comments = d.get("comments", [])
    return (text(d.get("repo")) and isinstance(d.get("number"), int) and text(d.get("commit_id"))
            and d.get("event") in EVENTS and isinstance(d.get("body", ""), str) and isinstance(comments, list)
            and (text(d.get("body")) or comments)
            and all(isinstance(c, dict) and text(c.get("path")) and isinstance(c.get("line"), int)
                    and text(c.get("body")) for c in comments))


def post_review(card):
    card = os.path.abspath(card)
    state = load(os.path.join(card, "state.json"))
    ids = [s["id"] for s in state.get("steps", [])]
    # a done card is allowed too, like pr.py: it repairs a post that failed after the card moved on
    if not (state.get("awaiting") == "draft" or (state.get("current") == "done" and "draft" in ids)):
        sys.exit(f"{card}: step 'draft' is not awaiting (awaiting={state.get('awaiting')}); nothing to post.")
    if not load(os.path.join(card, "approvals.json")).get("draft"):
        sys.exit("step 'draft' is not approved; the human must run /approve.")
    path = os.path.join(card, "draft.json")
    try:
        with open(path) as f:
            draft = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        sys.exit(f"{path} missing or invalid ({e}): write the draft first.")
    if not valid(draft):
        sys.exit(f"{path} needs repo, an int number, commit_id, an event in {EVENTS}, a body or comments, "
                 "and each comment a path, an int line and a non-empty body.")
    if draft.get("posted"):
        return f"already posted: {draft['posted']}"
    repo, number = draft["repo"], draft["number"]
    head = run(["gh", "pr", "view", str(number), "--repo", repo, "--json", "headRefOid", "--jq", ".headRefOid"])
    if head != draft["commit_id"]:
        sys.exit(f"PR head moved to {head} since the draft ({draft['commit_id']}): redo the draft step against it.")
    payload = {k: draft[k] for k in ("commit_id", "event", "body", "comments") if k in draft}
    url = run(["gh", "api", f"repos/{repo}/pulls/{number}/reviews", "--method", "POST", "--input", "-",
               "--jq", ".html_url"], input=json.dumps(payload))
    draft["posted"] = url
    with open(path, "w") as f:
        json.dump(draft, f, indent=2)
    return f"posted the review on {repo}#{number}: {url}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(post_review(sys.argv[1]))
