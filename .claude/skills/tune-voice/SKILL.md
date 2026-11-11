---
name: tune-voice
description: The human's /tune-voice. Create or refine voice.md, how the operator wants text for other people to read (PR bodies, review comments and replies, issues, ticket comments, documents). Steps with `voice: operator` apply it. Typed by the user only.
disable-model-invocation: true
---

# /tune-voice [change]

`voice.md` at the Bureau root (gitignored, never committed) is a voice layer, not a role. The step persona decides what to say; the voice decides how it sounds. Write only rules the user confirmed.

1. **Read what exists.** `voice.md`, if present, and the global instruction files already in your context (`~/AGENTS.md`, `~/.claude/CLAUDE.md` and the like). Tell the user in two or three lines what those already cover. The voice file adds to them and never restates or contradicts them; on a conflict, ask which one wins and change only `voice.md`.
2. **A one-line change** (`/tune-voice PR bodies: no headings`): apply just that, show the diff, write on the user's ok. Skip the rest.
3. **Pick sources.** Ask one multi-select question (AskUserQuestion, `multiSelect: true`): where should the voice be learned from? Options, only for sources this session can actually read:
   - **Past sessions (Recommended)**: `python3 scripts/voice_samples.py --out <scratchpad>/voice-samples.md` (`--exclude <project-substring>` for projects the user wants left out; ask in the same question's text).
   - **GitHub**, if `gh auth status` succeeds: the user's own PR bodies, review comments and issues (`--author @me`).
   - **Jira**, if `acli` is installed: the user's own ticket comments.
   - **Any connected tool** holding text the user wrote (Slack, email, Confluence, docs). A tool that only offers `authenticate` is not connected: list it in the question text as "needs sign-in", not as an option.
   At most 4 options: offer the 3 likeliest plus past sessions, and name the rest in the question text so the user can type them under "Other". No pick means interview only.
4. **Read each source** with one read-only subagent per source, in parallel. Its prompt: read only text the user authored (their sent messages, their PRs and comments, pages they wrote), about 30 recent items; return proposed rules grouped by kind of text, each with one reference (URL or session id), no quote longer than one sentence. For past sessions, weigh the user's corrections of a draft ("too long", "no headings") over their ordinary chat, which is instructions, not a writing sample; ignore bare approvals ("ok", "file it"). Reading is not a tracker write; never post, send or edit anything.
5. **Interview the gaps.** Merge the proposals, drop duplicates of step 1, then ask about what is still missing for each kind of text: length, tone, structure, always/never, language, an example the user likes. A few questions per round; any kind can be skipped.
6. **Show the full file (or the diff when refining) and wait.** Write `voice.md` only on the user's ok. A rule about content (what a review must check, how severe a finding is) belongs in a persona or step: say where, and leave it out.

Format:

```markdown
---
name: operator
description: <one line>
---
## General
## PR descriptions
## Review comments and replies
## Issues
## Ticket comments
## Documents
## Examples
```

Leave out empty sections. Rules are short imperative lines; examples are short and tagged with their kind of text.

End with the path of `voice.md` and of any scratch file written.
