#!/usr/bin/env python3
"""PreToolUse gate for desk worktrees.

Denies code writes inside desk/<card>/worktrees/<repo>/ unless
1. the card's current step may write code and every earlier gated step is approved
   (approvals.json, written only by approve.py), and
2. the repo's rule files were loaded through rules.py and have not changed since, and
3. the card is not owned by another session (sessions.py); desk.py state commands obey the same owner check,
   except `list`, `init` and a lone `doctor` (its only write is git's worktree link repair).
Subagent calls arrive with the same payload (plus agent_id), so they are covered too.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import rules
import sessions
import worktree

WT = rules.WT
ABS_WT = re.compile(r"(\S*?/desk/\S+?)/worktrees/([^/\s\"';|&)]+)")  # a repo name ends at a shell separator
REL_WT = re.compile(r"worktrees/([^/\s\"';|&)]+)")
GIT_C = r"""(-C\s+("?\$(\w+|\{\w+\})"?|[^\s{$]+)\s+)?"""  # a dir, not a brace list: -C {.,commit} log commits
SED_ADDR = r"(\d+|\$|/(?:[^/\\']|\\.)*/)"
OPERAND = r"\s+['\"]?[\w./~$]\S*"  # a file, never a literal option: not -i, '-i', ''-i or {-i,} ($X: README limits)
READ_ONLY = re.compile(
    r"^\s*(ls|cat|rg|grep|head|tail|wc|pwd|cd|echo|cut|tr|nl|diff|jq|sort|find|gh\s+pr\s+(view|diff|checks)"
    rf"|git\s+{GIT_C}(status|log|diff|show|grep|rev-parse|ls-files|merge-base|blame|cat-file|fetch|worktree\s+list))\b"
    rf"|^\s*git\s+{GIT_C}branch(\s+(-[arlv]|-vv|--(all|remotes|list|verbose|show-current)"
    r"|--(contains|merged|no-merged|points-at)((=|\s+)[\w./~^@]\S*)?))*\s*$"  # listing only: a name creates a branch
    rf"|^\s*sed\s+-n\s+('{SED_ADDR}(,{SED_ADDR})?p'|\d+(,\d+)?p)({OPERAND})*\s*$"  # print-only; bash expands a bare $
    rf"|^\s*awk(\s+-[Fv]\s*\S+)*\s+'(?![^']*(system|getline))[^'>|@]*'({OPERAND})*\s*$"  # no output, pipe, command, @include
    rf"|^\s*uniq(\s+-[\w-]*\w)*({OPERAND})?\s*$"  # a second operand is the output file
    r"|^\s*[A-Za-z_]\w*=(?:'[^']*'|\"[^\"]*\"|[^\s'\"])*\s*$"  # a lone `X=/path` segment
    r"|^\s*python3?\s+\S*/hooks/rules\.py\b"  # the rules loader must run before any write is allowed
    r"|^\s*python3?\s+\S*/scripts/worktree\.py\b"  # creates the worktree itself
)
WRITES = re.compile(  # write options of commands READ_ONLY allows by name
    r"^\s*find\b.*(?<![\w-])-(exec|ok|delete|fprint|fls)"
    r"|^\s*sort\b.*(?<![\w-])(-[a-zA-Z]*o|--[oc])"
    rf"|^\s*git\s+{GIT_C}fetch\b.*(:|--[us]|(?<![\w-])-u)"  # a:b, --stdin and --set-upstream write; --upload-pack runs
)
UNSAFE = re.compile(  # redirects and substitutions can write from a "read-only" command; on plain() text
    r"[>`]|[$<]\(|(?<!<)<<(?!<)|\$'")  # a heredoc body has no quoting to mask; $'…' can spell an option
QUOTED = re.compile(  # what bash reads as one inert unit, scanned left to right: \x, $'…', '…', "…", a # comment
    r"""\\.|\$'(?:[^'\\]|\\.)*'|\$"(?:[^"\\]|\\.)*"|'[^']*'|"(?:[^"\\]|\\.)*"|(?<![^\s;|&(])#[^\n]*""")
OPTION_CMD = re.compile(rf"^\s*(find|sort|sed|awk|uniq|git\s+{GIT_C}(fetch|branch))\b")  # options that write
WORD_VAR = re.compile(r"""(?:(?<=\s)|(?<=\s"))\$(\w+|\{\w+\})""")  # $X at a word's start: not "-de"$X, $@, ${X:--i}
BRACES = re.compile(r"\{[^}\s]*(,|\.\.)[^}\s]*\}")  # -{delete,print} spells an option; ${X} and @{1} do not
HARMLESS_REDIRECT = re.compile(r"\d?>\s*/dev/null|\d?>&\d")


def segments(cmd):
    """The commands of a chain: split on ; | & and newlines outside quotes, so `grep "a\\|b"` stays one."""
    mask = QUOTED.sub(lambda m: "_" * len(m[0]), cmd)
    out, start = [], 0
    for m in re.finditer(r"[;|&\n]+", mask):
        out.append(cmd[start:m.start()])
        start = m.end()
    return [s for s in out + [cmd[start:]] if s.strip()]


def reads(seg):
    if OPTION_CMD.match(seg) and (  # expansions can spell an option there; a $X starting a word is the README's limit
            "$" in WORD_VAR.sub("", QUOTED.sub(lambda m: m[0] if m[0][0] == '"' else "_", seg))
            or BRACES.search(QUOTED.sub("_", seg)) or re.search(r"(?<!\S)~[-+\d]", seg)):  # ~-, ~+, ~0 are $OLDPWD/$PWD in bash
        return False
    return READ_ONLY.match(seg) and not WRITES.match(re.sub(r"[\\'\"]", "", seg))  # -de""lete is -delete


def plain(cmd):
    """Drop what is inert: quoted, escaped and commented text, but keep "…" bodies ($( and backticks still run there)."""
    return QUOTED.sub(lambda m: re.sub(r"[<>]", "", m[0]) if m[0][0] == '"' else "$'" if m[0][:2] in ("$'", '$"') else "''", cmd)


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


def test_allowed(cmd, repo):
    """A non-writing step may also run the repo's `test:` command from repos.yaml, so a reviewer can run the suite."""
    try:
        prefix = worktree.read_repos(os.environ.get("BUREAU_REPOS", os.path.join(rules.BUREAU, "repos.yaml")))[repo]["test"]
    except (OSError, KeyError, ValueError):  # a missing or unreadable file denies; ValueError covers bad encoding
        return False
    if not prefix.strip():  # an empty prefix would match every segment
        return False
    cmd = HARMLESS_REDIRECT.sub("", cmd)
    return not UNSAFE.search(plain(cmd)) and all(
        reads(s) or re.match(rf"\s*{re.escape(prefix)}(\s|$)", s) for s in segments(cmd))


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
    if current == "done":
        deny("Card is done: no more code changes. Open the PR with scripts/pr.py (pr-review cards: scripts/reply.py; peer-review: scripts/post_review.py).")
    if not os.path.exists(os.path.join(card, "state.json")):
        deny(f"{card} has no workflow yet (intake is not finished). Confirm a workflow with the user, then run: "
             f"python3 {rules.BUREAU}/scripts/workflow.py start <name> {card}")
    if current not in ids:
        deny(f"Current step '{current}' in {card}/state.json is not one of its steps, or the file is unreadable. "
             f"If it lists steps: python3 {rules.BUREAU}/scripts/desk.py reject {card} <step> '<reason>'; else fix the file by hand.")
    idx = ids.index(current)
    if not steps[idx].get("writes_code"):
        if cmd is not None and test_allowed(cmd, repo):
            return
        deny(f"Step '{current}' does not write code. Move to a build step first.")
    for s in steps[:idx]:
        if s.get("gate", "none") != "none" and not approved.get(s["id"]):
            deny(f"Gate '{s['id']}' is not approved. Ask the user to run /approve before any code is written.")
        if s.get("loop") and approved.get(s["id"]) != "done":  # a round's `true` is not the end of the loop
            deny(f"Loop '{s['id']}' has not ended. Only the user ends it, with /approve done.")
    wt = os.path.join(card, "worktrees", repo)
    if not os.path.isdir(wt):  # a misparsed name would crash rules.digest, and a crashed hook allows the call
        deny(f"No worktree at {wt}. Create it with python3 {rules.BUREAU}/scripts/worktree.py {card} {repo}, "
             f"or, if it exists, name its path without quotes or punctuation around it.")
    if load(os.path.join(card, "ack.json")).get(repo) != rules.digest(wt):
        deny(f"Repo rules for '{repo}' are not loaded or changed. Run: python3 {rules.BUREAU}/hooks/rules.py {wt}")


DESK = re.compile(  # bare words and single-quoted text only: nothing for bash to expand, split or comment out
    r"[ \t]*python3?[ \t]+(?P<script>[\w./][\w./-]*)[ \t]+(?P<sub>init|list|doctor|finish|advance|revise|reject|add|skip|next)"
    r"(?:[ \t]+(?P<card>[\w./-]+)(?:[ \t]+(?:'[^']*'|[\w.-]+))*)?[ \t]*")
DESK_READS = ("list", "next")  # print card state, change nothing: read-only in a chain and on any session's card


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
    return not UNSAFE.search(plain(cmd)) and all(
        reads(s) or (desk_state(s, cwd) or ("",))[0] in DESK_READS for s in segments(cmd))


def bash_targets(cmd, cwd):
    out = set()
    m = WT.match(cwd + "/")
    if m:
        out.add((m["card"], m["repo"]))
    for m in ABS_WT.finditer(cmd):
        out.add((re.split(r"[=\"']", m[1])[-1], m[2]))  # the path after W= / --git-dir= / a quote
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
        if state_cmd and state_cmd[0] == "doctor":  # unowned cards are what it is for; it writes only git worktree links
            return
        if state_cmd and state_cmd[0] not in ("init", *DESK_READS):
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
