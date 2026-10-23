---
name: rework
description: Rework a finished card from review feedback on its open draft PR. Only for a card Bureau ran locally that is done and whose PR is open with comments; refuses otherwise and names the right command. Use for "address the review comments", /rework <card>. Not for starting or continuing a task (that is /work).
---

# /rework <card-id>

Paths are relative to the Bureau root. A hook claims the card for this session when you type `/rework <id>`, as for `/work`.

## 1. Check first

Run `python3 scripts/rework.py desk/<card-id>`.
On a non-zero exit, show its message, change nothing, and end with a **Next** block (see the `work` skill) naming the command the message gives (`/work …`) or what is missing. Do not add steps, create a worktree or try another route: the script refuses when the card is not local, is not done, has no PR opened, has lost its worktree and branch, has a merged or closed PR, or has no review to check (no unresolved thread and no new comment).

If `state.json` already has a rework step as `current` (`feedback`, `apply`, `rework-review`, with or without `-N`), a round is open: skip step 2 and carry on with that step through the `work` skill's run loop. Fetch the threads only in `feedback`; later steps work from `feedback.md` and `apply.md`, because once the threads are resolved or answered on GitHub the script has nothing left to print.

## 2. Open the rework round

Round 1 uses the ids below. For round N > 1 (when `feedback` already exists in `state.json`) add `-N` to each id, and anchor the first `add` on the previous round's last step (`rework-review`, or `rework-review-2` for round 3).

```
python3 scripts/desk.py add desk/<card> <last-step> '{"id":"feedback","persona":"staff-engineer","gate":"approve","writes_code":false}'
python3 scripts/desk.py add desk/<card> feedback '{"id":"apply","persona":"staff-engineer","gate":"approve","writes_code":true}'
python3 scripts/desk.py add desk/<card> apply '{"id":"rework-review","persona":"qa","gate":"none","writes_code":false}'
python3 scripts/desk.py reject desk/<card> feedback 'PR feedback'
```

Then run the steps as in the `work` skill's run loop.

## feedback (read-only, gate approve)

Input: the JSON `rework.py` printed (rerun it for fresh comments). If it says `truncated`, or a thread has more comments than it lists (`comments.totalCount`), say so in the artifact.
Every unresolved thread gets a row, including those with `"author_last": true` (the PR author spoke last). Read the whole thread against the current code: the author said "will do" or promised a change → it is still work, action change; fixed in a later commit or answered with nothing left to do → skip, "fixed in <commit>, skipping"; the reply is valid and settles it → skip, "valid reply, taken into account"; the reply is wrong or incomplete → change or reply. A thread with more comments than listed (`comments.totalCount`) needs its `url` read before judging. Never drop a thread silently.
Write `desk/<card>/feedback.md`: a table with one row per thread or comment: link, verdict (valid / already addressed / out of scope / wrong), a one-line reason, proposed action (change / reply / ask / skip). Check "already addressed" against the worktree's current code. Give the drafted reply text under the table for every reply and ask row. Nothing is posted or changed in this step.
`/approve` approves the listed changes and the listed replies, verbatim. End with `## Open questions` (or "none").

## apply (writes code, gate approve)

0. Record the branch head before changing anything: `Base: <sha>` at the top of `apply.md` (the QA step diffs from it).
1. If `desk/<card>/worktrees/` has no worktree, recreate it: `python3 scripts/worktree.py desk/<card> <repo>` (`repo` is in the `rework.py` output). Load the rules (`python3 hooks/rules.py …`).
2. Make only the changes approved in `feedback.md`, test first, and update docs the same way `build` does. Commit everything.
3. Push without force: `git -C <worktree> push origin bureau/<card>`. If it is rejected, stop and report; do not force or rebase.
4. After the push succeeds, post only the approved replies, unchanged, one call each: to a review thread, `gh api repos/{owner}/{repo}/pulls/<pr>/comments/<databaseId>/replies -f body=<text>` with the `databaseId` of the thread's first comment; to a top-level comment or review, `gh pr comment <pr> --body <text>`.
5. Write `apply.md`: commits, replies posted, anything approved but not done and why. End with `## Open questions` (or "none").

## rework-review (qa, read-only)

Read-only subagent with the persona, rule output, `feedback.md` and the diff from the `Base:` sha in `apply.md` to the branch head. It checks each approved row was done, nothing unapproved was changed, and the tests cover the change. Write `rework-review.md`, findings ranked.

When `current` is `done`, report the PR link and that merging is the human's.
