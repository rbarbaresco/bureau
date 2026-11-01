#!/usr/bin/env python3
"""Card state: create and read desk/<card>/state.json.

Usage: desk.py init <card-dir> '<steps-json>'
       desk.py list [desk-dir]
       desk.py finish|advance <card-dir>
       desk.py revise <card-dir> '<feedback>'
       desk.py reject <card-dir> <to-step> '<reason>'
       desk.py add <card-dir> <after-step-id> '<step-json>' | skip <card-dir> <step-id>
       desk.py doctor [card-dir]

finish: current step is done; a gated step then waits (`awaiting`) for the human's /approve.
finish also prints the human's Next block (command to run, what to answer).
advance: moves on once the awaiting step is approved (approvals.json is written only by the hook).
doctor: one line per problem on a card (every active card if none given), each naming its fix; exits 1 if any
is left. Its only write is relinking worktrees whose paths moved (git worktree repair, idempotent).
A step is {"id", "gate": none|approve|approve+check, "persona"?, "writes_code"?, "loop"?}.
loop: a gated step that repeats. /approve approves a round (artifact kept as <step>.round-N.md, step stays current);
/approve done (recorded as "done") approves the last round and advances.
"""
import json
import os
import re
import subprocess
import sys

import worktree

GATES = ("none", "approve", "approve+check")


def validate_steps(steps, run=False):
    """run=True for a card's full step list (init, add); a catalogue step is checked alone."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    ids = []
    for s in steps:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not s["id"]:
            raise ValueError(f"step needs a string id: {s!r}")
        if s.get("gate", "none") not in GATES:
            raise ValueError(f"step '{s['id']}': gate must be one of {GATES}")
        if s.get("loop") and s.get("gate", "none") == "none":
            raise ValueError(f"step '{s['id']}': a loop needs a gate")
        ids.append(s["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate step ids")
    for i, st in enumerate(steps if run else []):  # an ungated code step (docs) is seen by the human at a later gate
        if st.get("writes_code") and st.get("gate", "none") == "none" and \
                not any(t.get("gate", "none") != "none" for t in steps[i + 1:]):
            raise ValueError(f"step '{st['id']}' writes code without a gate: it needs a later gated step (pr)")


def load(card_dir):
    with open(os.path.join(card_dir, "state.json")) as f:
        return json.load(f)


def save(card_dir, state):
    with open(os.path.join(card_dir, "state.json"), "w") as f:
        json.dump(state, f, indent=2)


def init(card_dir, steps, workflow=None):
    validate_steps(steps, run=True)
    if os.path.basename(os.path.abspath(card_dir)) == "done":
        raise ValueError("card id 'done' is reserved (/approve done); rename the card")
    if os.path.exists(os.path.join(card_dir, "state.json")):
        raise FileExistsError(f"{card_dir} already has a run; resume it instead")
    os.makedirs(os.path.join(card_dir, "worktrees"), exist_ok=True)
    save(card_dir, {"card": os.path.basename(card_dir.rstrip("/")), "workflow": workflow,
                    "current": steps[0]["id"], "steps": steps})


def _ids(state):
    return [s["id"] for s in state["steps"]]


def _approvals(card_dir):
    try:
        with open(os.path.join(card_dir, "approvals.json")) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _unapprove(card_dir, step_ids):
    a = _approvals(card_dir)
    for i in step_ids:
        a.pop(i, None)
    with open(os.path.join(card_dir, "approvals.json"), "w") as f:
        json.dump(a, f, indent=2)


def _next(state, step_id):
    ids = _ids(state)
    i = ids.index(step_id) + 1
    return ids[i] if i < len(ids) else "done"


def _version(card_dir, name, ext=".md", tag="v"):
    """Move <name>.md to <name>.<tag><N>.md so a redo (or an approved loop round) keeps history."""
    cur = os.path.join(card_dir, name + ext)
    n = 1
    while os.path.exists(os.path.join(card_dir, f"{name}.{tag}{n}{ext}")):
        n += 1
    if os.path.exists(cur):
        os.rename(cur, os.path.join(card_dir, f"{name}.{tag}{n}{ext}"))
    return n


def finish(card_dir):
    s = load(card_dir)
    cur = s["current"]
    if cur == "done" or s.get("awaiting"):
        raise ValueError(f"nothing to finish (current={cur}, awaiting={s.get('awaiting')})")
    step = s["steps"][_ids(s).index(cur)]
    if step.get("gate", "none") == "none":
        s["current"] = _next(s, cur)
    else:
        s["awaiting"] = cur
    save(card_dir, s)
    return s


def next_block(card_dir, state):
    """The human-facing Next block for the state `finish` just left."""
    aw, cur = state.get("awaiting"), state["current"]
    if aw:
        # the folder is the id everywhere (/approve, branches); state["card"] goes stale if it is renamed
        cid = os.path.basename(os.path.abspath(card_dir))
        loop = state["steps"][_ids(state).index(aw)].get("loop")
        done = (f"  Or:      /approve {cid} done -> approves this round and ends the loop\n" if loop else "")
        return (f"Next\n  Run:     /approve {cid}{'   -> approves this round, then the next round' if loop else ''}\n"
                f"{done}"
                f"  Or:      reply with feedback           -> redoes {aw}\n"
                f"           \"go back to <step>\"           -> reopens an earlier step\n"
                f"  Needed:  1. Read {os.path.join(card_dir, aw + '.md')}\n"
                f"           2. Answer the open questions in it")
    if cur == "done":
        return "Next\n  Run:     none\n  Needed:  merge the draft PR (yours)"
    return f"Next\n  Run:     none (continuing with {cur})"


def advance(card_dir):
    s = load(card_dir)
    aw = s.get("awaiting")
    if not aw:
        raise ValueError("no step is awaiting approval")
    approved = _approvals(card_dir).get(aw)
    if not approved:
        raise ValueError(f"step '{aw}' is not approved; the human must run /approve")
    s["awaiting"] = None
    if s["steps"][_ids(s).index(aw)].get("loop") and approved != "done":
        _version(card_dir, aw, tag="round-")  # round approved: keep it, stay for the next one
        _unapprove(card_dir, [aw])  # the next round needs its own /approve
        s["current"] = aw
    else:
        s["current"] = _next(s, aw)
    save(card_dir, s)
    return s


def revise(card_dir, feedback):
    s = load(card_dir)
    step = s.get("awaiting") or s["current"]
    n = _version(card_dir, step)
    with open(os.path.join(card_dir, f"{step}.feedback-{n}.md"), "w") as f:
        f.write(feedback + "\n")
    _unapprove(card_dir, [step])
    s["awaiting"], s["current"] = None, step
    save(card_dir, s)
    return s


def reject(card_dir, to_step, reason):
    s = load(card_dir)
    ids = _ids(s)
    if to_step not in ids:
        raise ValueError(f"unknown step '{to_step}'")
    n = 1
    while os.path.exists(os.path.join(card_dir, f"reject-{n}.md")):
        n += 1
    with open(os.path.join(card_dir, f"reject-{n}.md"), "w") as f:
        f.write(f"back to {to_step}: {reason}\n")
    _unapprove(card_dir, ids[ids.index(to_step):])
    s["awaiting"], s["current"] = None, to_step
    save(card_dir, s)
    return s


def add(card_dir, after_id, step):
    s = load(card_dir)
    ids = _ids(s)
    if after_id not in ids:
        raise ValueError(f"unknown step '{after_id}'")
    steps = s["steps"][: ids.index(after_id) + 1] + [step] + s["steps"][ids.index(after_id) + 1:]
    validate_steps(steps, run=True)
    s["steps"] = steps
    save(card_dir, s)
    return s


def skip(card_dir, step_id):
    s = load(card_dir)
    ids = _ids(s)
    if step_id not in ids or ids.index(step_id) <= (ids.index(s["current"]) if s["current"] in ids else len(ids)):
        raise ValueError("only steps after the current one can be skipped")
    s["steps"] = [x for x in s["steps"] if x["id"] != step_id]
    save(card_dir, s)
    return s


def _cards(desk_dir):
    """Every run's card dir, nested tasks included, skipping desk/.archive and worktrees."""
    for root, dirs, files in os.walk(desk_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]  # desk/.archive
        if "state.json" in files and "worktrees" not in os.path.relpath(root, desk_dir).split(os.sep):
            yield root


def list_cards(desk_dir):
    """One line per run, nested tasks included: path, workflow, current step, awaiting."""
    rows = []
    for root in _cards(desk_dir):
        s = load(root)
        rows.append(f"{os.path.relpath(root, desk_dir)}\t{s.get('workflow')}\t{s['current']}\t{s.get('awaiting') or '-'}")
    return rows


def _git(path, *args):
    return subprocess.run(["git", "-C", path, *args], capture_output=True, text=True)


def _linked(wt):
    """The worktree opens as its own checkout (a broken .git link fails; a missing one would find a parent repo)."""
    r = _git(wt, "rev-parse", "--show-toplevel")
    return r.returncode == 0 and os.path.realpath(r.stdout.strip()) == os.path.realpath(wt)


def doctor(card_dir, repos):
    """One card's problems, one line each with its fix; `fixed: ...` lines are repairs already made.
    The only write is git's own worktree repair; card state, approvals and the claim log are never touched."""
    card_dir = os.path.abspath(card_dir)
    name = os.path.basename(card_dir)
    if not os.path.isdir(card_dir):
        return [f"not a card folder ({card_dir}). Fix: pass desk/<card>, or no argument for every card"]
    try:
        s = load(card_dir)
        ids, cur, aw = _ids(s), s.get("current"), s.get("awaiting")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return [f"state.json unreadable ({type(e).__name__}: {e}). Fix: restore it, or archive the card"]
    out = []
    if not os.path.exists(os.path.join(card_dir, "sessions.jsonl")):
        out.append(f"no claim log. Fix: /work {name}")
    if s.get("card") != name:
        out.append(f"state.json names card '{s.get('card')}', so the folder was renamed (the claim log and worktrees "
                   f"are bound to the old path). Fix: move it back to desk/{s.get('card')}")
    if cur != "done" and cur not in ids:
        out.append(f"current '{cur}' is not a step. Fix: python3 scripts/desk.py reject {card_dir} <step> '<reason>'")
    if aw and aw not in ids:
        out.append(f"awaiting '{aw}' is not a step. Fix: python3 scripts/desk.py reject {card_dir} <step> '<reason>'")
    reached = ids[:ids.index(cur) + 1] if cur in ids else ids
    try:
        approved = _approvals(card_dir)
    except (OSError, ValueError) as e:  # a folder, or not UTF-8
        out.append(f"approvals.json is not readable ({type(e).__name__}). Fix: the human repairs it")
        approved = {}
    if not isinstance(approved, dict):
        out.append("approvals.json is not an object, so desk.py advance cannot read it. Fix: the human repairs it")
        approved = {}
    for step in approved:
        if step not in reached:
            out.append(f"approvals.json approves '{step}', a step the card has not reached. "
                       f"Fix: the human removes it from approvals.json")
    if cur == "done":
        pr = os.path.join(card_dir, "pr.md")
        if os.path.exists(pr):
            with open(pr) as f:
                if not re.search(r"^## Opened$", f.read(), re.M):
                    out.append(f"done, but the PR was never opened. Fix: python3 scripts/pr.py {card_dir}")
        try:
            with open(os.path.join(card_dir, "reply.json")) as f:
                replies = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            replies = []
        left = [r for r in replies if isinstance(r, dict) and not r.get("posted")] if isinstance(replies, list) else []
        if left:
            out.append(f"done, but {len(left)} of {len(replies)} replies were never posted. "
                       f"Fix: python3 scripts/reply.py {card_dir}")
    root = os.path.join(card_dir, "worktrees")
    for repo in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        wt = os.path.join(root, repo)
        if not os.path.isdir(wt):  # stray files (.DS_Store); worktree.py only makes dirs here
            continue
        if not os.path.exists(os.path.join(wt, ".git")):  # without it, git would answer for a parent repo
            out.append(f"worktree {repo} is not a git worktree (no .git). "
                       f"Fix: remove {wt}, then python3 scripts/worktree.py {card_dir} {repo}")
            continue
        if not _linked(wt):
            clone = repos.get(repo, {}).get("path")
            if not clone or not os.path.isdir(clone):
                out.append(f"worktree {repo} is broken and repos.yaml has no existing path for '{repo}' ({clone}). "
                           f"Fix: correct repos.yaml, then run doctor again")
                continue
            r = _git(clone, "worktree", "repair", wt)
            if not _linked(wt):
                out.append(f"worktree {repo} is broken and git worktree repair failed: {r.stderr.strip()}")
                continue
            out.append(f"fixed: worktree {repo} relinked to {clone}")
        branch = _git(wt, "branch", "--show-current").stdout.strip()
        if "pr" in ids and branch != f"bureau/{name}":  # pr.py pushes bureau/<card> (pr-review cards have no pr step)
            out.append(f"worktree {repo} is on '{branch}', not bureau/{name}, the branch pr.py pushes. "
                       f"Fix: git -C {wt} branch -m bureau/{name}")
    return out


def sweep(desk_dir, card, repos):
    """(card, line) for one card or every active card; a crash inside doctor() is one line, not the end of the run."""
    found = []
    for c in [card] if card else _cards(desk_dir):
        try:
            lines = doctor(c, repos)
        except Exception as e:  # state.json and approvals errors are reported inside doctor; this is for its bugs
            lines = [f"could not check this card ({type(e).__name__}: {e}). Fix: report it as a doctor bug"]
        found += [(os.path.relpath(os.path.abspath(c), desk_dir), x) for x in lines]
    return found


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["list"]:
        print("\n".join(list_cards(a[1] if len(a) > 1 else os.path.join(worktree.BUREAU, "desk"))))
        sys.exit(0)
    if a[:1] == ["doctor"]:
        try:
            repos = worktree.read_repos(os.environ.get("BUREAU_REPOS", os.path.join(worktree.BUREAU, "repos.yaml")))
        except (OSError, ValueError):
            repos = {}  # every broken worktree then reports repos.yaml
        found = sweep(os.environ.get("BUREAU_DESK") or os.path.join(worktree.BUREAU, "desk"), a[1] if len(a) > 1 else None, repos)
        print("\n".join(f"{c}: {x}" for c, x in found) or "all cards healthy")
        sys.exit(1 if any(not x.startswith("fixed:") for _, x in found) else 0)
    try:
        cmd = {"init": lambda: init(a[1], json.loads(a[2])), "finish": lambda: finish(a[1]),
               "advance": lambda: advance(a[1]), "revise": lambda: revise(a[1], a[2]),
               "reject": lambda: reject(a[1], a[2], a[3]), "add": lambda: add(a[1], a[2], json.loads(a[3])),
               "skip": lambda: skip(a[1], a[2])}[a[0]]
    except (IndexError, KeyError):
        sys.exit(__doc__)
    try:
        out = cmd()
        if a[0] == "finish":
            print(next_block(a[1], out))
    except ValueError as e:
        sys.exit(f"error: {e}")
