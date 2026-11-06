---
name: understand
use_when: Always the first step: read the card and the code it points at. Gate `approve` when no plan step follows (the approval then allows code); `none` when a plan does. Not for PRs with review comments (use triage).
---
## understand
persona: staff-engineer
gate: none

Read card.md and the relevant code. Write understand.md: what is asked, acceptance criteria as a checklist, open questions. With no plan step after this one, also write the proposed change (for docs, the draft wording) and set `gate: approve`: that approval is what allows code. Ask the human anything blocking before moving on.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
