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

import sessions

DESK = sessions.DESK


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def main():
    ev = json.load(sys.stdin)
    m = re.match(r"\s*/approve\b\s*(\S*)", ev.get("prompt", ""))
    if not m:
        return
    want = m[1]
    cards = []
    for p in glob.glob(os.path.join(DESK, "**", "state.json"), recursive=True):
        with open(p) as f:
            state = json.load(f)
        card = os.path.dirname(p)
        # a bare /approve means this session's card; an explicit id is the human's word
        if state.get("awaiting") and (os.path.basename(card) == want if want else sessions.status(card, ev.get("session_id")) == "mine"):
            cards.append((card, state))
    if len(cards) != 1:
        block(f"/approve needs exactly one awaiting card owned by this session; found {len(cards)}. Use /approve <card-id>.")
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
