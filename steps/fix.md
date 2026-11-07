---
name: fix
use_when: A defect whose root cause is known (from a plan or reproduce step). Not for new behaviour (use build).
---
## fix
persona: staff-engineer
gate: approve
writes_code: true

Load the repo rules, create the worktree, write the failing test first, then the fix. Commit all work before finishing: the `pr` step cannot commit.
Write fix.md: what changed, test output, anything deliberately left alone.
If no `docs` step follows, also update stale docs here, or write `Docs: none needed, <reason>` in fix.md.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
