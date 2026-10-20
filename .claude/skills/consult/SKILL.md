---
name: consult
description: Ask a Bureau persona (architect, staff-engineer, qa, or any file in personas/) a question about the current card, answered by a read-only subagent and saved to the card folder. Use for "ask the architect whether…", "what would QA say about this plan".
---

# Consult a persona

1. Pick the card: the one in the conversation, else the only one in `desk/` with a `state.json` that is not `done`; if unclear, ask.
2. Read `personas/<name>.md`. If the user wants a role that does not exist, write a short persona from their description to `desk/<card>/personas/<name>.md` and offer to promote it to `personas/`.
3. Spawn a read-only subagent (Agent tool, general-purpose or Explore). Its prompt contains, in this order:
   the persona file; the repo rules if a worktree exists
   (`python3 hooks/rules.py desk/<card>/worktrees/<repo>`, paste the output); `card.md`; the artifacts relevant to the
   question (plan, design, diff); then the question. Tell it not to edit files.
4. Save the answer to `desk/<card>/consult-<persona>-<n>.md` (next free `n`) and give the user the short version with the path.
5. Do not change `state.json`. A consultation is advice, not a gate.
