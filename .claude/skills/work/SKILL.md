---
name: work
description: Start or resume a work item (ticket, issue, Sentry link, pasted story, or an existing card ID) in Bureau. Reads the card, shows an overview, proposes a workflow, then runs it step by step with human gates. Use for "let's work on this task" and /work.
---

# /work <ref> [workflow]

`<ref>` is a card ID already in `desk/`, a GitHub issue/PR URL or `owner/repo#n`, a Jira key or URL, a Sentry link, or pasted text.
Paths below are relative to the Bureau root. Never run steps the human did not confirm.

## 1. Resume or intake

- Run `python3 scripts/desk.py list`. If `<ref>` matches a run: read its `state.json`, `card.md`, latest artifact; go to **Run loop** (resume rules there).
- A `desk/<card-id>/` folder with `card.md` but no `state.json` means intake is done and no workflow was confirmed yet: go to step 3.
- Otherwise fetch the card and write `desk/<card-id>/card.md` (title, source link, description, acceptance criteria if any, comments that matter):
  - GitHub: `gh issue view <ref> --json title,body,labels,url,comments` (use `gh pr view` for a PR). Card id: `<repo>-<number>`.
  - Jira: `acli jira workitem view <KEY> --json`. Card id: the key.
  - Sentry (no CLI installed): use a Sentry tool if one is connected; otherwise ask the user to paste the issue.
  - Pasted text: save as given. Use the id the user gave, else make a short kebab-case slug from the title (the user can rename it); do not ask.
  - Fetch failed or tool missing: say so and ask for pasted text. Do not guess content.

## 2. Overview (for the human to read)

At most ten lines: what is asked; acceptance criteria and what is unclear; the likely repo(s) from `repos.yaml`;
size and risk (auth, data, infra, migrations). Flag anything blocking.

## 3. Workflow

- `python3 scripts/workflow.py list` prints each workflow's "use when". Pick the best match and give the reason in one line,
  or say none fits and propose a custom step list (same format as `workflows/*.md`: `## step-id`, `persona:`, `gate:`, `writes_code:`, instructions;
  write it to `desk/<card-id>/workflow.md`). If the user named a workflow, use it.
- Show the steps with their persona and gate (`python3 scripts/workflow.py show <name|file>`).
  The human accepts or edits (add, skip, reorder, change a gate or persona). **Wait for confirmation.**
- On confirmation: `python3 scripts/workflow.py start <name|desk/<card-id>/workflow.md> desk/<card-id>`.

## 4. Run loop

For the current step in `state.json`:

1. Read the step's section in `desk/<card-id>/workflow.md` and its persona in `personas/<persona>.md` (or `desk/<card-id>/personas/`).
2. Do the work as that persona. `read-only` personas run as a read-only subagent (their prompt has the persona, `card.md`,
   the prior artifacts, and the repo rules output). `writer` personas work in this session.
3. A step that writes code: create the worktree with `python3 scripts/worktree.py desk/<card-id> <repo>` (repo is a name in
   `repos.yaml`), then load the rules with `python3 hooks/rules.py desk/<card-id>/worktrees/<repo>` and follow them. Edits are
   denied by a hook until both that and the earlier approvals are in place; if denied, do what the message says, never route around it.
4. Write the step's artifact to `desk/<card-id>/<step-id>.md` (short; evidence and logs by path).
5. `python3 scripts/desk.py finish desk/<card-id>`.
   - Gate `none`: the step advanced; continue with the next.
   - Gated: `awaiting` is set. Summarize the artifact in a few lines with its path, tell the user to **`/approve`**, or give feedback.
     **Stop.** Do not write `approvals.json` and do not call `advance` until the user has approved.
6. Human outcomes at a gate: `/approve` → the approve skill advances. Feedback → `python3 scripts/desk.py revise desk/<card-id> '<feedback>'`
   and redo the step. "Go back to X" → `desk.py reject desk/<card-id> <step> '<reason>'`.
   Add or skip steps on request: `desk.py add desk/<card-id> <after-step> '<step-json>'`, `desk.py skip desk/<card-id> <step>`.
7. When `current` is `done`: summarize what was delivered and where (worktree paths, branches, PR link).

Resume: if `awaiting` is set and `approvals.json` has it, run `desk.py advance`; if not approved, show the artifact and remind the user to `/approve`.

## Rules

- Tracker writes (comments, status changes, creating issues) and opening a PR need the human's explicit approval first; PRs are drafts (`gh pr create --draft`). Merging is the human's.
- Status updates in tracker comments are summaries, not logs.
- End each reply with where work landed: Bureau path, card folder, worktree and branch, committed or not.
