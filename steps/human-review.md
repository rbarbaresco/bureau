---
name: human-review
use_when: The human wants to steer the change over several rounds (wording, UI, prompts) after the code step. Each round needs its own approval and only the human ends it. Not for one round of feedback (feedback already redoes a step).
---
## human-review
persona: staff-engineer
gate: approve
writes_code: true
loop: true

Each round: apply the human's latest notes, commit, and write human-review.md: what changed this round, and the
diff since the last round. `/approve` accepts the round and starts the next; `/approve done` ends the step.
End the artifact with `## Open questions` (or "none").
