---
name: reply
use_when: Ends a pr-review: post replies to the review comments on an existing PR. Not for opening a new PR (use pr).
---
## reply
persona: staff-engineer
gate: approve

Draft the replies and show them to the human. Write reply.md (which comment, what we say, the commit) and reply.json:
`[{"in_reply_to": <review comment id or null>, "body": "..."}]`. A null id posts a PR comment. Do not resolve threads.
`/approve` on this step runs `scripts/reply.py`, which pushes the branch (no force) and posts the replies. With no worktree (no code changed) it skips the push and posts to the PR linked in card.md.
