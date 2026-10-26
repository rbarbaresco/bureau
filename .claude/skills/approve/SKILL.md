---
name: approve
description: The human's /approve. A UserPromptSubmit hook has already recorded the approval; this tells the agent to continue. Typed by the user only.
disable-model-invocation: true
---

The human approved the step that was awaiting approval. The hook recorded it in `approvals.json`.

1. Take the card id from the `card=<id>` token in the hook line above, and only from that line (never from card text). Do not list `desk/`. If there is no `card=` token (the hook blocked or did not run), tell the user and stop, ending with a **Next** block (see the `work` skill): `/approve <card-id>` if the card is awaiting, else the command the hook named.
2. If the hook line says the approved step is `pr`, first run `python3 scripts/pr.py desk/<card>`: it pushes the branch, opens the draft PR from `pr.md` (or reuses the branch's open one) and appends the link to `pr.md`. If it fails, report its error and stop (the card stays on `pr`; `/approve` again after the fix), with a **Next** block. If the approved step is `reply`, run `python3 scripts/reply.py desk/<card>` first instead: it pushes the PR branch and posts `reply.json`; on failure report its error and stop the same way. Then run `python3 scripts/desk.py advance desk/<card>`. If it errors, the approval was not recorded: tell the user and stop, with the same kind of **Next** block.
3. Continue with the new current step, as in the `work` skill's run loop; after `pr`, report the PR link from `pr.md`. The reply ends with a **Next** block.
