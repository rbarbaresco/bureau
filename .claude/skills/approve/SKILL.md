---
name: approve
description: The human's /approve. A UserPromptSubmit hook has already recorded the approval; this tells the agent to continue. Typed by the user only.
disable-model-invocation: true
---

The human approved the step that was awaiting approval. The hook recorded it in `approvals.json`.

1. Find the card (`python3 scripts/desk.py list`; the one whose `awaiting` was just approved).
2. Run `python3 scripts/desk.py advance desk/<card>`. If it errors, the approval was not recorded: tell the user and stop.
3. Continue with the new current step, as in the `work` skill's run loop.
