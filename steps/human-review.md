---
name: human-review
use_when: The human wants to steer the change over several rounds (wording, UI, prompts) after the code step. Each round needs its own approval and only the human ends it. Not for one round of feedback (feedback already redoes a step).
---
## human-review
persona: staff-engineer
gate: approve
writes_code: true
loop: true

Each round: apply the human's notes, commit, and write human-review.md: the notes, what changed, and the diff since the
last round. Notes come in the human's message (with `/approve`, after the `/approve` line, or as plain feedback); if a new
round starts with none, ask for them and wait. `/approve` accepts the round and starts the next; `/approve done` ends the step.
End the artifact with `## Open questions` (or "none").
