#!/usr/bin/env bash
# End-to-end check with real `claude -p` runs against a throwaway Bureau copy:
#  A. a code write is refused while the repo rules are not loaded
#  B. after loading them, rules from the repo AND from an ancestor folder reach the model
#  C. a raw "/approve" prompt reaches the hook and is recorded
# Costs a few model calls. Re-run after any Claude Code upgrade.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
MODEL="${E2E_MODEL:-claude-haiku-5-5}"
fail() { echo "FAIL: $*" >&2; exit 1; }

# Bureau copy (hooks + settings + skills + base rules)
B="$T/bureau"; mkdir -p "$B"
cp -r "$SRC/hooks" "$SRC/.claude" "$SRC/AGENTS.md" "$B/"
mkdir -p "$B/desk"

# ancestor rule + repo rule
mkdir -p "$T/ancestor/clone"
echo 'Every file you create must start with the line "# CANARY-ANCESTOR".' > "$T/ancestor/AGENTS.md"
git -C "$T/ancestor/clone" init -q -b main
echo 'Every file you create must also contain the line "# CANARY-REPO".' > "$T/ancestor/clone/CLAUDE.md"
git -C "$T/ancestor/clone" add -A
git -C "$T/ancestor/clone" -c user.name=t -c user.email=t@t commit -q -m init

# card: build step, plan already approved
C="$B/desk/E2E"; mkdir -p "$C"
git -C "$T/ancestor/clone" worktree add -q "$C/worktrees/clone" -b e2e
echo '{"current":"build","steps":[{"id":"plan","gate":"approve"},{"id":"build","gate":"approve","writes_code":true}]}' > "$C/state.json"
echo '{"plan":true}' > "$C/approvals.json"
WT="$C/worktrees/clone"

run() { (cd "$B" && printf "%s" "$1" | claude -p --model "$MODEL" --allowedTools "Bash Read Edit Write" 2>&1); }

echo "A. write refused without loaded rules"
run "Create the file $WT/hello.txt containing 'hi' using the Write tool. Do not run any other command first. If it is blocked, say BLOCKED and stop." > "$T/a.out" || true
[ ! -e "$WT/hello.txt" ] || fail "A: file was written without rules ack"
grep -qi "blocked\|denied\|not loaded" "$T/a.out" || fail "A: no block reported: $(cat "$T/a.out")"

echo "B. rules from repo and ancestor reach the model"
run "Create $WT/hello.txt containing 'hi'. Follow the repo's rules; the Bureau AGENTS.md says how to load them." > "$T/b.out" || true
[ -e "$WT/hello.txt" ] || fail "B: file not created: $(cat "$T/b.out")"
grep -q "CANARY-ANCESTOR" "$WT/hello.txt" || fail "B: ancestor rule missing"
grep -q "CANARY-REPO" "$WT/hello.txt" || fail "B: repo rule missing"

echo "C. raw /approve reaches the hook"
rm "$C/approvals.json"
echo '{"awaiting":"plan","current":"plan","steps":[{"id":"plan","gate":"approve"},{"id":"build","gate":"approve","writes_code":true}]}' > "$C/state.json"
run "/approve E2E" > "$T/c.out" || true
grep -q '"plan": true' "$C/approvals.json" 2>/dev/null || fail "C: approval not recorded: $(cat "$T/c.out")"

echo "OK"
