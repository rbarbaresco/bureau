---
name: reproduce
use_when: A reported defect nobody has shown happening yet, before planning a fix. Not when the card already has a failing test or a stack trace that pins the line.
---
## reproduce
persona: staff-engineer
gate: approve

Reproduce the symptom without changing code: the exact command, input or steps, and the output that shows it
This step does not write code, so in the worktree the gate allows only read-only commands and the repo's `test:`
command (`repos.yaml`): reproduce with a test, or run the app or CLI from a scratch copy outside the worktree. If you cannot, say what you tried and what is missing.
Write reproduce.md: steps, observed vs. expected, the code path it points at. The human approves before a fix is planned.
End the artifact with `## Open questions` (or "none").
