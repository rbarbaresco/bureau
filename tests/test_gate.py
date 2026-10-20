import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import rules  # noqa: E402

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

    def run_gate(self, tool, **inp):
        payload = {"tool_name": tool, "tool_input": inp, "cwd": self.card}
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

    def test_rules_loader_runs_before_ack(self):
        cmd = f"python3 {ROOT}/hooks/rules.py {self.wt}"
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
        self.state({"current": "plan", "awaiting": "plan", "steps": STEPS})
        desk = os.path.join(ROOT, "desk")
        card = os.path.join(desk, "TEST-APPROVE")
        write(os.path.join(card, "state.json"), json.dumps({"awaiting": "plan", "steps": STEPS}))
        try:
            run = lambda prompt: subprocess.run([sys.executable, APPROVE], input=json.dumps({"prompt": prompt}),
                                                capture_output=True, text=True).stdout
            self.assertEqual(run("hello"), "")
            self.assertIn("approved step 'plan'", run("/approve TEST-APPROVE"))
            with open(os.path.join(card, "approvals.json")) as f:
                self.assertEqual(json.load(f), {"plan": True})
        finally:
            subprocess.run(["rm", "-rf", card])


if __name__ == "__main__":
    unittest.main()
