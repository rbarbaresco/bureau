---
name: task
use_when: A well-defined story or task with clear acceptance criteria in one repo (new behaviour, small refactor). Not for open-ended discovery or defects with an unknown cause.
---
## understand
persona: staff-engineer
gate: none

Read card.md and the relevant code. Write understand.md: what is asked, acceptance criteria as a checklist,
open questions. Ask the human anything blocking before moving on.

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

Load the repo rules, create the worktree, then implement test first. Write build.md: what changed,
test output, deviations from plan.md and why.
Commit all work before finishing: the `pr` step cannot commit.
End the artifact with `## Open questions` (or "none").

## docs
persona: journalist
gate: none
writes_code: true

Load the repo rules. Read the code step's artifact and the branch diff (`git diff origin/<base>...HEAD`).
Find every README, doc and instruction file (`AGENTS.md`/`CLAUDE.md`) the change makes wrong or incomplete, and update
it in the same branch, in the repo's own style. Commit before finishing: the `pr` step cannot commit.
If nothing is stale, edit nothing and write `Docs: none needed, <reason>`.
Write docs.md: each file updated and why, or the none-needed line. No gate: the human sees these commits at the `pr` gate.
End the artifact with `## Open questions` (or "none").

## review
persona: qa
gate: none

As a read-only subagent, check the diff against the acceptance criteria and plan.md. Write review.md
with findings ranked by severity.
Check docs.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.

## pr
persona: staff-engineer
gate: approve

Draft the PR title and body (summary, not the case). Show it to the human.
Write the draft to pr.md: first line the title, then the body, then the `git diff --stat` file list. `/approve` on this step runs `scripts/pr.py`, which pushes the branch, opens the draft PR and appends its link to pr.md.
If the repo needs the PR number in a follow-up commit, a `followup` step goes after this one (`steps/followup.md`).
