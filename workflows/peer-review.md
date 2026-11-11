---
name: peer-review
use_when: An open PR someone else wrote (author is not the `gh` user; forks included) that you review: findings, then drafted review comments posted as one review. Never commits or pushes. For your own PR's review comments, use pr-review.
---
## review
persona: qa
gate: approve

Read-only. Fetch the PR: `gh pr view <n> --repo <owner>/<repo> --json title,body,url,author,headRefOid,files,reviews,comments`, the diff with `gh pr diff <n> --repo <owner>/<repo>`, and the inline threads with `gh api repos/<owner>/<repo>/pulls/<n>/comments` (take owner and repo from the PR URL; this step runs outside the repo). Read the surrounding code in the base repo where the diff alone does not show the effect.
Write review.md: the head commit (`headRefOid`), then findings ranked by severity, each with `file:line` (a line in the diff's new version), what is wrong, and a suggested fix. Leave out points an existing comment already raises; name them in one line instead. No worktree, no commits, no posting.
Stop here; the human approves the findings (and may drop or reword them) before any comment is drafted.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.

## draft
persona: staff-engineer
gate: approve

Turn the findings the human approved in review.md into one review. Write draft.json:
`{"repo": "<owner>/<repo>", "number": <n>, "commit_id": "<headRefOid>", "event": "COMMENT", "body": "...", "comments": [{"path": "a.py", "line": 12, "body": "..."}]}`.
Re-read `headRefOid`; if it changed since review.md, say so and draft against the new head. Each `line` is a line number in the new version of the file and must sit inside a hunk of `gh pr diff` at that commit (GitHub rejects the whole review otherwise). A finding with no diff line goes in `body`. The event is `COMMENT` unless the human asked for `REQUEST_CHANGES` or `APPROVE`.
Write draft.md for the human: the event on its first line, then each comment as `path:line` and its text, then the body.
`/approve` on this step runs `scripts/post_review.py`, which checks the head is unchanged and posts the review. No worktree, no push, no thread resolved.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
