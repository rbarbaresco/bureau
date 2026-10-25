---
name: task
use_when: A well-defined story or task with clear acceptance criteria in one repo (new behaviour, small refactor). Not for open-ended discovery or defects with an unknown cause.
---
## understand
persona: staff-engineer
gate: none

Read card.md and the relevant code. Write understand.md: what is asked, acceptance criteria as a checklist,
open questions. If something blocks, list it under `## Open questions`, ask the human and stop before `desk.py finish`.

## plan
persona: architect
gate: approve

Write plan.md: approach, files and callers affected, test strategy, risks, and what is deliberately out of scope.
Stop here; the human approves before any code.
End the artifact with `## Open questions` (or "none").

## build
persona: staff-engineer
gate: approve
writes_code: true

Create the worktree, load the repo rules, then implement test first. Write build.md: what changed,
test output, deviations from plan.md and why.
Docs: if the change alters documented behaviour, update the README, docs and instruction files
(`AGENTS.md`/`CLAUDE.md`) in the same change; otherwise write `Docs: none needed, <reason>` in build.md. Commit all work before finishing: the `pr` step cannot commit.
End the artifact with `## Open questions` (or "none").

## review
persona: qa
gate: none

As a read-only subagent, check the diff against the acceptance criteria and plan.md. Report findings
ranked by severity (the session writes them to review.md).
Check the docs line in build.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.

## pr
persona: staff-engineer
gate: approve

Read review.md first. If it has a finding above low, lead the gate summary with it so the human can answer "go back to build" instead of `/approve`; do not fix it yourself here.
Draft the PR title and body (summary, not the case). Show it to the human.
Write the draft to pr.md: first line the title, then the body, then the `git diff --stat` file list. `/approve` on this step runs `scripts/pr.py`, which pushes the branch, opens the draft PR and appends its link to pr.md.
If the repo needs the PR number in a follow-up commit, a `followup` step goes after this one (README, *A follow-up that needs the PR number*).
