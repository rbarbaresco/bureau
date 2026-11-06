---
name: migration
use_when: The change alters a schema or existing data. Replaces build for that part, or runs before it. Not for code-only changes.
---
## migration
persona: staff-engineer
gate: approve
writes_code: true

Load the repo rules, create the worktree. Write the migration with its rollback (or say why there is none), in the repo's migration tool. Test both directions where the repo can. Commit all work before finishing.
Write migration.md: forward and rollback, data backfill, lock or table-size risk, deploy order against the code that uses it.
If no `docs` step follows, also update stale docs here, or write `Docs: none needed, <reason>` in migration.md.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
