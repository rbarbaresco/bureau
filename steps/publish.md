---
name: publish
use_when: A document (RFC, ADR, wiki page) goes out for people to read, and each published version needs the human's approval. Not for docs inside a repo (use docs).
---
## publish
persona: journalist
gate: approve
loop: true
voice: operator

Each round: revise the document from the human's notes and the readers' comments, and write publish.md: the full text (or its path), where it will be published, and what changed since the last round. Publishing is a write outside Bureau, so it happens only after `/approve`, right after the approval: on `/approve` publish the round just kept as `publish.round-N.md` (the highest N); on `/approve done` publish `publish.md` (the last round is not renamed). Add the link to the file you published, then start the next round or, after `done`, the next step. Never publish an unapproved round.
End the artifact with `## Open questions`: one numbered item per question, written `Short label: full question, with options and a default if there is a choice (Default: X)`. The label is what the Next block shows. Put statements and assumptions elsewhere in the artifact. Write "none" if there are no questions.
