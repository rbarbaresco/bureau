#!/usr/bin/env python3
"""SessionEnd hook: frees every card this session owns by appending an `end` event."""
import json
import sys

import sessions


def main():
    sid = json.load(sys.stdin).get("session_id")
    for card in sessions.cards():
        e = sessions.last(card)
        if e and e["event"] == "claim" and e["session"] == sid:
            sessions.append(card, "end", sid, e["pid"])


if __name__ == "__main__":
    main()
