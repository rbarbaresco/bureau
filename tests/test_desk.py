import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desk  # noqa: E402

STEPS = [{"id": "plan", "gate": "approve"}, {"id": "build", "gate": "approve", "writes_code": True}]


class DeskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clone = os.path.join(self.tmp, "clone")
        subprocess.run(["git", "init", "-q", "-b", "main", self.clone], check=True)
        subprocess.run(["git", "-C", self.clone, "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        self.repos = os.path.join(self.tmp, "repos.yaml")
        with open(self.repos, "w") as f:
            f.write(f"repos:\n  clone:\n    path: {self.clone}   # comment\n    base: main\n")
        self.card = os.path.join(self.tmp, "desk", "ABC-1")

    def test_init_writes_valid_state(self):
        desk.init(self.card, STEPS, "bugfix")
        s = desk.load(self.card)
        self.assertEqual((s["card"], s["current"], s["workflow"]), ("ABC-1", "plan", "bugfix"))
        with self.assertRaises(FileExistsError):
            desk.init(self.card, STEPS)

    def test_invalid_steps_rejected(self):
        for bad in ([], [{"id": "a"}, {"id": "a"}], [{"id": "a", "gate": "maybe"}], [{"gate": "none"}]):
            with self.assertRaises(ValueError):
                desk.validate_steps(bad)

    def test_worktree_then_gate_allows_edit_after_approve_and_ack(self):
        desk.init(self.card, STEPS)
        wt = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "worktree.py"), self.card, "clone",
                             "--repos", self.repos], check=True, capture_output=True, text=True).stdout.strip().splitlines()[-1]
        self.assertTrue(os.path.isfile(os.path.join(wt, ".git")))
        s = desk.load(self.card)
        s["current"] = "build"
        desk.save(self.card, s)
        with open(os.path.join(self.card, "approvals.json"), "w") as f:
            json.dump({"plan": True}, f)
        subprocess.run([sys.executable, os.path.join(ROOT, "hooks", "rules.py"), wt], check=True, capture_output=True)
        payload = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(wt, "x.py")}, "cwd": self.card}
        out = subprocess.run([sys.executable, os.path.join(ROOT, "hooks", "gate.py")], input=json.dumps(payload),
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out, "")

    def test_unknown_repo_fails(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "worktree.py"), self.card, "nope",
                            "--repos", self.repos], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
