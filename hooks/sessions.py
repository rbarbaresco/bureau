"""Which session owns a card: desk/<card>/sessions.jsonl, append-only, written only by hooks.

One JSON line per event: {"event": "claim"|"end", "session", "pid", "at", ...}.
The owner is the session of the last event if that is a `claim`; an `end` leaves the card free.
The pid is the `claude` process above the hook: a claim whose pid is gone (crash) is free too.
"""
import fcntl
import glob
import json
import os
import time

# BUREAU_DESK and BUREAU_CLAUDE_PID let tests point at a temp desk and a stand-in process;
# the agent cannot set env for a hook.
DESK = os.environ.get("BUREAU_DESK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desk")
NAME = "claude"


def comm(pid):
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except OSError:
        return None


def my_pid():
    """The `claude` process above this hook (hooks run under sh)."""
    if os.environ.get("BUREAU_CLAUDE_PID"):
        return int(os.environ["BUREAU_CLAUDE_PID"])
    pid = os.getpid()
    while pid > 1:
        try:
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except OSError:
            return None
        if comm(pid) == NAME:
            return pid
    return None


def events(card):
    out = []
    try:
        with open(os.path.join(card, "sessions.jsonl")) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:  # a torn write must not turn every hook into a crash (fail-open)
                    continue
                if isinstance(e, dict) and "event" in e:
                    out.append(e)
    except FileNotFoundError:
        pass
    return out


def last(card):
    ev = events(card)
    return ev[-1] if ev else None


def append(card, event, session, pid, **extra):
    os.makedirs(card, exist_ok=True)
    rec = {"event": event, "session": session, "pid": pid, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **extra}
    with open(os.path.join(card, "sessions.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")


def claim(card, session, pid, seen, **extra):
    """Claim unless the log moved since `seen` (another session got there first). True if the claim was made."""
    os.makedirs(card, exist_ok=True)
    with open(os.path.join(card, "sessions.lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if last(card) != seen:
            return False
        append(card, "claim", session, pid, **extra)
        return True


def status(card, session):
    """none (never claimed: open to all), mine, held (another live session), free (ended or dead owner)."""
    e = last(card)
    if e is None:
        return "none"
    if e["event"] == "claim":
        if e["session"] == session:
            return "mine"
        if comm(e["pid"]) == NAME:
            return "held"
    return "free"


def refresh(card, session):
    """The owner came back under a new process (resume): log it, so the old pid's death does not free the card."""
    pid = my_pid()
    if pid and last(card)["pid"] != pid:
        append(card, "claim", session, pid, why="resume")


def cards():
    return [os.path.dirname(p) for p in glob.glob(os.path.join(DESK, "**", "sessions.jsonl"), recursive=True)]
