---
name: review
use_when: After any code step, before pr: a read-only check of the diff. Not a substitute for the human's gate.
---
## review
persona: qa
gate: none

As a read-only subagent, check the diff against the card and the approved plan (plan.md, understand.md or triage.md):
missed criteria, what else the change could break, weak or missing tests, anything unneeded.
If a docs step ran, check docs.md: does the diff leave any README, doc or instruction file stale? Rank a miss as a finding.
Write review.md with findings ranked by severity.
