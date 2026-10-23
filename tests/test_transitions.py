import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import desk  # noqa: E402

STEPS = [{"id": "plan", "gate": "approve"}, {"id": "build", "gate": "approve", "writes_code": True},
         {"id": "review", "gate": "none"}]


class TransitionTest(unittest.TestCase):
    def setUp(self):
        self.card = os.path.join(tempfile.mkdtemp(), "ABC-1")
        desk.init(self.card, STEPS)

    def approve(self, *ids):
        with open(os.path.join(self.card, "approvals.json"), "w") as f:
            json.dump({i: True for i in ids}, f)

    def test_gated_step_waits_then_advances_only_when_approved(self):
        self.assertEqual(desk.finish(self.card)["awaiting"], "plan")
        with self.assertRaises(ValueError):
            desk.advance(self.card)
        self.approve("plan")
        s = desk.advance(self.card)
        self.assertEqual((s["current"], s["awaiting"]), ("build", None))

    def test_ungated_step_advances_and_last_step_is_done(self):
        for sid in ("plan", "build"):
            desk.finish(self.card)
            self.approve("plan", "build")
            desk.advance(self.card)
        self.assertEqual(desk.finish(self.card)["current"], "done")

    def test_next_block_gated_names_command_card_and_artifact(self):
        out = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("Run:     /approve ABC-1", out)
        self.assertIn(f"Read {self.card}/plan.md", out)
        self.assertIn("redoes plan", out)

    def test_next_block_ungated_continues_then_done(self):
        self.approve("plan", "build")
        for _ in range(2):
            desk.finish(self.card)
            desk.advance(self.card)
        out = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("Run:     none", out)
        self.assertIn("merge the draft PR", out)
        self.assertNotIn("/approve", out)

    def test_next_block_names_each_cards_own_id_when_two_await(self):
        other = os.path.join(os.path.dirname(self.card), "ABC-2")
        desk.init(other, STEPS)
        for card in (self.card, other):
            self.assertIn(f"/approve {os.path.basename(card)}\n", desk.next_block(card, desk.finish(card)))

    def test_next_block_ungated_mid_run_names_next_step(self):
        s = desk.load(self.card)
        s["steps"][0]["gate"] = "none"
        desk.save(self.card, s)
        out = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("continuing with build", out)

    def test_cli_finish_prints_next_block(self):
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(desk.__file__), "desk.py"), "finish", self.card],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("Run:     /approve ABC-1", out)

    def test_revise_versions_artifact_and_clears_approval(self):
        open(os.path.join(self.card, "plan.md"), "w").write("v1")
        desk.finish(self.card)
        self.approve("plan")
        s = desk.revise(self.card, "cover the migration")
        self.assertEqual((s["current"], s["awaiting"]), ("plan", None))
        self.assertTrue(os.path.exists(os.path.join(self.card, "plan.v1.md")))
        self.assertFalse(os.path.exists(os.path.join(self.card, "plan.md")))
        self.assertIn("migration", open(os.path.join(self.card, "plan.feedback-1.md")).read())
        self.assertEqual(json.load(open(os.path.join(self.card, "approvals.json"))), {})

    def test_reject_goes_back_and_clears_later_approvals(self):
        self.approve("plan", "build")
        s = desk.load(self.card)
        s["current"] = "review"
        desk.save(self.card, s)
        s = desk.reject(self.card, "plan", "wrong approach")
        self.assertEqual(s["current"], "plan")
        self.assertEqual(json.load(open(os.path.join(self.card, "approvals.json"))), {})
        with self.assertRaises(ValueError):
            desk.reject(self.card, "nope", "x")

    def test_add_and_skip(self):
        s = desk.add(self.card, "plan", {"id": "design", "gate": "approve"})
        self.assertEqual([x["id"] for x in s["steps"]], ["plan", "design", "build", "review"])
        s = desk.skip(self.card, "review")
        self.assertEqual([x["id"] for x in s["steps"]], ["plan", "design", "build"])
        with self.assertRaises(ValueError):
            desk.skip(self.card, "plan")  # current step
        with self.assertRaises(ValueError):
            desk.add(self.card, "plan", {"id": "build"})  # duplicate id


class CancelTest(unittest.TestCase):
    def setUp(self):
        self.desk = tempfile.mkdtemp()
        self.card = os.path.join(self.desk, "ABC-1")
        desk.init(self.card, STEPS)

    def test_cancel_records_reason_clears_awaiting_and_renames_the_folder(self):
        desk.finish(self.card)  # plan is gated: awaiting
        new = desk.cancel(self.card, "not needed")
        self.assertEqual(new, os.path.join(self.desk, "ABC-1.cancelled"))
        self.assertFalse(os.path.exists(self.card))
        s = desk.load(new)
        self.assertEqual((s["current"], s["awaiting"], s["cancelled"]["reason"]), ("cancelled", None, "not needed"))
        self.assertTrue(s["cancelled"]["at"])
        self.assertIn("cancelled", desk.list_cards(self.desk)[0])

    def test_repeat_cancels_of_the_same_id_get_a_counter(self):
        desk.cancel(self.card, "a")
        desk.init(self.card, STEPS)
        self.assertEqual(desk.cancel(self.card, "b"), os.path.join(self.desk, "ABC-1.cancelled-2"))
        desk.init(self.card, STEPS)
        self.assertEqual(desk.cancel(self.card, "c"), os.path.join(self.desk, "ABC-1.cancelled-3"))

    def test_cancelled_and_done_cards_refuse_every_transition(self):
        done = os.path.join(self.desk, "ABC-2")
        desk.init(done, STEPS)
        s = desk.load(done)
        s["current"] = "done"
        desk.save(done, s)
        with self.assertRaises(ValueError):
            desk.cancel(done, "x")
        new = desk.cancel(self.card, "x")
        for call in (lambda: desk.cancel(new, "y"), lambda: desk.finish(new), lambda: desk.advance(new),
                     lambda: desk.revise(new, "f"), lambda: desk.reject(new, "plan", "r"),
                     lambda: desk.add(new, "plan", {"id": "x"}), lambda: desk.skip(new, "review")):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(desk.load(new)["current"], "cancelled")

    def test_worktree_still_works_after_the_rename(self):
        clone = os.path.join(self.desk, "clone")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        subprocess.run(["git", "-C", clone, "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        wt = os.path.join(self.card, "worktrees", "clone")
        subprocess.run(["git", "-C", clone, "worktree", "add", "-q", "-b", "bureau/ABC-1", wt], check=True)
        new = desk.cancel(self.card, "x")
        r = subprocess.run(["git", "-C", os.path.join(new, "worktrees", "clone"), "status", "-sb"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bureau/ABC-1", r.stdout)  # the branch keeps its name

    def test_next_block_and_cli_name_the_cancelled_card(self):
        new = desk.cancel(self.card, "x")
        self.assertIn("cancelled", desk.next_block(new, desk.load(new)))
        card = os.path.join(self.desk, "ABC-9")
        desk.init(card, STEPS)
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(desk.__file__), "desk.py"), "cancel", card, "why"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("ABC-9.cancelled", out)


class ListTest(unittest.TestCase):
    def test_list_finds_nested_runs_and_skips_worktrees(self):
        d = tempfile.mkdtemp()
        desk.init(os.path.join(d, "P-1"), STEPS, "project")
        desk.init(os.path.join(d, "P-1", "tasks", "T-1"), STEPS, "task")
        os.makedirs(os.path.join(d, "P-1", "worktrees", "r"))
        open(os.path.join(d, "P-1", "worktrees", "r", "state.json"), "w").write("{}")  # a repo's own file
        rows = desk.list_cards(d)
        self.assertEqual(sorted(r.split("\t")[0] for r in rows), ["P-1", "P-1/tasks/T-1"])


if __name__ == "__main__":
    unittest.main()
