---
name: publish
use_when: A document (RFC, ADR, wiki page) goes out for people to read, and each published version needs the human's approval. Not for docs inside a repo (use docs).
---
## publish
persona: journalist
gate: approve
loop: true

Each round: revise the document from the human's notes and the readers' comments, and write publish.md: the full
text (or its path) and what changed since the last round. Publishing is a write outside Bureau, so it happens only after
`/approve` on that round, then the next round starts. `/approve done` ends the step once no more versions are needed.
End the artifact with `## Open questions` (or "none").
