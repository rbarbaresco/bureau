# Build steps

Each step is done only when its test passes. Update the status as you go.

| # | Step | Test (done when) | Status |
|---|---|---|---|
| 0 | Hooks: rules loader, PreToolUse gate, `/approve` hook | `python3 -I -m unittest discover -s tests` passes (12 tests) | done |
| 1 | Layout: real skills in `.claude/skills/` (no symlink), base `AGENTS.md`, `README` with setup | `ls -la .claude` shows a directory; `AGENTS.md` is picked up by `rules.py` (add a unit test) | done |
| 2 | End-to-end canary: repo rule and ancestor rule both reach the model; write refused without ack; confirms the hook sees a raw `/approve` prompt | `tests/e2e_canary.sh` exits 0 | done (passes with claude-haiku-5-5, Claude Code 2.1.304) |
| 3 | Desk bootstrap: `scripts/worktree.py` reads `repos.yaml`, creates `desk/<card>/`, the worktree and `state.json` | unit test on a scratch repo: folder, worktree and valid `state.json` exist; the gate allows an edit after approve + ack | done |
| 4 | Step transitions: approve / revise (artifact versioned) / reject (back to a named step) | unit tests for each transition on `state.json` | done |
| 5 | Workflow format, `bugfix` and `task` files, and a loader that turns one into `state.json` steps | unit test loads both and rejects a malformed one | done |
| 6 | Personas (architect, staff engineer, QA) and the `consult` skill | persona frontmatter validates; manual: "ask the architect …" saves a note in the card folder | open |
| 7 | `work` skill: intake (`gh`, `acli`, paste) into `card.md`, overview, workflow match, start or resume | manual on one real GitHub issue and one pasted story; resume after a new session lands on the right gate | open |
| 8 | Dogfood on one real bugfix card, then adjust | you drove it end to end | open |
| 9 | Later: `project` workflow (discovery, story creation, nested tasks), Sentry intake, Cursor/Codex adapters | n/a | deferred |
