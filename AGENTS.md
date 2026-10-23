# Bureau

A desk for running work items (tickets, issues, stories) through named, gated workflows.
Start with `/work`. State lives in `desk/<card-id>/`; reusable parts live in `workflows/` and `personas/`.

## Rules for every step

- **Read the target repo's rules before touching its code.** Run
  `python3 hooks/rules.py desk/<card-id>/worktrees/<repo>` and follow what it prints (repo
  instruction files, their parent folders' files, and these base rules). The gate hook denies
  code edits until you have; it also denies them after any of those files change.
- **Never edit the Bureau checkout itself.** A session that will change code starts with `/work` and works
  only in that card's worktree (`desk/<card-id>/worktrees/<repo>`). Two sessions in the root share one working tree.
  The gate hook does not enforce this outside worktrees; it is on you.
- **Never approve your own gate.** Only the human's `/approve` records approval. Do not write
  `approvals.json`. After a gated step finishes, set `awaiting` in `state.json` to that step's id and stop.
- **One writer per unit of work.** Read-only roles (review, QA, triage) run as subagents; give
  them the rule output in their prompt.
- **State files:** `state.json` (progress, you may update `current` and `awaiting`),
  `approvals.json` (human only), `ack.json` (written by `rules.py`), `card.md`, and one artifact per step.
- **Writes to a tracker** (comments, creating issues, status changes) need the human's
  explicit approval first. `/approve` on the `pr` step is the approval to open the PR, as a draft. Merging is the human's.
- Say where the work landed at the end of each reply: path, branch, commit state, files.
