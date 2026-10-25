---
name: bugfix
use_when: A defect with a symptom you can reproduce or locate in one repo (error report, failing behaviour, Sentry issue). Not for new behaviour or multi-repo changes.
---
## plan
persona: staff-engineer
gate: approve

Find the repo and the failing code path. Reproduce the symptom, or say why you cannot.
Write plan.md: reproduction, root cause, the smallest fix that closes it, who else calls the code being changed
(blast radius), anything missing from the card, and the test that fails before and passes after. Stop here; the human approves before any code.
End the artifact with `## Open questions` (or "none").

## fix
persona: staff-engineer
gate: approve
writes_code: true

Create the worktree, load the repo rules, write the failing test first, then the fix. Commit all work before finishing: the `pr` step cannot commit.
Write fix.md: what changed, test output, anything deliberately left alone.
Docs: if the change alters documented behaviour, update the README, docs and instruction files
(`AGENTS.md`/`CLAUDE.md`) in the same change; otherwise write `Docs: none needed, <reason>` in fix.md.
End the artifact with `## Open questions` (or "none").

## review
persona: qa
gate: none

As a read-only subagent, review the diff against plan.md and the card: does the test prove the fix,
what else could the change break, anything unneeded. Report findings ranked by severity (the session writes them to review.md).
Check the docs line in fix.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.

## pr
persona: staff-engineer
gate: approve

Read review.md first. If it has a finding above low, lead the gate summary with it so the human can answer "go back to fix" instead of `/approve`; do not fix it yourself here.
Draft the PR title and body (summary, not the case; evidence stays in fix.md, posted as a PR comment only if the human asks). Show it to the human.
Write the draft to pr.md: first line the title, then the body, then the `git diff --stat` file list. `/approve` on this step runs `scripts/pr.py`, which pushes the branch, opens the draft PR and appends its link to pr.md.
