import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# commands name LINK, not ROOT: in a card worktree ROOT holds desk/<card>, which the gate owner-checks
LINK = os.path.join(tempfile.mkdtemp(), "bureau")
os.symlink(ROOT, LINK)
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import rules  # noqa: E402
import sessions  # noqa: E402

GATE = os.path.join(ROOT, "hooks", "gate.py")
APPROVE = os.path.join(ROOT, "hooks", "approve.py")
STEPS = [
    {"id": "plan", "gate": "approve"},
    {"id": "build", "gate": "approve", "writes_code": True},
]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # ancestor/ (AGENTS.md) / clone (CLAUDE.md @imports extra.md) ; worktree under desk
        self.clone = os.path.join(self.tmp, "ancestor", "clone")
        write(os.path.join(self.tmp, "ancestor", "AGENTS.md"), "ancestor rule\n")
        write(os.path.join(self.clone, "CLAUDE.md"), "clone rule\n@extra.md\n")
        write(os.path.join(self.clone, "extra.md"), "imported rule\n")
        self.card = os.path.join(self.tmp, "desk", "ABC-1")
        self.wt = os.path.join(self.card, "worktrees", "clone")
        write(os.path.join(self.wt, "CLAUDE.md"), "clone rule\n@extra.md\n")
        write(os.path.join(self.wt, "extra.md"), "imported rule\n")
        write(os.path.join(self.wt, ".git"), f"gitdir: {self.clone}/.git/worktrees/ABC-1\n")
        self.state({"current": "build", "steps": STEPS})

    def state(self, s):
        write(os.path.join(self.card, "state.json"), json.dumps(s))

    def approve(self, *ids):
        write(os.path.join(self.card, "approvals.json"), json.dumps({i: True for i in ids}))

    def ack(self):
        subprocess.run([sys.executable, os.path.join(ROOT, "hooks", "rules.py"), self.wt],
                       check=True, capture_output=True)

    def run_gate(self, tool, cwd=None, **inp):
        payload = {"tool_name": tool, "tool_input": inp, "cwd": cwd or self.card}
        out = subprocess.run([sys.executable, GATE], input=json.dumps(payload),
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else None

    def edit(self):
        return self.run_gate("Edit", file_path=os.path.join(self.wt, "app.py"))

    def test_denied_without_approval(self):
        self.ack()
        self.assertIn("'plan' is not approved", self.edit())

    def test_denied_without_ack(self):
        self.approve("plan")
        self.assertIn("rules.py", self.edit())

    def test_allowed_when_approved_and_acked(self):
        self.approve("plan")
        self.ack()
        self.assertIsNone(self.edit())

    def test_stale_ack_after_rule_change(self):
        self.approve("plan")
        self.ack()
        write(os.path.join(self.wt, "extra.md"), "changed rule\n")
        self.assertIn("changed", self.edit())

    def test_non_build_step_denied(self):
        self.state({"current": "plan", "steps": STEPS})
        self.approve("plan")
        self.ack()
        self.assertIn("does not write code", self.edit())

    def test_declared_test_command_allowed_on_non_build_step(self):
        self.state({"current": "plan", "steps": STEPS})
        repos = os.path.join(self.tmp, "repos.yaml")
        write(repos, "repos:\n  clone:\n    path: x\n    test: python3 -I -m unittest\n  other:\n    path: y\n")
        run = f"cd {self.wt} && python3 -I -m unittest discover -s tests 2>&1 | tail -3"
        self.assertIn("does not write code", self.run_gate("Bash", command=run))  # no repos file: today's behaviour
        with mock.patch.dict(os.environ, {"BUREAU_REPOS": repos}):
            self.assertIsNone(self.run_gate("Bash", command=run))
            self.assertIsNone(self.run_gate("Bash", command="python3 -I -m unittest", cwd=self.wt))
            for bad in (f"{run} && rm -rf x", f"{run} > out.txt", f"cd {self.wt} && python3 -I -m unittest $(id)",
                        f"cd {self.wt} && python3 -I -m unittestx", f"cd {self.wt} && python3 other.py"):
                self.assertIn("does not write code", self.run_gate("Bash", command=bad), bad)
            self.assertIn("does not write code", self.run_gate("Edit", file_path=os.path.join(self.wt, "app.py")))
            write(repos, "repos:\n  clone:\n    path: x\n")  # repo without a test: key
            self.assertIn("does not write code", self.run_gate("Bash", command=run))
            write(repos, "repos:\n  clone:\n    path: x\n    test:\n")  # empty value must not match every segment
            self.assertIn("does not write code", self.run_gate("Bash", command=f"cd {self.wt} && rm -rf x"))

    def test_path_outside_worktree_allowed(self):
        self.assertIsNone(self.run_gate("Write", file_path=os.path.join(self.card, "plan.md")))

    def test_agent_cannot_write_approvals(self):
        self.assertIn("approve hook", self.run_gate("Write", file_path=os.path.join(self.card, "approvals.json")))
        self.assertIn("approve hook", self.run_gate("Bash", command=f"echo '{{}}' > {self.card}/approvals.json"))

    def test_bash_write_denied_read_only_allowed(self):
        self.assertIsNotNone(self.run_gate("Bash", command=f"sed -i s/a/b/ {self.wt}/app.py"))
        self.assertIsNotNone(self.run_gate("Bash", command=f"cat {self.wt}/a > {self.wt}/b"))
        self.assertIsNotNone(self.run_gate("Bash", command="cd worktrees/clone && touch x"))
        self.assertIsNone(self.run_gate("Bash", command=f"ls {self.wt} && git -C {self.wt} status"))
        self.assertIsNone(self.run_gate("Bash", command="rg foo worktrees/clone"))
        self.assertIsNone(self.run_gate("Bash", command="rg foo worktrees/clone 2>/dev/null | head -5"))
        self.assertIsNone(self.run_gate("Bash", command="grep -rn foo worktrees/clone 2>&1"))
        self.assertIsNotNone(self.run_gate("Bash", command="cat a >/dev/null; touch worktrees/clone/x"))

    def test_done_card_denies_code_changes(self):
        self.state({"current": "done", "steps": STEPS})
        self.approve("plan", "build")
        self.assertIn("Card is done", self.edit())
        self.assertIn("Card is done", self.run_gate("Bash", command=f"cd {self.wt} && git push origin b"))

    def test_read_only_quoted_text(self):
        self.assertIsNone(self.run_gate("Bash", command=f"rg 'a>b' \"<c>\" {self.wt}"))
        self.assertIsNotNone(self.run_gate("Bash", command=f"echo x > {self.wt}/f"))
        self.assertIsNotNone(self.run_gate("Bash", command=f'echo "$(touch {self.wt}/f)"'))

    def test_git_grep_allowed_on_read_only_step(self):
        self.state({"current": "plan", "steps": STEPS})
        self.assertIsNone(self.run_gate("Bash", command=f"git -C {self.wt} grep foo"))

    def test_desk_state_commands_allowed_from_worktree_cwd(self):
        self.state({"current": "plan", "steps": STEPS})
        desk = f"python3 {LINK}/scripts/desk.py"
        run = lambda c: self.run_gate("Bash", cwd=self.wt, command=c)
        self.assertIsNone(run(f"{desk} finish {self.card}"))
        self.assertIsNone(run(f"{desk} reject {self.card} plan 'redo'"))
        self.assertIsNotNone(run(f"{desk} finish {self.card}; touch {self.wt}/x"))
        self.assertIsNotNone(run(f"{desk} finish {self.card} > {self.wt}/x"))
        self.assertIsNotNone(run(f"{desk} init {self.wt}/sub '[]'"))  # argument points into a worktree
        self.assertIsNone(run(f"{desk} reject {self.card} plan 'redo; see worktrees/x & more'"))  # free text
        self.assertIsNotNone(run(f"{desk} init . '[]'"))  # "." is the worktree
        self.assertIsNotNone(run(f"{desk} finish $PWD"))
        self.assertIsNotNone(run(f"{desk} finish {self.card}\ntouch {self.wt}/x"))  # newline = second command
        self.assertIsNotNone(run(f"{desk} finish c# ; touch {self.wt}/x"))  # mid-word # is not a comment
        self.assertIsNotNone(run(f"{desk} init {{{self.wt}/x,y}} '[]'"))  # brace expansion
        self.assertIsNotNone(run(f"{desk} finish {self.card[:-1]}?"))  # glob
        self.assertIsNone(self.run_gate("Bash", cwd=ROOT, command=f"python3 scripts/desk.py finish {self.card}"))
        self.assertIsNotNone(run(f'{desk} reject {self.card} plan "$(touch {self.wt}/x)"'))
        self.assertIsNotNone(run(f"{desk} revise {self.card} `touch {self.wt}/x`"))
        self.assertIsNotNone(run(f"{desk} $UNSET init {self.wt}/sub '[]'"))  # shifts the card argument
        self.assertIsNone(run(f"{desk} revise {self.card} 'line1\nline2'"))  # newline inside quotes is inert
        self.assertIsNotNone(run(f"{desk} list /c #'\ntouch {self.wt}/x #'"))  # comment hides a quote pair
        self.assertIsNotNone(run(f"python3 -Wx/../scripts/desk.py list {self.card}"))  # python option, not the script
        other = os.path.join(self.tmp, "other", "scripts", "desk.py")  # unrelated project's desk.py
        write(other, "")
        self.assertIsNotNone(run(f"python3 {other} finish {self.card}"))

    def test_rules_loader_runs_before_ack(self):
        cmd = f"python3 {LINK}/hooks/rules.py {self.wt}"
        self.assertIsNone(self.run_gate("Bash", command=cmd))

    def test_subagent_call_gated_too(self):
        payload = {"tool_name": "Edit", "agent_id": "a1", "cwd": self.card,
                   "tool_input": {"file_path": os.path.join(self.wt, "app.py")}}
        out = subprocess.run([sys.executable, GATE], input=json.dumps(payload),
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("deny", out)

    def test_resolver_collects_ancestors_and_imports(self):
        names = [os.path.relpath(p, self.tmp) for p in rules.collect(self.wt) if p.startswith(self.tmp)]
        self.assertIn("ancestor/AGENTS.md", names)
        self.assertTrue(any(n.endswith("clone/extra.md") for n in names))

    def test_resolver_includes_bureau_base_rules(self):
        self.assertIn(os.path.join(ROOT, "AGENTS.md"), rules.collect(self.wt))

    def test_approve_hook_records_awaiting_step(self):
        desk = os.path.join(self.tmp, "desk")  # setUp's ABC-1 is not awaiting, so only TEST-APPROVE matches
        card = os.path.join(desk, "TEST-APPROVE")
        write(os.path.join(card, "state.json"), json.dumps({"awaiting": "plan", "steps": STEPS}))
        env = {**os.environ, "BUREAU_DESK": desk}
        sessions.append(card, "claim", "s1", os.getpid())  # bare /approve needs the caller to own the card
        run = lambda prompt: subprocess.run([sys.executable, APPROVE], input=json.dumps({"prompt": prompt, "session_id": "s1"}),
                                            capture_output=True, text=True, env=env).stdout
        self.assertEqual(run("hello"), "")
        for prompt in ("/approve TEST-APPROVE", "/approve"):
            out = run(prompt)
            self.assertIn("approved step 'plan'", out)
            self.assertIn("card=TEST-APPROVE", out.split())
        with open(os.path.join(card, "approvals.json")) as f:
            self.assertEqual(json.load(f), {"plan": True})


if __name__ == "__main__":
    unittest.main()
