---
name: tune-voice
description: The human's /tune-voice. Create or refine voice.md, how the operator wants text for other people to read (PR bodies, review comments and replies, issues, ticket comments, documents). Steps with `voice: operator` apply it. Typed by the user only.
disable-model-invocation: true
---

`voice.md` at the Bureau root (gitignored) is how the text sounds, not what it says: the step persona keeps the content. Write only rules the user confirmed.

1. **Read what exists:** `voice.md`, and the global instruction files in your context (`~/AGENTS.md`, `~/.claude/CLAUDE.md`). Say in two lines what they already cover. `voice.md` only adds to them; on a conflict, ask which wins and change only `voice.md`.
2. **One change** (`/tune-voice PR bodies: no headings`): apply it, creating the file in the format below if it is missing, show the diff, write on the user's ok. Stop there.
3. **Pick sources** with one AskUserQuestion, `multiSelect: true`, 2–4 options:
   - `Interview only`: always offered, so the question is valid with no source.
   - `Past sessions (Recommended)`: `python3 scripts/voice_samples.py --out <scratchpad>/voice-samples.md`.
   - `GitHub`, if `gh auth status` succeeds: the user's own PRs, review comments and issues (`--author @me`).
   - `Jira` if `acli` is installed, or any connected tool holding text the user wrote (Slack, email, Confluence, docs). A tool that only offers `authenticate` is not connected: name it in the question text as "needs sign-in".
   Over four, keep the likeliest and name the rest in the question text for "Other". If past sessions is picked, ask next which projects to leave out: `None (Recommended)` plus up to 3 folder names from `$CLAUDE_CONFIG_DIR/projects` (default `~/.claude/projects`), each picked one becoming `--exclude <name>`.
4. **Read each source** with one read-only subagent per source, in parallel. Prompt: only text the user authored, about 30 recent items; return proposed rules per kind of text, each with one reference (URL or session id), no quote over one sentence. In sessions, the user's corrections of a draft ("too long", "no headings") count most; skip bare approvals ("ok", "file it"). Never post, send or edit anything.
5. **Interview the gaps:** merge the proposals, drop what step 1 covers, then ask, a few questions a round, what is still missing per kind of text: length, tone, structure, always/never, language, an example they like. Any kind can be skipped.
6. **Show the file (or the diff) and wait;** write `voice.md` on the user's ok. A content rule (what a review checks, how severe a finding is) belongs in a persona or step: say where, and leave it out.

Format: frontmatter `name: operator` and a one-line `description`, then any of `## General`, `## PR descriptions`, `## Review comments and replies`, `## Issues`, `## Ticket comments`, `## Documents`, `## Examples` (short, each tagged with its kind of text). Rules are short imperative lines; leave empty sections out.

End with the path of `voice.md` and of any scratch file written.
