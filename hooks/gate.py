#!/usr/bin/env python3
"""PreToolUse gate for desk worktrees.

Denies code writes inside desk/<card>/worktrees/<repo>/ unless
1. the card's current step may write code and every earlier gated step is approved
   (approvals.json, written only by approve.py), and
2. the repo's rule files were loaded through rules.py and have not changed since, and
3. the card is not owned by another session (sessions.py); desk.py state commands obey the same owner check.
Subagent calls arrive with the same payload (plus agent_id), so they are covered too.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import rules
import sessions
import worktree

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
QUOTED = re.compile(r"""'[^']*'|"(?:[^"\\]|\\.)*\"""")
HARMLESS_REDIRECT = re.compile(r"\d?>\s*/dev/null|\d?>&\d")


def plain(cmd):
    """Drop what is inert in quotes: single-quoted text, and <> in double quotes ($( and backticks still run there)."""
    return QUOTED.sub(lambda m: "''" if m[0][0] == "'" else re.sub(r"[<>]", "", m[0]), cmd)


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
    """Nearest ancestor holding a state.json (or, for a card still in intake, a session log)."""
    d = os.path.abspath(path)
    while d != "/":
        if os.path.isfile(os.path.join(d, "state.json")) or os.path.isfile(os.path.join(d, "sessions.jsonl")):
            return d
        d = os.path.dirname(d)
    return None


def pr_allowed(cmd):
    """Once the last gate is approved the card is `done`; only commit, push and the draft PR may run."""
    segs = [s for s in re.split(r"[;|&\n]+", cmd) if s.strip()]
    return not UNSAFE.search(plain(cmd)) and all(
        PR_CMD.match(s) and not (re.match(rf"\s*{GIT}push\b", s) and FORCE.search(s)) for s in segs)


def test_allowed(cmd, repo):
    """A non-writing step may also run the repo's `test:` command from repos.yaml, so a reviewer can run the suite."""
    try:
        prefix = worktree.read_repos(os.environ.get("BUREAU_REPOS", os.path.join(rules.BUREAU, "repos.yaml")))[repo]["test"]
    except (OSError, KeyError):
        return False
    cmd = HARMLESS_REDIRECT.sub("", cmd)
    segs = [s for s in re.split(r"[;|&\n]+", cmd) if s.strip()]
    return not UNSAFE.search(plain(cmd)) and all(
        READ_ONLY.match(s) or re.match(rf"\s*{re.escape(prefix)}(\s|$)", s) for s in segs)


def owner(card, session):
    """A card with a session log belongs to the session of its last claim; the first call of a resumed owner is logged."""
    st = sessions.status(card, session)
    if st == "mine":
        sessions.refresh(card, session)
    elif st != "none":
        e, name = sessions.last(card), os.path.basename(card)
        deny(f"Card {name} is held by session {e['session']} (pid {e['pid']}); close it first." if st == "held"
             else f"Card {name} has no live owner session. Run /work {name} to take over.")


def check(card, repo, session, cmd=None):
    owner(card, session)
    state = load(os.path.join(card, "state.json"))
    steps, current = state.get("steps", []), state.get("current")
    ids = [s["id"] for s in steps]
    approved = load(os.path.join(card, "approvals.json"))
    if current == "done" and steps and approved.get(ids[-1]):
        if cmd is None or not pr_allowed(cmd):
            deny("Card is done: only git add/commit/push (no force) and gh pr create --draft are allowed.")
        if re.search(rf"(^|[;|&\n])\s*({GIT}push|gh\s+pr\s+create)\b", cmd):
            st = subprocess.run(["git", "-C", os.path.join(card, "worktrees", repo), "status", "--porcelain"],
                                capture_output=True, text=True)
            if st.returncode or st.stdout.strip():  # a failed status counts as dirty
                deny("Uncommitted changes in the worktree: commit first, then push or open the PR in a separate call.")
        return
    if current not in ids:
        deny(f"No valid current step in {card}/state.json; start the run through /work.")
    idx = ids.index(current)
    if not steps[idx].get("writes_code"):
        if cmd is not None and test_allowed(cmd, repo):
            return
        deny(f"Step '{current}' does not write code. Move to a build step first.")
    for s in steps[:idx]:
        if s.get("gate", "none") != "none" and not approved.get(s["id"]):
            deny(f"Gate '{s['id']}' is not approved. Ask the user to run /approve before any code is written.")
    wt = os.path.join(card, "worktrees", repo)
    if load(os.path.join(card, "ack.json")).get(repo) != rules.digest(wt):
        deny(f"Repo rules for '{repo}' are not loaded or changed. Run: python3 {rules.BUREAU}/hooks/rules.py {wt}")


DESK = re.compile(  # bare words and single-quoted text only: nothing for bash to expand, split or comment out
    r"[ \t]*python3?[ \t]+(?P<script>[\w./][\w./-]*)[ \t]+(?P<sub>init|list|finish|advance|revise|reject|add|skip)"
    r"(?:[ \t]+(?P<card>[\w./-]+)(?:[ \t]+(?:'[^']*'|[\w.-]+))*)?[ \t]*")


def desk_state(cmd, cwd):
    """One invocation of Bureau's own desk.py (by real path) on a card path outside any worktree: card state only.
    Returns (subcommand, card dir), or None."""
    m = DESK.fullmatch(cmd)
    if not m:
        return None
    if os.path.realpath(os.path.join(cwd, m["script"])) != os.path.join(os.path.realpath(rules.BUREAU), "scripts", "desk.py"):
        return None
    card = os.path.realpath(os.path.join(cwd, m["card"] or ""))
    return None if WT.match(card + "/") else (m["sub"], card)


NEW = re.compile(  # the whole command, bare words and single-quoted text only: a mention in echo/grep/git is not a start
    r"[ \t]*python3?[ \t]+(?P<script>[\w./][\w./-]*)[ \t]+(?:start[ \t]+[\w./-]+|init)[ \t]+(?P<card>[\w./-]+)"
    r"(?:[ \t]+(?:'[^']*'|[\w.-]+))*[ \t]*")
CARD_REF = re.compile(r"(?<![\w.-])(?:[\w./~-]*/)?desk/[\w.-]+")  # after > = ' ( too, not only after a space


def claim_new(cmd, cwd, session):
    """The session that creates a card (Bureau's own workflow.py start / desk.py init, no state.json yet) owns it."""
    m = NEW.fullmatch(cmd)
    if not m:
        return
    script = os.path.realpath(os.path.join(cwd, m["script"]))
    card = os.path.realpath(os.path.join(cwd, m["card"]))
    scripts = os.path.join(os.path.realpath(rules.BUREAU), "scripts")
    if script in (os.path.join(scripts, "workflow.py"), os.path.join(scripts, "desk.py")) \
            and "/desk/" in card and not os.path.exists(os.path.join(card, "state.json")) and sessions.last(card) is None:
        sessions.claim(card, session, sessions.my_pid(), None, why="new")


def claim_intake(path, session):
    """Intake writes desk/<id>/card.md first: the session that does it owns the card (no state.json, no log yet)."""
    card = os.path.dirname(path)
    if os.path.basename(path) == "card.md" and os.path.basename(os.path.dirname(card)) == "desk" \
            and not os.path.exists(os.path.join(card, "state.json")) and sessions.last(card) is None:
        sessions.claim(card, session, sessions.my_pid(), None, why="new")


def named_cards(cmd, cwd):
    """Card dirs a command names by path (desk/<id>, however quoted or chained)."""
    return {os.path.realpath(os.path.join(cwd, m[0])) for m in CARD_REF.finditer(cmd)}


def read_only(cmd, cwd=""):
    if desk_state(cmd, cwd):
        return True
    cmd = HARMLESS_REDIRECT.sub("", cmd)
    segs = [s for s in re.split(r"[;|&\n]+", cmd) if s.strip()]
    return not UNSAFE.search(plain(cmd)) and all(READ_ONLY.match(s) for s in segs)


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
    session = ev.get("session_id")
    tool, inp = ev.get("tool_name"), ev.get("tool_input", {})
    if tool in ("Edit", "Write", "NotebookEdit"):
        path = os.path.abspath(inp.get("file_path") or inp.get("notebook_path") or "")
        claim_intake(path, session)
        if card_root(os.path.dirname(path)):
            owner(card_root(os.path.dirname(path)), session)
        if path.endswith("/approvals.json") and "/desk/" in path:
            deny("approvals.json is written only by the /approve hook.")
        if path.endswith("/sessions.jsonl") and "/desk/" in path:
            deny("sessions.jsonl is written only by the session hooks.")
        m = WT.match(path)
        if m:
            check(m["card"], m["repo"], session)
    elif tool == "Bash":
        cmd, cwd = inp.get("command", ""), ev.get("cwd", "")
        claim_new(cmd, cwd, session)
        state_cmd = desk_state(cmd, cwd)
        if state_cmd and state_cmd[0] not in ("list", "init"):
            for card in sorted({state_cmd[1]} | named_cards(cmd, cwd)):  # "." and desk/<id>/sub both mean a card
                owner(card, session)
        if read_only(cmd, cwd):
            return
        for card in sorted(named_cards(cmd, cwd)):  # any other command naming a card (sed -i state.json, && chains, quotes)
            owner(card, session)
        if "approvals.json" in cmd or "sessions.jsonl" in cmd:
            deny("approvals.json is written only by the /approve hook; sessions.jsonl only by the session hooks.")
        for card, repo in sorted(bash_targets(cmd, cwd)):
            check(card, repo, session, cmd)


if __name__ == "__main__":
    main()
