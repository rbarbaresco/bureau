---
name: archive
description: Move a finished card out of desk/ into archive/ and remove its worktrees. Typed by the user only, as /archive <card-id>, usually once the PR is merged.
disable-model-invocation: true
---

1. Take the card id from the user's `/archive <card-id>`; if there is none, ask. Never pick one from `desk/`.
2. Run `python3 scripts/archive.py desk/<card-id>`. It refuses, moving nothing, unless the card is `done`, no other live session holds it, and every worktree is clean with its branch pushed. Report its refusal as is; do not work around it.
3. On success, say where the card went (the path it printed). The local `bureau/<card-id>` branch is kept. `scripts/ui.py` still shows the card, under Archived.
