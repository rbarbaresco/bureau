---
name: work
description: Start or resume a work item (ticket, issue, Sentry link, pasted story, or an existing card ID) in Bureau. Reads the card, shows an overview, proposes a workflow, then runs it step by step with human gates. Use for "let's work on this task" and /work.
---

# /work <ref> [workflow]

`<ref>` is a card ID already in `desk/`, a GitHub issue/PR URL or `owner/repo#n`, a Jira key or URL, a Sentry link, or pasted text.
Paths below are relative to the Bureau root. Never run steps the human did not confirm.

## 1. Resume or intake

- A hook claims the card for this session when you type `/work <id>`. If it printed "Took over …" above, tell the user that line (past sessions); if it blocked, the card is held by a live session: stop.
- Run `python3 scripts/desk.py list`. If `<ref>` matches a run: read its `state.json`, `card.md`, latest artifact; go to **Run loop** (resume rules there).
- A `desk/<card-id>/` folder with `card.md` but no `state.json` means intake is done and no workflow was confirmed yet: go to step 3.
- Otherwise fetch the card and write `desk/<card-id>/card.md` with the Write tool (a hook claims the card on that write) (title, source link, description, acceptance criteria if any, comments that matter):
  - GitHub: `gh issue view <ref> --json title,body,labels,url,comments` (use `gh pr view` for a PR). Card id: `<repo>-<number>`.
  - Jira: `acli jira workitem view <KEY> --json`. Card id: the key.
  - Sentry (no CLI installed): use a Sentry tool if one is connected; otherwise ask the user to paste the issue.
  - Pasted text: save as given. Use the id the user gave, else make a short kebab-case slug from the title (the user can rename it); do not ask.
  - Fetch failed or tool missing: say so and ask for pasted text, ending with a Next block ("paste the ticket text"). Do not guess content.

## 2. Overview (for the human to read)

Before sizing, check the card against the repo as it is now: read the code it points at, `git log` for the area,
and open or linked PRs/issues. Then, at most ten lines: **Validity** (`valid`, `real bug`, `already fixed`,
`stale or partly wrong` (claims don't match the code), `duplicate`, `nitpick` or `unverifiable`, with a one-line reason
and a file or PR reference); what is asked; acceptance criteria and what is unclear; the likely repo(s) from `repos.yaml`;
size and risk (auth, data, infra, migrations). Flag anything blocking.

If Validity is not `valid` or `real bug`, say so first and stop: the human decides to continue, close the card, or fix
the card text. Still show the rest of the overview, but do not propose a workflow until they answer. On "continue" go to
§3; after a card-text fix, redo §2. A card with no repo pointers is `unverifiable`.

## 3. Workflow

- `python3 scripts/workflow.py list` prints each workflow's "use when". Pick the best match and give the reason in one line,
  or say none fits and propose a custom step list (same format as `workflows/*.md`: `## step-id`, `persona:`, `gate:`, `writes_code:`, instructions;
  write it to `desk/<card-id>/workflow.md`). If the user named a workflow, use it.
- Show the steps with their persona and gate (`python3 scripts/workflow.py show <name|file>`).
  If the repo's rules require an entry that needs the PR number (a changelog fragment), propose a `followup` step after `pr` (see the README, *A follow-up that needs the PR number*).
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
   - Gated: `awaiting` is set. Summarize the artifact in a few lines with its path, then paste the **Next** block `finish` printed.
     **Stop.** Do not write `approvals.json` and do not call `advance` until the user has approved.
6. Human outcomes at a gate: `/approve` → the approve skill advances. Feedback → `python3 scripts/desk.py revise desk/<card-id> '<feedback>'`
   and redo the step. "Go back to X" → `desk.py reject desk/<card-id> <step> '<reason>'`.
   Add or skip steps on request: `desk.py add desk/<card-id> <after-step> '<step-json>'`, `desk.py skip desk/<card-id> <step>`.
7. When `current` is `done`: summarize what was delivered and where (worktree paths, branches, PR link from `pr.md`). If `pr.md` has no `## Opened` section, the PR was not opened: run `python3 scripts/pr.py desk/<card-id>` (it works on a done card).

Resume: if `awaiting` is set and `approvals.json` has it, run `desk.py advance` (for `pr`, run `python3 scripts/pr.py desk/<card-id>` first); if not approved, show the artifact and remind the user to `/approve`.

## Next block

Every `/work` and `/approve` reply ends with a **Next** block, just before the location block. For a gated step, paste what
`desk.py finish` printed (it names `/approve <card-id>`). Otherwise write it in the same shape from this table; `Needed` quotes
the artifact's `## Open questions` when there are any. A failed or blocked state names the exact command, or asks for the missing input.

| State | Run | Needed |
|---|---|---|
| Intake done / workflow proposed | reply "ok", or name a workflow | confirm or edit the steps: add, skip, reorder, change a gate or persona |
| Gated step finished | `/approve <card-id>` | feedback ("redoes this step"), "go back to <step>", or the open questions |
| Validity is not `valid` or `real bug` | none | continue, close the card, or fix the card text |
| Step blocked (hook denied an edit, no card awaiting) | the command the error names | what the error says is missing |
| Fetch failed or tool missing | none | paste the ticket text |
| Run done | none | merge the draft PR (yours) |

## Rules

- Tracker writes (comments, status changes, creating issues) need the human's explicit approval first. Opening a PR is approved by `/approve` on the `pr` step (no second confirmation); `scripts/pr.py` opens it as a draft. Merging is the human's.
- Status updates in tracker comments are summaries, not logs.
- End each reply with where work landed: Bureau path, card folder, worktree and branch, committed or not.
