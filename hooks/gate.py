#!/usr/bin/env python3
"""PreToolUse gate for desk worktrees.

Denies code writes inside desk/<card>/worktrees/<repo>/ unless
1. the card's current step may write code and every earlier gated step is approved
   (approvals.json, written only by approve.py), and
2. the repo's rule files were loaded through rules.py and have not changed since.
Subagent calls arrive with the same payload (plus agent_id), so they are covered too.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules

WT = rules.WT
ABS_WT = re.compile(r"(\S*?/desk/\S+?)/worktrees/([^/\s\"']+)")
REL_WT = re.compile(r"worktrees/([^/\s\"']+)")
READ_ONLY = re.compile(
    r"^\s*(ls|cat|rg|grep|head|tail|wc|pwd|cd|echo|git\s+(-C\s+\S+\s+)?(status|log|diff|show|grep|rev-parse|ls-files))\b"
    r"|^\s*python3?\s+\S*/hooks/rules\.py\b"  # the rules loader must run before any write is allowed
    r"|^\s*python3?\s+\S*/scripts/worktree\.py\b"  # creates the worktree itself
)
GIT = r"git\s+(-C\s+\S+\s+)?"
PR_CMD = re.compile(rf"^\s*(cd|{GIT}(add|commit|push)|gh\s+pr\s+create\b.*--draft)\b")
FORCE = re.compile(r"\s(-[a-zA-Z]*f[a-zA-Z]*|--force\S*)(\s|$)|\s\+\S")  # checked on push segments only
UNSAFE = re.compile(r"[>`]|\$\(")  # redirects and substitutions can write from a "read-only" command
HARMLESS_REDIRECT = re.compile(r"\d?>\s*/dev/null|\d?>&\d")


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def card_root(path):
    """Nearest ancestor holding a state.json."""
    d = os.path.abspath(path)
    while d != "/":
        if os.path.isfile(os.path.join(d, "state.json")):
            return d
        d = os.path.dirname(d)
    return None


def pr_allowed(cmd):
    """Once the last gate is approved the card is `done`; only commit, push and the draft PR may run."""
    segs = [s for s in re.split(r"[;|&\n]+", cmd) if s.strip()]
    return not UNSAFE.search(cmd) and all(
        PR_CMD.match(s) and not (re.match(rf"\s*{GIT}push\b", s) and FORCE.search(s)) for s in segs)


def check(card, repo, cmd=None):
    state = load(os.path.join(card, "state.json"))
    steps, current = state.get("steps", []), state.get("current")
    ids = [s["id"] for s in steps]
    approved = load(os.path.join(card, "approvals.json"))
    if current == "done" and steps and approved.get(ids[-1]):
        if cmd is None or not pr_allowed(cmd):
            deny("Card is done: only git add/commit/push (no force) and gh pr create --draft are allowed.")
        return
    if current not in ids:
        deny(f"No valid current step in {card}/state.json; start the run through /work.")
    idx = ids.index(current)
    if not steps[idx].get("writes_code"):
        deny(f"Step '{current}' does not write code. Move to a build step first.")
    for s in steps[:idx]:
        if s.get("gate", "none") != "none" and not approved.get(s["id"]):
            deny(f"Gate '{s['id']}' is not approved. Ask the user to run /approve before any code is written.")
    wt = os.path.join(card, "worktrees", repo)
    if load(os.path.join(card, "ack.json")).get(repo) != rules.digest(wt):
        deny(f"Repo rules for '{repo}' are not loaded or changed. Run: python3 {rules.BUREAU}/hooks/rules.py {wt}")


def read_only(cmd):
    cmd = HARMLESS_REDIRECT.sub("", cmd)
    segs = [s for s in re.split(r"[;|&\n]+", cmd) if s.strip()]
    return not UNSAFE.search(cmd) and all(READ_ONLY.match(s) for s in segs)


def bash_targets(cmd, cwd):
    out = set()
    m = WT.match(cwd + "/")
    if m:
        out.add((m["card"], m["repo"]))
    for m in ABS_WT.finditer(cmd):
        out.add((m[1].lstrip("\"'="), m[2]))
    base = card_root(cwd)
    if base:
        out.update((base, m[1]) for m in REL_WT.finditer(cmd))
    return out


def main():
    ev = json.load(sys.stdin)
    tool, inp = ev.get("tool_name"), ev.get("tool_input", {})
    if tool in ("Edit", "Write", "NotebookEdit"):
        path = os.path.abspath(inp.get("file_path") or inp.get("notebook_path") or "")
        if path.endswith("/approvals.json") and "/desk/" in path:
            deny("approvals.json is written only by the /approve hook.")
        m = WT.match(path)
        if m:
            check(m["card"], m["repo"])
    elif tool == "Bash":
        cmd = inp.get("command", "")
        if read_only(cmd):
            return
        if "approvals.json" in cmd:
            deny("approvals.json is written only by the /approve hook.")
        for card, repo in sorted(bash_targets(cmd, ev.get("cwd", ""))):
            check(card, repo, cmd)


if __name__ == "__main__":
    main()
