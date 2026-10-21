#!/usr/bin/env python3
"""UserPromptSubmit hook: records `/approve [card-id]` from the human's own prompt.

The agent never sees this as a tool call, so it cannot approve its own gate.
Marks the card's `awaiting` step as approved in approvals.json.
"""
import glob
import json
import os
import re
import sys

# BUREAU_DESK lets tests point at a temp desk; the agent cannot set env for a hook.
DESK = os.environ.get("BUREAU_DESK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desk")


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main():
    m = re.match(r"\s*/approve\b\s*(\S*)", json.load(sys.stdin).get("prompt", ""))
    if not m:
        return
    want = m[1]
    cards = []
    for p in glob.glob(os.path.join(DESK, "**", "state.json"), recursive=True):
        with open(p) as f:
            state = json.load(f)
        if state.get("awaiting") and (not want or os.path.basename(os.path.dirname(p)) == want):
            cards.append((os.path.dirname(p), state))
    if len(cards) != 1:
        block(f"/approve needs exactly one card awaiting approval; found {len(cards)}. Use /approve <card-id>.")
    card, state = cards[0]
    path = os.path.join(card, "approvals.json")
    try:
        with open(path) as f:
            approved = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        approved = {}
    approved[state["awaiting"]] = True
    with open(path, "w") as f:
        json.dump(approved, f, indent=2)
    card_id = os.path.basename(card)
    print(f"Human approved step '{state['awaiting']}' of {card_id} (recorded in approvals.json). card={card_id}")


if __name__ == "__main__":
    main()
