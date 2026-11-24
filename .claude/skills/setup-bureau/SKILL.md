---
name: setup-bureau
description: The human's /setup-bureau. A UserPromptSubmit hook prints the settings questionnaire (from bureau.template.json) or saves the answers to bureau.json; this pastes its text. Typed by the user only.
disable-model-invocation: true
---

The hook `hooks/setup.py` has already run on the human's line. It printed the questionnaire above (with `Saved to bureau.json` first, if the line had answers), or it blocked the prompt.

1. Paste the hook's text exactly as printed, in a code block. Do not reword, reorder or answer it.
2. Never write `bureau.json` yourself (the gate hook denies it). The human answers by typing `/setup-bureau 1a 2c 3b`.
3. If nothing was printed, the hook did not run: tell the user to check `/hooks` (the hooks load only when Claude Code starts in the Bureau folder).

No files change in this step apart from what the hook wrote.
