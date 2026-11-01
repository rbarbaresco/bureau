---
name: plan
use_when: The approach, blast radius or test strategy is not obvious from the card. Not for changes whose approach is obvious (understand covers them) or defects (fold the plan into reproduce or the bugfix plan).
---
## plan
persona: architect
gate: approve

Write plan.md: approach, files and callers affected, test strategy, risks, and what is deliberately out of scope.
Stop here; the human approves before any code. Set `loop: true` only if every version of the plan is something
the human signs off in turn; plain feedback already redoes the step.
End the artifact with `## Open questions` (or "none").
