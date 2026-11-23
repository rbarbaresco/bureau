"""Standing settings (#126): /setup-bureau writes bureau.json; cards snapshot it at start; review may go back on its own."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desk  # noqa: E402
import workflow  # noqa: E402

SETUP = os.path.join(ROOT, "hooks", "setup.py")
TEMPLATE = os.path.join(ROOT, "bureau.template.json")
STEPS = [{"id": "plan", "gate": "approve"}, {"id": "build", "gate": "approve", "writes_code": True},
         {"id": "docs", "gate": "none", "writes_code": True}, {"id": "review", "gate": "approve"},
         {"id": "pr", "gate": "approve"}]


class GoBackTest(unittest.TestCase):
    def setUp(self):
        self.card = os.path.join(tempfile.mkdtemp(), "ABC-1")

    def at_review(self, settings, severity="medium"):
        desk.init(self.card, [dict(s) for s in STEPS], settings=settings)
        s = desk.load(self.card)
        s["current"] = "review"
        desk.save(self.card, s)
        if severity is not None:
            with open(os.path.join(self.card, "review.md"), "w") as f:
                f.write(f"# Review\nHighest severity: {severity}\n\n1. something\n")

    def test_off_stops_at_the_review_gate(self):
        for settings in (None, {}, {"go_back": "off"}):
            with self.subTest(settings=settings):
                self.card = os.path.join(tempfile.mkdtemp(), "ABC-1")
                self.at_review(settings, "high")
                s = desk.finish(self.card)
                self.assertEqual((s["current"], s["awaiting"]), ("review", "review"))

    def test_at_or_above_threshold_goes_back_to_the_code_step(self):
        self.at_review({"go_back": "medium", "go_back_rounds": "4"}, "high")
        s = desk.finish(self.card)
        self.assertEqual((s["current"], s["awaiting"]), ("build", None))
        with open(os.path.join(self.card, "reject-1.md")) as f:
            self.assertEqual(f.read(), "back to build: auto: review found high (round 1 of 4)\n")

    def test_below_threshold_none_and_missing_line_stop(self):
        for sev in ("low", "nit", "none", None):
            with self.subTest(sev=sev):
                self.card = os.path.join(tempfile.mkdtemp(), "ABC-1")
                self.at_review({"go_back": "medium"}, sev)
                self.assertEqual(desk.finish(self.card)["awaiting"], "review")

    def test_rounds_used_up_stops_and_human_rejects_do_not_count(self):
        self.at_review({"go_back": "low", "go_back_rounds": "2"}, "medium")
        desk.reject(self.card, "build", "human asked")  # a human go-back is not a round
        for n in (1, 2):
            s = desk.load(self.card)
            s["current"] = "review"
            desk.save(self.card, s)
            self.assertEqual(desk.finish(self.card)["current"], "build", n)
        s = desk.load(self.card)
        s["current"] = "review"
        desk.save(self.card, s)
        self.assertEqual(desk.finish(self.card)["awaiting"], "review")
        block = desk.next_block(self.card, desk.load(self.card))
        self.assertIn("Auto:", block)
        self.assertIn("2 go-backs from review (reject-2.md, reject-3.md)", block)

    def test_missing_severity_line_is_named_at_the_gate(self):
        self.at_review({"go_back": "medium"}, None)
        block = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("Highest severity:", block)

    def test_live_bureau_json_does_not_change_a_running_card(self):
        self.at_review(None, "high")
        with mock.patch.object(desk, "settings", return_value={"go_back": "nit"}):
            self.assertEqual(desk.finish(self.card)["awaiting"], "review")


class AutoAdvanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.settings = os.path.join(self.tmp, "bureau.json")
        p = mock.patch.object(desk, "SETTINGS", self.settings)
        p.start()
        self.addCleanup(p.stop)

    def write(self, data):
        with open(self.settings, "w") as f:
            json.dump(data, f)

    def test_start_ungates_the_code_step_and_stores_settings(self):
        self.write({"auto_advance": "on", "go_back": "medium", "go_back_rounds": "4"})
        card = os.path.join(self.tmp, "ABC-1")
        workflow.start("task", card)
        s = desk.load(card)
        build = next(x for x in s["steps"] if x["id"] == "build")
        self.assertEqual((build["gate"], build.get("auto")), ("none", True))
        self.assertEqual(next(x for x in s["steps"] if x["id"] == "pr")["gate"], "approve")
        self.assertEqual(s["settings"], {"auto_advance": "on", "go_back": "medium", "go_back_rounds": "4"})

    def test_off_or_missing_keeps_the_gate(self):
        for data in (None, {"auto_advance": "off"}):
            if data is not None:
                self.write(data)
            card = os.path.join(self.tmp, f"C-{data is None}")
            workflow.start("bugfix", card)
            self.assertEqual(next(x for x in desk.load(card)["steps"] if x["id"] == "fix")["gate"], "approve")

    def test_no_later_gate_refuses_the_override(self):
        with self.assertRaisesRegex(ValueError, "later gated step"):
            desk.apply_settings([{"id": "build", "gate": "approve", "writes_code": True}], {"auto_advance": "on"})

    def test_show_marks_the_auto_gate(self):
        self.write({"auto_advance": "on"})
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "workflow.py"), "show", "small"],
                             capture_output=True, text=True, env={**os.environ, "BUREAU_SETTINGS": self.settings}).stdout
        self.assertIn("| build | staff-engineer |  | none (auto) | yes |", out)


class SetupHookTest(unittest.TestCase):
    def setUp(self):
        self.settings = os.path.join(tempfile.mkdtemp(), "bureau.json")

    def run_hook(self, prompt):
        return subprocess.run([sys.executable, SETUP], input=json.dumps({"prompt": prompt}), capture_output=True,
                              text=True, env={**os.environ, "BUREAU_SETTINGS": self.settings}, check=True).stdout

    def saved(self):
        with open(self.settings) as f:
            return json.load(f)

    def test_template_suggestions_are_options(self):
        with open(TEMPLATE) as f:
            for q in json.load(f):
                self.assertIn(q["suggest"], [v for v, _ in q["options"]], q["key"])
                self.assertEqual(q["options"][0][0] == "off", q["key"] != "go_back_rounds", q["key"])

    def test_other_prompts_ignored(self):
        self.assertEqual(self.run_hook("hello /setup-bureau"), "")

    def test_no_args_prints_the_questionnaire(self):
        out = self.run_hook("/setup-bureau")
        self.assertIn("1. Auto-advance from the code step", out)
        self.assertIn("a) off: stop after build for /approve (today)   <- current", out)
        self.assertIn("   Suggestion: c", out)
        self.assertIn("b) 4   <- current", out)
        self.assertIn("/setup-bureau 1a 2c 3b", out)
        self.assertFalse(os.path.exists(self.settings))

    def test_answers_write_and_merge(self):
        self.run_hook("/setup-bureau 1b 2C")
        self.assertEqual(self.saved(), {"auto_advance": "on", "go_back": "medium"})
        out = self.run_hook("/setup-bureau 3c\nthanks")
        self.assertEqual(self.saved(), {"auto_advance": "on", "go_back": "medium", "go_back_rounds": "6"})
        self.assertIn("c) 6   <- current", out)

    def test_bad_answer_blocks_and_writes_nothing(self):
        for bad in ("/setup-bureau 1z", "/setup-bureau 9a", "/setup-bureau 1a x", "/setup-bureau 1a 1b"):
            with self.subTest(bad=bad):
                out = json.loads(self.run_hook(bad))
                self.assertEqual(out["decision"], "block")
                self.assertFalse(os.path.exists(self.settings))


if __name__ == "__main__":
    unittest.main()
