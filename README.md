# Bureau

Run day-to-day work items through gated, configurable agent workflows from a Claude Code session.
Give it a ticket, issue or pasted story; read the overview; accept or edit a workflow; approve each gated step.

> Status: first slice in progress. See [STEPS.md](STEPS.md).

## Setup

```sh
cp repos.yaml.sample repos.yaml   # point each name at one of your existing clones
cd bureau && claude               # hooks in .claude/settings.json load automatically
```

Needs `python3` and `git`. Optional: `gh` (GitHub), `acli` (Jira).

## Layout

| Path | What |
|---|---|
| `.claude/skills/` | `/work`, `/approve`, `/consult` |
| `workflows/` | Named workflows (`bugfix`, `task`). Each has a "use when" line |
| `personas/` | Roles used by steps and for consultation |
| `hooks/` | The gates (below) |
| `desk/` | One folder per card: state, artifacts, worktrees. Gitignored |
| `repos.yaml` | Your clones. Gitignored; copy from `repos.yaml.sample` |

## What is enforced, and what is not

- Code edits in a card's worktree are **denied** until the previous gated steps are approved with
  `/approve` (typed by you) and the repo's instruction files were loaded with `hooks/rules.py`.
- Subagents are covered by the same hook. Bash is gated with a read-only allowlist.
- **Not covered:** deliberate evasion (scripts that write files, hand-editing `state.json`).
  This guards against skipped steps, not a hostile agent.

## Tests

```sh
python3 -I -m unittest discover -s tests
```
