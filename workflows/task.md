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
Docs: if the change alters documented behaviour, update the README, docs and instruction files
(`AGENTS.md`/`CLAUDE.md`) in the same change; otherwise write `Docs: none needed, <reason>` in build.md.
End the artifact with `## Open questions` (or "none").

## review
persona: qa
gate: none

As a read-only subagent, check the diff against the acceptance criteria and plan.md. Write review.md
with findings ranked by severity.
Check the docs line in build.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.

## pr
persona: staff-engineer
gate: approve

Draft the PR title and body (summary, not the case). Show it to the human. Open a draft PR only after approval.
