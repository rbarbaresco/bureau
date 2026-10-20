#!/usr/bin/env python3
"""Card state: create and read desk/<card>/state.json.

Usage: desk.py init <card-dir> '<steps-json>'
       desk.py list [desk-dir]
       desk.py finish|advance <card-dir>
       desk.py revise <card-dir> '<feedback>'
       desk.py reject <card-dir> <to-step> '<reason>'
       desk.py add <card-dir> <after-step-id> '<step-json>' | skip <card-dir> <step-id>

finish: current step is done; a gated step then waits (`awaiting`) for the human's /approve.
advance: moves on once the awaiting step is approved (approvals.json is written only by the hook).
A step is {"id", "gate": none|approve|approve+check, "persona"?, "writes_code"?}.
"""
import json
import os
import sys

GATES = ("none", "approve", "approve+check")


def validate_steps(steps):
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    ids = []
    for s in steps:
        if not isinstance(s, dict) or not isinstance(s.get("id"), str) or not s["id"]:
            raise ValueError(f"step needs a string id: {s!r}")
        if s.get("gate", "none") not in GATES:
            raise ValueError(f"step '{s['id']}': gate must be one of {GATES}")
        ids.append(s["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate step ids")


def load(card_dir):
    with open(os.path.join(card_dir, "state.json")) as f:
        return json.load(f)


def save(card_dir, state):
    with open(os.path.join(card_dir, "state.json"), "w") as f:
        json.dump(state, f, indent=2)


def init(card_dir, steps, workflow=None):
    validate_steps(steps)
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


def _version(card_dir, name, ext=".md"):
    """Move <name>.md to <name>.v<N>.md so a redo keeps history."""
    cur = os.path.join(card_dir, name + ext)
    n = 1
    while os.path.exists(os.path.join(card_dir, f"{name}.v{n}{ext}")):
        n += 1
    if os.path.exists(cur):
        os.rename(cur, os.path.join(card_dir, f"{name}.v{n}{ext}"))
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


def advance(card_dir):
    s = load(card_dir)
    aw = s.get("awaiting")
    if not aw:
        raise ValueError("no step is awaiting approval")
    if not _approvals(card_dir).get(aw):
        raise ValueError(f"step '{aw}' is not approved; the human must run /approve")
    s["awaiting"] = None
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
    validate_steps(steps)
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


def list_cards(desk_dir):
    """One line per run, nested tasks included: path, workflow, current step, awaiting."""
    rows = []
    for root, _, files in os.walk(desk_dir):
        if "state.json" in files and "worktrees" not in os.path.relpath(root, desk_dir).split(os.sep):
            s = load(root)
            rows.append(f"{os.path.relpath(root, desk_dir)}\t{s.get('workflow')}\t{s['current']}\t{s.get('awaiting') or '-'}")
    return rows


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["list"]:
        print("\n".join(list_cards(a[1] if len(a) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desk"))))
        sys.exit(0)
    try:
        cmd = {"init": lambda: init(a[1], json.loads(a[2])), "finish": lambda: finish(a[1]),
               "advance": lambda: advance(a[1]), "revise": lambda: revise(a[1], a[2]),
               "reject": lambda: reject(a[1], a[2], a[3]), "add": lambda: add(a[1], a[2], json.loads(a[3])),
               "skip": lambda: skip(a[1], a[2])}[a[0]]
    except (IndexError, KeyError):
        sys.exit(__doc__)
    try:
        cmd()
    except ValueError as e:
        sys.exit(f"error: {e}")
