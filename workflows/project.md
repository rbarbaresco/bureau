---
name: project
use_when: A source that is already split into several tasks (sub-issues of a GitHub issue, a Jira epic, a bulleted or markdown task list) to run as one child card per task. Not for a single task (use task or bugfix) or for work nobody has split yet.
---
## intake
persona: staff-engineer
gate: approve

Read the source and the code the tasks touch. Write tasks.md in this folder, one table and nothing else the parser reads:

| id | title | repo | blocked by | edge |
|----|-------|------|------------|------|
| 1 | Short title | repo-name-from-repos.yaml | - | - |
| 2 | Short title | repo-name-from-repos.yaml | 1 | stated |

`blocked by` lists ids (comma separated) or `-`. `edge` is `stated` (the source says so) or `inferred` (you worked it out; say why under the table). Two tasks that edit the same file get an inferred edge. GitHub sub-issues: `gh api repos/<owner>/<repo>/issues/<n>/sub_issues`.
Stop here: the human corrects the table, then approves. `/approve` runs nothing; the next step creates the children.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.

## run
persona: staff-engineer
gate: approve
loop: true

Each round: on the first, run `python3 scripts/project.py spawn <this folder>` (creates one `task` card per row; running it again changes nothing). Then `python3 scripts/project.py status <this folder>`: every `ready` child that has not started gets a background subagent that runs its current step as `/work` would (the child's `workflow.md`, persona, repo rules, worktree). One subagent per child step; it ends by running `desk.py finish` on the child, which leaves a gated step awaiting. A child never approves itself: the human types `/approve <child-id>`, and the next round starts the next step.
Write run.md: the status table, what was started this round, and what each awaiting child needs from the human (its artifact path and open question labels). `/approve` accepts the round; `/approve done` ends the run once every child is merged.
Each child opens its own draft PR through its own `pr` step. Merge state is read with `gh pr view` from the child's `pr.md`, never from the tracker's blocked-by.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
