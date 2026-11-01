---
name: followup
use_when: Right after pr, only when the repo wants an entry named after the PR number (a changelog fragment). Not otherwise.
---
## followup
persona: staff-engineer
gate: approve
writes_code: true

Read the PR link from pr.md. Make the change that needs the PR number, commit and push (no force): `pr.py` pushes only once, so this step pushes itself. Write followup.md: the commit and what it adds.
End the artifact with `## Open questions` (or "none").
