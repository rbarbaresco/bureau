---
name: archive
description: Move a finished card out of desk/ into desk/.archive/ and remove its worktrees. Typed by the user only, as /archive <card-id>, usually once the PR is merged.
disable-model-invocation: true
---

1. Take the card id from the user's `/archive <card-id>`; if there is none, ask. Never pick one from `desk/`.
2. Run `python3 scripts/archive.py desk/<card-id>`. It refuses, moving nothing, unless the card is `done`, no other live session holds it, and every worktree is clean with its branch pushed. Report its refusal as is; do not work around it.
   If the refusal lists uncommitted changes or unpushed commits, show that list to the user and ask whether to archive anyway (uncommitted changes are discarded; unpushed commits stay on the local `bureau/<card-id>` branch). Only after an explicit yes in the user's own reply, re-run with `--force`. Never add `--force` on your own.
3. On success, say where the card went (the path it printed). The local `bureau/<card-id>` branch is kept. `scripts/ui.py` still shows the card, under Archived.
