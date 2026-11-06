---
name: human-review
use_when: The human wants to steer the change over several rounds (wording, UI, prompts) after the code step. Each round needs its own approval and only the human ends it. Not for one round of feedback (feedback already redoes a step).
---
## human-review
persona: staff-engineer
gate: approve
writes_code: true
loop: true

Each round: apply the human's notes, commit, and write human-review.md: the notes, what changed, and the diff since the last round. Notes for the next round come after the `/approve` line in the same message; if a new round starts with none, ask for them and wait. Feedback without `/approve` redoes the current round instead (`revise`), without approving it. `/approve` accepts the round and starts the next; `/approve done` ends the step.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
