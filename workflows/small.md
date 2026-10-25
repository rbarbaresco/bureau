---
name: small
use_when: A small, low-risk change in one repo whose approach is obvious from the card (docs, instruction files, config, small renames). Not for new behaviour, logic changes that need design, or defects; use task or bugfix for those.
---
## understand
persona: staff-engineer
gate: approve

Read card.md and the relevant files. Write understand.md in a few lines: what is asked, acceptance criteria as a checklist,
and the proposed change (for a docs change, the draft wording). This replaces a separate plan, so the human's approval here
is what allows any code to be written. Stop here.
End the artifact with `## Open questions` (or "none").

## build
persona: staff-engineer
gate: approve
writes_code: true

Create the worktree, load the repo rules, then make the change. Test first if there is any logic. For docs, show the rendered diff. Commit all work before finishing: the `pr` step cannot commit.
Write build.md: what changed, test output, deviations from understand.md and why.
Docs: if the change alters documented behaviour, update the README, docs and instruction files
(`AGENTS.md`/`CLAUDE.md`) in the same change; otherwise write `Docs: none needed, <reason>` in build.md. A docs-only change skips this; the change is the docs.
End the artifact with `## Open questions` (or "none").

## review
persona: qa
gate: none

As a read-only subagent, check the diff against the acceptance criteria in understand.md. Report findings ranked by severity (the session writes them to review.md).
Check the docs line in build.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding. For a docs-only change, skip this docs check only and still review the diff.

## pr
persona: staff-engineer
gate: approve

Read review.md first. If it has a finding above low, lead the gate summary with it so the human can answer "go back to build" instead of `/approve`; do not fix it yourself here.
Draft the PR title and body (summary, not the case). Show it to the human.
Write the draft to pr.md: first line the title, then the body, then the `git diff --stat` file list. `/approve` on this step runs `scripts/pr.py`, which pushes the branch, opens the draft PR and appends its link to pr.md.
If the repo needs the PR number in a follow-up commit, a `followup` step goes after this one (README, *A follow-up that needs the PR number*).
