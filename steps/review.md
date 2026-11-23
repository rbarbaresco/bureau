---
name: review
use_when: After any code step, before pr: a read-only check of the diff. Gated: the human reads the findings before the PR.
---
## review
persona: qa
gate: approve

As a read-only subagent, check the diff against the card and the approved plan (plan.md, understand.md or triage.md, plus reproduce.md or research.md if they ran):
missed criteria, what else the change could break, weak or missing tests, anything unneeded.
If a docs step ran, check docs.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.
Write review.md with findings ranked by severity.
Findings to fix: the human sends the card back to the code step ("Go back"); a clean review is approved as is.
