---
name: triage
use_when: An existing open PR (same repo, not a fork) has review comments to sort before any code. Not for new work from a ticket.
---
## triage
persona: staff-engineer
gate: approve

Read-only. Fetch the PR: `gh pr view <n> --json headRefName,isCrossRepository,reviews,comments,url` and the inline threads with `gh api repos/<owner>/<repo>/pulls/<n>/comments` (owner and repo from the PR URL). If `isCrossRepository` is true, stop: Bureau cannot push to a fork.
Write triage.md: the head branch, then one row per comment (id, author, `file:line`, quote) classified apply, disagree, needs a question or already resolved, each with a reason. For a reply, record the thread's root comment id.
Stop here; the human approves the list before any code changes.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
