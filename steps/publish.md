---
name: publish
use_when: A document (RFC, ADR, wiki page) goes out for people to read, and each published version needs the human's approval. Not for docs inside a repo (use docs).
---
## publish
persona: journalist
gate: approve
loop: true

Each round: revise the document from the human's notes and the readers' comments, and write publish.md: the full
text (or its path), where it will be published, and what changed since the last round. Publishing is a write outside
Bureau, so it happens only after `/approve`: right after the approval (on `/approve` and on `/approve done`), publish the
version just approved (now `publish.round-N.md`, the highest N) and add its link to that file, then start the next round
or, after `done`, the next step. Never publish an unapproved round.
End the artifact with `## Open questions` (or "none").
