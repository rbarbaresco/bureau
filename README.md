# Bureau

Bureau runs a work item (a Jira ticket, a GitHub issue, a Sentry issue, a pasted user story) through a **workflow**: an ordered list of steps such as triage, plan, build, review and PR. Each step is done by a **persona** (architect, staff engineer, QA…), and any step can be a **gate**, meaning the agent stops and waits until you approve.

It runs inside a [Claude Code](https://claude.com/claude-code) session. There is no server, no UI and no database: it is a folder of skills, markdown files, a few small Python scripts and two hooks.

```
you:    /work https://github.com/acme/shop/issues/412
bureau: [reads the issue, shows a short overview, proposes the "bugfix" workflow]
you:    looks good
bureau: [triages, writes a plan, stops]  → you read plan.md, then type /approve
bureau: [creates a worktree, writes the failing test and the fix, stops]  → /approve
bureau: [reviews the diff with a read-only QA persona, drafts the PR, stops]  → /approve
```

## Contents

- [Requirements](#requirements)
- [First steps](#first-steps)
- [Your first run](#your-first-run)
- [How it works](#how-it-works)
- [What is enforced, and what is not](#what-is-enforced-and-what-is-not)
- [Customizing](#customizing)
- [Files and layout](#files-and-layout)
- [Troubleshooting](#troubleshooting)
- [Tests](#tests)
- [Status and limits](#status-and-limits)

## Requirements

| Needed | For |
|---|---|
| [Claude Code](https://claude.com/claude-code) | Runs the skills and hooks. Tested on 2.1.304 |
| `python3` (standard library only) and `git` | The hooks and scripts |
| `gh` (GitHub CLI), logged in | Reading GitHub issues and PRs, opening draft PRs |
| `acli` (Atlassian CLI), logged in | Reading Jira work items. Optional, and not yet exercised (see [limits](#status-and-limits)) |

Bureau runs on Linux and macOS. Windows is untested.

## First steps

1. **Clone Bureau and enter it.** You start Claude Code from this folder, because that is where the hooks and skills load from.

   ```sh
   git clone https://github.com/rbarbaresco/bureau.git
   cd bureau
   ```

2. **Register your repositories.** Bureau never clones for you. It creates worktrees (extra working folders of a repo, each on its own branch) from clones you already have. Tell it where they are:

   ```sh
   cp repos.yaml.sample repos.yaml
   ```

   Then edit `repos.yaml`:

   ```yaml
   repos:
     shop:                       # the name you use for the repo in workflows
       path: ~/code/shop         # an existing clone
       base: main                # branch that new worktrees start from
     shop-api:
       path: ~/code/shop-api
       base: develop
   ```

   `repos.yaml` is gitignored, because it holds paths from your machine. A repo can be listed under any name, and a card can use several.

3. **Log in to the tools you will use.** `gh auth status` and, for Jira, `acli jira auth status` (log in with `acli jira auth login`). If a tool is missing, you can always paste the card text instead.

4. **Start Claude Code in the Bureau folder.**

   ```sh
   claude
   ```

   Project hooks load automatically. If Claude Code asks whether to trust the folder and its hooks, review `.claude/settings.json` (two entries, both calling scripts in `hooks/`) and accept.

5. **Check that the gates are active.** In the session, run `/hooks` and confirm you see one `PreToolUse` and one `UserPromptSubmit` entry.

## Your first run

Start with something small and low risk, such as a typo or a failing test in a repo you registered.

```
/work <ref> [workflow]
```

`<ref>` can be:

| You give | Bureau does |
|---|---|
| A GitHub issue or PR URL, or `owner/repo#123` | Reads it with `gh` |
| A Jira key (`SHOP-42`) or URL | Reads it with `acli` |
| A Sentry link | Uses a connected Sentry tool if you have one, else asks you to paste the issue |
| Pasted text | Uses it as the card. A short card id is made from the title |
| An existing card id | Resumes that run where it stopped |

What happens next:

1. **Intake.** The card is saved to `desk/<card-id>/card.md`.
2. **Overview.** You get about ten lines: what is asked, acceptance criteria, what is unclear, the likely repo, size and risk.
3. **Workflow.** Bureau picks the best match from `workflows/` and says why, or proposes a custom step list. You accept it or edit it ("skip review", "add a design step before plan", "make plan use the architect"). Nothing starts until you confirm.
4. **The run.** Bureau does one step at a time and writes an artifact for each (`triage.md`, `plan.md`…). At a gated step it stops, summarizes the artifact and waits.
5. **At a gate you have three answers:**

   | You type | Result |
   |---|---|
   | `/approve` | The gate is recorded and the run moves to the next step |
   | Feedback in plain words | The same step runs again; the old artifact is kept as `plan.v1.md` |
   | "Go back to plan, the approach is wrong" | The run returns to that step; later approvals are cleared |

To continue a run in a new session, run `/work <card-id>` again. It resumes at the current step.

### Asking a persona for advice

At any point, ask in plain words: *"Ask the architect whether this belongs in the monolith."* The `consult` skill runs that persona as a read-only subagent and saves the answer as `desk/<card-id>/consult-architect-1.md`. A consultation never moves the run forward.

## How it works

**Card.** The thing you are working on. Its source of truth is the tracker; Bureau holds a copy in `card.md`.

**Workflow.** A markdown file in `workflows/` listing steps. Two ship with Bureau:

| Workflow | Use when | Steps (gates in bold) |
|---|---|---|
| `bugfix` | A defect you can reproduce or locate in one repo | triage → **plan** → **fix** → review → **pr** |
| `task` | A well-defined story in one repo | understand → **plan** → **build** → review → **pr** |

**Step.** Has a persona, a gate (`none`, `approve` or `approve+check`) and, for steps that edit code, `writes_code: true`.

**Persona.** A markdown file in `personas/` describing a role: what it cares about and how it reports. `writer` personas work in your session. `read-only` personas run as subagents that cannot edit files. Shipped: `architect`, `staff-engineer`, `qa`.

**Desk.** One folder per card, never committed:

```
desk/SHOP-42/
  card.md            the card, as read from the tracker
  workflow.md        this run's own copy of the workflow
  state.json         where the run is: current step, awaiting approval
  approvals.json     which gates you approved (written only by the /approve hook)
  ack.json           which repo rules were loaded (written by hooks/rules.py)
  triage.md plan.md  one artifact per finished step
  worktrees/shop/    the git worktree where code is written, on branch bureau/SHOP-42
```

**Division of labour.** The tracker owns *what the work is*. The desk owns *where the run is*. Bureau writes to the tracker (comments, status, new issues) and opens PRs only after you approve. PRs are drafts. Merging is always yours.

## What is enforced, and what is not

Instructions in `AGENTS.md` are a request. Two hooks turn the two most important ones into rules the agent cannot skip.

**1. No code before the gate.** A `PreToolUse` hook (`hooks/gate.py`) denies edits inside a card's worktree unless the current step writes code and every earlier gated step is approved. Only a prompt you type (`/approve`, handled by the `UserPromptSubmit` hook `hooks/approve.py`) can approve, so the agent cannot approve itself.

**2. No code before the repo's rules are read.** The same hook denies edits until `hooks/rules.py` has been run for that worktree. It prints and records a hash of:

- the Bureau `AGENTS.md`;
- the `AGENTS.md` and `CLAUDE.md` of the original clone's parent folders, which a worktree under `desk/` would otherwise lose (for example a team-wide rules file one level above the clone);
- the repo's own `AGENTS.md` and `CLAUDE.md`, with their `@imports`.

If any of those files change, the hash no longer matches and the rules must be loaded again. Subagents run through the same hook.

**What these do not cover.** Be clear about the limits:

- Bash is gated with a read-only allowlist (`ls`, `cat`, `rg`, `grep`, `git status|log|diff`…). A deliberate evasion, such as a script that writes files, can slip through.
- The agent can edit `state.json`, for example to fake the current step. This protects against skipped steps and forgetfulness, not against a hostile agent.
- On steps that do not write code, any Bash command outside the allowlist that touches the worktree is denied, including running tests.

## Customizing

### Add a workflow

Create `workflows/<name>.md`:

```markdown
---
name: spike
use_when: Time-boxed investigation of an unknown; the output is a recommendation, not code.
---
## investigate
persona: architect
gate: none

Read card.md and the relevant code. Write investigate.md: options, evidence, what is still unknown.

## recommend
persona: architect
gate: approve

Write recommend.md: one recommendation, its trade-offs, and what you would do next.
```

Rules: each `## heading` is a step id, unique within the file. Optional lines before the instructions: `persona:`, `gate:` (`none`, `approve`, `approve+check`), `writes_code: true`. `use_when` is what Bureau reads to pick a workflow, so write it as a short rule that also says when *not* to use it. Check it with:

```sh
python3 scripts/workflow.py show spike
python3 scripts/workflow.py list
```

### Add a persona

Create `personas/<name>.md`; the file name must match `name`:

```markdown
---
name: sre
description: Checks operability: alerts, rollout, rollback, failure modes.
mode: read-only
---
You are an SRE reviewing a change before it ships. Check ...
```

`mode` is `writer` or `read-only`. A step that writes code must use a `writer`. You can also describe a persona on the fly ("review this as a security engineer"); Bureau saves it in that card's folder and offers to promote it to `personas/`.

### Change a run while it is going

Say it in plain words: skip a step, add one after another, change a gate. Bureau applies it with `scripts/desk.py add` and `skip`; you can run those yourself too (`python3 scripts/desk.py` prints the usage).

### Keep local files out of the public repo

Anything personal (a persona with your company's conventions, a private workflow) can go in `personas/` or `workflows/` under a name you add to `.git/info/exclude`.

## Files and layout

| Path | What |
|---|---|
| `.claude/skills/work` | `/work`: intake, overview, workflow choice, the run loop |
| `.claude/skills/approve` | `/approve`: continues after the hook has recorded your approval |
| `.claude/skills/consult` | Ask a persona a question about the current card |
| `.claude/settings.json` | Registers the two hooks |
| `hooks/gate.py` | Denies code writes until the gate and the rules are satisfied |
| `hooks/rules.py` | Collects and acknowledges the repo's instruction files |
| `hooks/approve.py` | Records `/approve` from your own prompt |
| `scripts/desk.py` | Card state and transitions: `init finish advance revise reject add skip list` |
| `scripts/workflow.py` | Parses workflows: `list show start` |
| `scripts/worktree.py` | Creates a card's worktree from `repos.yaml` |
| `workflows/`, `personas/` | The shipped workflows and personas, yours to extend |
| `AGENTS.md` | Base rules loaded for every card |
| `repos.yaml.sample` | Copy to `repos.yaml` |
| `desk/` | Run state, gitignored |
| `tests/` | Unit tests and the end-to-end check |
| `STEPS.md` | Build log: what is done and how each step was verified |

## Troubleshooting

| You see | Cause and fix |
|---|---|
| "Repo rules for 'x' are not loaded or changed" | Run the command in the message (`python3 hooks/rules.py desk/<card>/worktrees/<repo>`). Bureau normally does this itself |
| "Gate 'plan' is not approved" | Type `/approve` (or `/approve <card-id>` if more than one card is waiting) |
| "/approve needs exactly one card awaiting approval" | Zero or several cards are waiting: add the card id |
| "Step 'x' does not write code" | The run is not on a build step yet; finish the earlier steps |
| "unknown repo 'x'" | Add it to `repos.yaml` |
| `/approve` seems to do nothing | Check `/hooks`. The hooks load from `.claude/settings.json` only when Claude Code is started inside the Bureau folder |
| A read-only command is denied | Redirects other than to `/dev/null` and pipes into non-allowlisted commands count as writes. Simplify the command, or approve the build step first |
| Jira card cannot be read | Check the `acli` login, or paste the story text |

## Tests

```sh
python3 -I -m unittest discover -s tests   # 29 unit tests, no network, a few seconds
tests/e2e_canary.sh                         # real `claude -p` runs; costs a few model calls
```

The end-to-end script builds a throwaway Bureau copy and checks that a write is refused before the rules are loaded, that rules from both the repo and a parent folder then reach the model, and that a raw `/approve` prompt reaches the hook. Run it again after upgrading Claude Code, since the hooks depend on its behaviour. Set `E2E_MODEL` to change the model.

## Status and limits

- **Claude Code only.** The files are plain markdown and Python, so Cursor and Codex adapters are possible later; none exist.
- **Single repo per card in practice.** `repos.yaml` and the desk allow several repos per card, but the shipped workflows assume one.
- **Not built yet:** a `project` workflow (discovery, creating child stories, nested task runs), Sentry intake without a pasted issue, a trial on a real production card.
- **Tested with real sessions:** pasted stories, GitHub issues, the full plan → fix → review → PR-draft loop on a scratch repo. Jira intake through `acli` has not been exercised.
- Early work: expect rough edges, and read `STEPS.md` for what has been verified.
