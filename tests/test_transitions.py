import json
import os
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


if __name__ == "__main__":
    unittest.main()
