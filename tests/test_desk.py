import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desk  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import sessions  # noqa: E402

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


class DoctorTest(unittest.TestCase):
    """A healthy card with a worktree, then one problem at a time."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.clone = os.path.join(self.tmp, "clone")
        subprocess.run(["git", "init", "-q", "-b", "main", self.clone], check=True)
        subprocess.run(["git", "-C", self.clone, "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        self.card = os.path.join(self.tmp, "desk", "ABC-1")
        desk.init(self.card, STEPS + [{"id": "pr", "gate": "approve"}])
        sessions.append(self.card, "claim", "s1", 1)
        self.wt = os.path.join(self.card, "worktrees", "clone")
        subprocess.run(["git", "-C", self.clone, "worktree", "add", "-q", "-b", "bureau/ABC-1", self.wt], check=True)

    def doctor(self, card=None, clone=None):
        return desk.doctor(card or self.card, {"clone": {"path": clone or self.clone}})

    def set(self, **kw):
        s = desk.load(self.card)
        s.update(kw)
        desk.save(self.card, s)

    def snapshot(self):
        out = {}
        for f in os.listdir(self.card):
            p = os.path.join(self.card, f)
            if os.path.isfile(p):
                with open(p, "rb") as fh:
                    out[f] = fh.read()
        return out

    def test_healthy_card_has_no_lines_and_doctor_writes_no_card_file(self):
        before = self.snapshot()
        self.assertEqual(self.doctor(), [])
        self.assertEqual(self.snapshot(), before)

    def test_missing_claim_log(self):
        os.remove(os.path.join(self.card, "sessions" + ".jsonl"))
        self.assertEqual(self.doctor(), ["no claim log. Fix: /work ABC-1"])

    def test_renamed_card(self):
        self.set(card="OLD-1")
        [line] = self.doctor()
        self.assertIn("renamed", line)
        self.assertIn("desk/OLD-1", line)

    def test_awaiting_and_current_not_steps(self):
        self.set(awaiting="ghost", current="gone")
        lines = self.doctor()
        self.assertTrue(any("awaiting 'ghost'" in x for x in lines), lines)
        self.assertTrue(any("current 'gone'" in x for x in lines), lines)

    def test_approval_for_a_step_not_reached(self):
        with open(os.path.join(self.card, "approvals.json"), "w") as f:
            json.dump({"plan": True, "pr": True}, f)  # plan is current: approving it is fine, pr is ahead
        [line] = self.doctor()
        self.assertIn("'pr'", line)
        self.set(current="build")
        with open(os.path.join(self.card, "approvals.json"), "w") as f:
            json.dump({"plan": True}, f)  # a past approval stays on record
        self.assertEqual(self.doctor(), [])

    def test_done_card_with_unopened_pr_and_unposted_replies(self):
        self.set(current="done")
        with open(os.path.join(self.card, "pr.md"), "w") as f:
            f.write("# Title\n\nbody\n")
        with open(os.path.join(self.card, "reply.json"), "w") as f:
            json.dump([{"body": "a", "posted": True}, {"body": "b"}], f)
        lines = self.doctor()
        self.assertTrue(any("scripts/pr.py" in x for x in lines), lines)
        self.assertTrue(any("1 of 2" in x and "scripts/reply.py" in x for x in lines), lines)
        with open(os.path.join(self.card, "pr.md"), "a") as f:
            f.write("\n## Opened\nhttps://example/pr/1\n")
        self.assertEqual(len(self.doctor()), 1)

    def test_worktree_on_wrong_branch(self):
        subprocess.run(["git", "-C", self.wt, "checkout", "-q", "-b", "other"], check=True)
        [line] = self.doctor()
        self.assertIn("bureau/ABC-1", line)

    def test_moved_checkout_worktree_is_repaired(self):
        """The Bureau move: source repo and desk both moved, repos.yaml already points at the new clone."""
        new = os.path.join(self.tmp, "moved")
        os.makedirs(new)
        os.rename(self.clone, os.path.join(new, "clone"))
        os.rename(os.path.join(self.tmp, "desk"), os.path.join(new, "desk"))
        card, clone = os.path.join(new, "desk", "ABC-1"), os.path.join(new, "clone")
        wt = os.path.join(card, "worktrees", "clone")
        self.assertNotEqual(subprocess.run(["git", "-C", wt, "status"], capture_output=True).returncode, 0)
        [line] = self.doctor(card, clone)
        self.assertTrue(line.startswith("fixed:"), line)
        subprocess.run(["git", "-C", wt, "status"], check=True, capture_output=True)
        self.assertEqual(self.doctor(card, clone), [])  # idempotent

    def test_branch_check_skipped_without_pr_step(self):
        subprocess.run(["git", "-C", self.wt, "checkout", "-q", "-b", "pr-head"], check=True)
        self.set(steps=STEPS)  # pr-review style: the worktree sits on the PR's head branch
        self.assertEqual(self.doctor(), [])

    def test_worktree_dir_without_git_is_reported(self):
        os.makedirs(os.path.join(self.card, "worktrees", "stray"))
        [line] = self.doctor()
        self.assertIn("worktree stray is not a git worktree", line)

    def test_next_block_names_the_folder_not_a_stale_state_card(self):
        self.set(card="OLD-1", awaiting="plan")
        self.assertIn("/approve ABC-1", desk.next_block(self.card, desk.load(self.card)))

    def test_broken_worktree_without_a_valid_repos_path_is_reported(self):
        os.rename(self.clone, self.clone + "-gone")
        [line] = self.doctor(clone=self.clone)
        self.assertIn("repos.yaml", line)

    def test_cli_sweeps_desk_and_exits_1_on_unfixed(self):
        other = os.path.join(self.tmp, "desk", "XYZ-2")
        desk.init(other, STEPS)  # no claim log
        os.makedirs(os.path.join(self.tmp, "desk", ".archive", "OLD-3"))
        desk.init(os.path.join(self.tmp, "desk", ".archive", "OLD-3"), STEPS)  # archived: skipped
        repos = os.path.join(self.tmp, "repos.yaml")
        with open(repos, "w") as f:
            f.write(f"repos:\n  clone:\n    path: {self.clone}\n")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "desk.py"), "doctor"],
                           capture_output=True, text=True, cwd=os.path.join(self.tmp, "desk"),
                           env={**os.environ, "BUREAU_REPOS": repos, "BUREAU_DESK": os.path.join(self.tmp, "desk")})
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(r.stdout.strip(), "XYZ-2: no claim log. Fix: /work XYZ-2")

    def test_cli_keeps_sweeping_past_a_malformed_card(self):
        bad = os.path.join(self.tmp, "desk", "AAA-0")  # walked before ABC-1
        os.makedirs(bad)
        with open(os.path.join(bad, "state.json"), "w") as f:
            f.write("{bad")
        nosteps = os.path.join(self.tmp, "desk", "AAB-0")
        os.makedirs(nosteps)
        with open(os.path.join(nosteps, "state.json"), "w") as f:
            json.dump({"current": "plan"}, f)
        os.remove(os.path.join(self.card, "sessions" + ".jsonl"))  # a problem on the healthy card, found after them
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "desk.py"), "doctor"], capture_output=True,
                           text=True, env={**os.environ, "BUREAU_REPOS": os.path.join(self.tmp, "none.yaml"),
                                           "BUREAU_DESK": os.path.join(self.tmp, "desk")})
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("AAA-0: state.json unreadable", r.stdout)
        self.assertIn("AAB-0: state.json unreadable", r.stdout)
        self.assertIn("ABC-1: no claim log", r.stdout)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "desk.py"), "doctor",
                            os.path.join(self.tmp, "desk", "TYPO-9")], capture_output=True, text=True,
                           env={**os.environ, "BUREAU_DESK": os.path.join(self.tmp, "desk")})
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("TYPO-9: state.json unreadable", r.stdout)


if __name__ == "__main__":
    unittest.main()
