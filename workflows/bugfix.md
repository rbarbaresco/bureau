---
name: bugfix
use_when: A defect with a symptom you can reproduce or locate in one repo (error report, failing behaviour, Sentry issue). Not for new behaviour or multi-repo changes.
---
## triage
persona: staff-engineer
gate: none

Read card.md. Find the repo and the failing code path. Reproduce the symptom, or say why you cannot.
Write triage.md: symptom, reproduction, suspected cause, blast radius, anything missing from the card.

## plan
persona: staff-engineer
gate: approve

Write plan.md: root cause, the smallest fix that closes it, who else calls the code being changed,
and the test that fails before and passes after. Stop here; the human approves before any code.
End the artifact with `## Open questions` (or "none").

## fix
persona: staff-engineer
gate: approve
writes_code: true

Load the repo rules, create the worktree, write the failing test first, then the fix.
Write fix.md: what changed, test output, anything deliberately left alone.
Docs: if the change alters documented behaviour, update the README, docs and instruction files
(`AGENTS.md`/`CLAUDE.md`) in the same change; otherwise write `Docs: none needed, <reason>` in fix.md.
End the artifact with `## Open questions` (or "none").

## review
persona: qa
gate: none

As a read-only subagent, review the diff against plan.md and the card: does the test prove the fix,
what else could the change break, anything unneeded. Write review.md with findings ranked by severity.
Check the docs line in fix.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.

## pr
persona: staff-engineer
gate: approve

Draft the PR title and body (summary, not the case; evidence goes in a comment). Show it to the human.
Open a draft PR only after approval.
