---
name: bugfix
use_when: A defect with a symptom you can reproduce or locate in one repo (error report, failing behaviour, Sentry issue). Not for new behaviour or multi-repo changes.
---
## plan
persona: staff-engineer
gate: approve

Find the repo and the failing code path. Reproduce the symptom, or say why you cannot.
Write plan.md: reproduction, root cause, the smallest fix that closes it, who else calls the code being changed (blast radius), anything missing from the card, and the test that fails before and passes after. Stop here; the human approves before any code.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.

## fix
persona: staff-engineer
gate: approve
writes_code: true

Load the repo rules, create the worktree, write the failing test first, then the fix. Commit all work before finishing: the `pr` step cannot commit.
Write fix.md: what changed, test output, anything deliberately left alone.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.

## docs
persona: journalist
gate: none
writes_code: true

Load the repo rules. Read the code step's artifact and the branch diff (`git diff origin/<base>...HEAD`).
Find every README, doc and instruction file (`AGENTS.md`/`CLAUDE.md`) the change makes wrong or incomplete, and update it in the same branch, in the repo's own style. Commit before finishing: the `pr` step cannot commit.
If nothing is stale, edit nothing and write `Docs: none needed, <reason>`.
Write docs.md: each file updated and why, or the none-needed line. No gate: the human sees these commits at the `pr` gate.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.

## review
persona: qa
gate: none

As a read-only subagent, review the diff against plan.md and the card: does the test prove the fix, what else could the change break, anything unneeded. Write review.md with findings ranked by severity.
Check docs.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.

## pr
persona: staff-engineer
gate: approve

Draft the PR title and body (summary, not the case; evidence goes in a comment). Show it to the human.
Write the draft to pr.md: first line the title, then the body, then the `git diff --stat` file list. `/approve` on this step runs `scripts/pr.py`, which pushes the branch, opens the draft PR and appends its link to pr.md.
If the repo needs the PR number in a follow-up commit, a `followup` step goes after this one (`steps/followup.md`).
