#!/usr/bin/env python3
"""Card state: create and read desk/<card>/state.json.

Usage: desk.py init <card-dir> '<steps-json>'
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


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "init":
        init(sys.argv[2], json.loads(sys.argv[3]))
    else:
        sys.exit(__doc__)
