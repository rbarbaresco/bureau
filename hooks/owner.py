#!/usr/bin/env python3
"""UserPromptSubmit hook: `/work <ref>` (or `/rework <ref>`) claims the card for this session.

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
    name = f"{m[1]}-{m[2]}" if m else ref
    card = os.path.join(sessions.DESK, name)
    ok = re.fullmatch(r"[\w.-]+", name) and name not in (".", "..")
    return card if ok and any(os.path.isfile(os.path.join(card, f)) for f in ("state.json", "card.md")) else None


def main():
    ev = json.load(sys.stdin)
    m = re.match(r"\s*/(?:re)?work\s+(\S+)", ev.get("prompt", ""))
    card = m and resolve(m[1])
    if not card:
        return
    sid, e = ev.get("session_id"), sessions.last(card)
    st = sessions.status(card, sid)
    if st == "mine":
        sessions.refresh(card, sid)
        return
    held = f"{os.path.basename(card)} is held by live session %s (pid %s, since %s). Close that session first; there is no override."
    if st == "held":
        block(held % (e["session"], e["pid"], e["at"]))
    why = "new" if e is None else "owner-dead" if e["event"] == "claim" else "owner-ended"
    pid = sessions.my_pid()
    if not sessions.claim(card, sid, pid, e, why=why, prev=e and e["session"]):  # lost a race for the same free card
        e = sessions.last(card)
        block(held % (e["session"], e["pid"], e["at"]))
    if not pid:
        print("Warning: could not find the claude process, so this card will not lock against other sessions.")
    if e:
        past = {x["session"] for x in sessions.events(card)} - {sid}
        print(f"Took over {os.path.basename(card)} from session {e['session']} "
              f"({'ended cleanly' if why == 'owner-ended' else 'died, pid gone'}). "
              f"{len(past)} past session{'s' * (len(past) != 1)} on this card; log: {card}/sessions.jsonl")


if __name__ == "__main__":
    main()
