---
name: build
use_when: New behaviour or a refactor against an approved plan (plan.md, or understand.md where there is no plan). Not for defects (use fix) or schema/data changes (use migration).
---
## build
persona: staff-engineer
gate: approve
writes_code: true

Load the repo rules, create the worktree, then implement test first. Commit all work before finishing: the `pr` step cannot commit.
Write build.md: what changed, test output, deviations from the approved plan and why.
If no `docs` step follows, also update stale docs here, or write `Docs: none needed, <reason>` in build.md.
End the artifact with `## Open questions` (or "none").
