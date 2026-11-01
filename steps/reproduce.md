---
name: reproduce
use_when: A reported defect nobody has shown happening yet, before planning a fix. Not when the card already has a failing test or a stack trace that pins the line.
---
## reproduce
persona: staff-engineer
gate: approve

Reproduce the symptom without changing code: the exact command, input or steps, and the output that shows it
(tests may run; anything else goes in the scratchpad). If you cannot, say what you tried and what is missing.
Write reproduce.md: steps, observed vs. expected, the code path it points at. The human approves before a fix is planned.
End the artifact with `## Open questions` (or "none").
