---
name: pr-review
use_when: An existing open PR in a registered repo (same repo, not a fork) has review comments to triage and apply. Not for new work from a ticket (use task or bugfix) or PRs from forks.
---
## triage
persona: staff-engineer
gate: approve

Read-only. Fetch the PR: `gh pr view <n> --json headRefName,isCrossRepository,reviews,comments,url` and the inline
threads with `gh api repos/<owner>/<repo>/pulls/<n>/comments` (take owner and repo from the PR URL; this step runs outside the repo, so `{owner}` placeholders do not resolve). If `isCrossRepository` is true, stop: Bureau cannot push to a fork.
Write triage.md: the head branch, then one row per comment (id, author, `file:line`, quote) classified apply, disagree,
needs a question or already resolved, each with a reason and the code it touches. For a reply, record the thread's root comment id (GitHub only accepts replies to a thread's first comment).
Stop here; the human approves the list (and may reclassify rows) before any code changes.
End the artifact with `## Open questions` (or "none").

## fix
persona: staff-engineer
gate: approve
writes_code: true

Create the worktree on the PR's branch: `python3 scripts/worktree.py desk/<card-id> <repo> --branch <headRefName>`, then load
the repo rules. Apply only the items the human approved in triage.md, test first where behaviour changes, one commit per logical fix.
Write fix.md: a table mapping each commit to the comment id it answers, test output, anything approved but not applied and why.
Docs: if a fix alters documented behaviour, update the README, docs and instruction files in the same change; otherwise write
`Docs: none needed, <reason>` in fix.md. Commit all work before finishing; do not push.
End the artifact with `## Open questions` (or "none").

## review
persona: qa
gate: none

As a read-only subagent, check the diff against the approved list in triage.md and fix.md: missed items, over-applied
changes, a commit that answers the wrong comment. Write review.md with findings ranked by severity.

## reply
persona: staff-engineer
gate: approve

Draft the replies and show them to the human. Write reply.md (readable: which comment, what we say, the commit) and reply.json:
`[{"in_reply_to": <review comment id or null>, "body": "..."}]`. A null id posts a PR comment. Replies to "disagree" and
"needs a question" items say why, briefly; do not resolve threads (the reviewer does). `/approve` on this step runs
`scripts/reply.py`, which pushes the branch (no force) and posts the replies.
