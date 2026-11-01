---
name: docs
use_when: A code step changed behaviour that README, docs or instruction files describe. Put it after build/fix, before review. Not for docs-only cards, where the code step's change is the docs.
---
## docs
persona: journalist
gate: none
writes_code: true

Load the repo rules. Read the code step's artifact and the branch diff (`git diff origin/<base>...HEAD`).
Find every README, doc and instruction file (`AGENTS.md`/`CLAUDE.md`) the change makes wrong or incomplete, and update
it in the same branch, in the repo's own style. Commit before finishing: the `pr` step cannot commit.
If nothing is stale, edit nothing and write `Docs: none needed, <reason>`.
Write docs.md: each file updated and why, or the none-needed line. No gate: the human sees this diff at the `pr` gate.
End the artifact with `## Open questions` (or "none").
