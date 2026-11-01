---
name: pr
use_when: Opens the draft PR after review. Every workflow that writes code ends with it (or with reply on an existing PR).
---
## pr
persona: staff-engineer
gate: approve

Draft the PR title and body (summary, not the case; evidence goes in a comment). Show it to the human.
Write the draft to pr.md: first line the title, then the body, then the `git diff --stat` file list. `/approve` on this step runs `scripts/pr.py`, which pushes the branch, opens the draft PR and appends its link to pr.md.
If the repo needs the PR number in a follow-up commit, a `followup` step goes after this one.
