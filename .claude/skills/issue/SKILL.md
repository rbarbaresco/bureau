---
name: issue
description: Draft, and after approval file, a GitHub issue for Bureau or another repo. Use for "write an issue", "draft a ticket for this", "file this as an issue", "open an issue about…", even when the user only describes a problem or an idea and has not said "issue".
---

# Write a GitHub issue

An issue is a work artifact: one reader who has the context, picking it up later. Write the summary, not the case.

1. **Repo.** The one the user names, else the current repo (`gh repo view --json nameWithOwner`). If the issue is about code, read the files it points at so the problem cites real paths (`file:line`), not "the permission system".
2. **Template.** Propose this one; do not go looking for another. Body: **Problem**, then one of **Expected** (a change is clear), **To verify** (a suspicion), or **Question** (a decision is needed). One label from `gh label list` (`bug`, `enhancement`, `question`, `documentation`). Keep it short.
3. **Write the draft.**
   - Problem: what happens, where, and why it matters, in a few sentences. Quote exact error text.
   - Expected, To verify or Question: the outcome wanted, not a design. If the user has a design, give it one line and name the open choice.
   - Skip proposal tables, acceptance-criteria lists and scope sections unless the user asks. Evidence (commands, logs, long lists) goes in a first comment, with one pointer from the body.
   - Say plainly when something is unknown or unverified, rather than inventing a cause.
4. **Show the draft** with the title, label and target repo, and **wait**. Creating an issue is a tracker write, so it needs the user's explicit go-ahead.
5. **File it** after approval: write the body to the scratchpad and run `gh issue create --repo <repo> --title '<title>' --label <label> --body-file <file>`. Give back the URL.

Edits to an issue that already exists (`gh issue edit`, comments) need the same approval.

End the reply with where work landed, per `AGENTS.md`: for a draft, "no files changed"; after filing, the issue URL.
