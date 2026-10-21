#!/usr/bin/env python3
"""UserPromptSubmit hook: `/work <ref>` claims the card for this session.

A card held by another live session is refused (no override). A free card, or one whose owner
ended or died, is taken over, and the new session is told about the past ones.
"""
import json
import os
import re
import sys

import sessions


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def resolve(ref):
    """Card dir of an existing card: its id, or owner/repo#n -> repo-n. Anything else is a new card, claimed at init."""
    m = re.fullmatch(r"(?:[\w.-]+/)?([\w.-]+)#(\d+)", ref)
    card = os.path.join(sessions.DESK, f"{m[1]}-{m[2]}" if m else ref)
    return card if os.path.isdir(card) else None


def main():
    ev = json.load(sys.stdin)
    m = re.match(r"\s*/work\s+(\S+)", ev.get("prompt", ""))
    card = m and resolve(m[1])
    if not card:
        return
    sid, e = ev.get("session_id"), sessions.last(card)
    st = sessions.status(card, sid)
    if st == "mine":
        return
    if st == "held":
        block(f"{os.path.basename(card)} is held by live session {e['session']} (pid {e['pid']}, since {e['at']}). "
              "Close that session first; there is no override.")
    why = "new" if e is None else "owner-dead" if e["event"] == "claim" else "owner-ended"
    sessions.append(card, "claim", sid, sessions.my_pid(), why=why, prev=e and e["session"])
    if e:
        past = {x["session"] for x in sessions.events(card)} - {sid}
        print(f"Took over {os.path.basename(card)} from session {e['session']} "
              f"({'ended cleanly' if why == 'owner-ended' else 'died, pid gone'}). "
              f"{len(past)} past session{'s' * (len(past) != 1)} on this card; log: {card}/sessions.jsonl")


if __name__ == "__main__":
    main()
