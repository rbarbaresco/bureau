---
name: review-comments
use_when: Ends a peer-review: turn approved review findings into one GitHub review, posted after approval. Not for replying on your own PR (use reply).
---
## review-comments
persona: staff-engineer
gate: approve

Turn the approved findings into review-comments.json: `{"repo": "<owner>/<repo>", "number": <n>, "commit_id": "<headRefOid>", "event": "COMMENT", "body": "...", "comments": [{"path": "a.py", "line": 12, "body": "..."}]}`. Each `line` must sit inside a hunk of `gh pr diff` at that commit; `body` is required: a summary plus any finding with no diff line. Write review-comments.md for the human: the event first, then each comment as `path:line` and its text.
`/approve` on this step runs `scripts/post_review.py`, which checks the head is unchanged and posts one review. No worktree, no push, no thread resolved.
