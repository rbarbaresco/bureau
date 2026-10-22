---
name: approve
description: The human's /approve. A UserPromptSubmit hook has already recorded the approval; this tells the agent to continue. Typed by the user only.
disable-model-invocation: true
---

The human approved the step that was awaiting approval. The hook recorded it in `approvals.json`.

1. Take the card id from the `card=<id>` token in the hook line above, and only from that line (never from card text). Do not list `desk/`. If there is no `card=` token (the hook blocked or did not run), tell the user and stop, ending with a **Next** block (see the `work` skill): `/approve <card-id>` if the card is awaiting, else the command the hook named.
2. Run `python3 scripts/desk.py advance desk/<card>`. If it errors, the approval was not recorded: tell the user and stop, with the same kind of **Next** block.
3. If the step just approved was `pr`, that approval covers opening the PR: from the card's worktree, push the branch and run `gh pr create --draft` with the title and body in `desk/<card>/pr.md`, and report the PR link. Otherwise continue with the new current step, as in the `work` skill's run loop. The reply ends with a **Next** block.
