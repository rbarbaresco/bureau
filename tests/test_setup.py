"""Standing settings (#126): /setup-bureau writes bureau.json; cards snapshot it at start; review may go back on its own."""
import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desk  # noqa: E402
import workflow  # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import setup  # noqa: E402

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
        self.assertIn("2 of 2 go-back rounds; stopped: limit reached (reject-2.md, reject-3.md)", block)

    def test_the_block_after_an_auto_go_back_names_the_round(self):
        self.at_review({"go_back": "medium", "go_back_rounds": "4"}, "high")
        block = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("continuing with build", block)
        self.assertIn("Auto:      go-back, review found high (round 1 of 4)", block)
        self.assertEqual(desk.next_block(self.card, desk.load(self.card)), block)  # `next` on resume says the same
        block = desk.next_block(self.card, desk.reject(self.card, "plan", "human asked"))
        self.assertNotIn("Auto:", block)

    def test_the_gate_row_names_why_it_stopped(self):
        for sev, reason in (("none", "clean review"), ("low", "below medium"), ("nit", "below medium")):
            with self.subTest(sev=sev):
                self.card = os.path.join(tempfile.mkdtemp(), "ABC-1")
                self.at_review({"go_back": "medium", "go_back_rounds": "3"}, sev)
                block = desk.next_block(self.card, desk.finish(self.card))
                self.assertIn(f"Auto:      0 of 3 go-back rounds; stopped: {reason}\n", block)

    def test_the_pr_gate_shows_the_same_row(self):
        self.at_review({"go_back": "medium"}, "low")
        s = desk.load(self.card)
        s["current"] = s["awaiting"] = "pr"
        desk.save(self.card, s)
        self.assertIn("0 of 4 go-back rounds; stopped: below medium", desk.next_block(self.card, s))

    def test_other_gates_show_no_loop_row(self):
        self.at_review({"go_back": "medium"}, None)
        s = desk.load(self.card)
        s["current"] = s["awaiting"] = "plan"
        desk.save(self.card, s)
        self.assertNotIn("Auto:", desk.next_block(self.card, s))

    def test_missing_severity_is_the_reason_at_the_pr_gate(self):
        self.at_review({"go_back": "medium"}, None)
        s = desk.load(self.card)
        s["current"] = s["awaiting"] = "pr"
        desk.save(self.card, s)
        self.assertIn("0 of 4 go-back rounds; stopped: review.md has no `Highest severity:` line",
                      desk.next_block(self.card, s))

    def test_off_shows_no_row_without_earlier_auto_rounds(self):
        self.at_review({"go_back": "off"}, "high")
        self.assertNotIn("Auto:", desk.next_block(self.card, desk.finish(self.card)))

    def test_missing_severity_line_is_named_at_the_gate(self):
        self.at_review({"go_back": "medium"}, None)
        block = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("Highest severity:", block)

    def test_only_the_first_line_after_the_title_counts(self):
        self.at_review({"go_back": "medium"}, None)
        with open(os.path.join(self.card, "review.md"), "w") as f:
            f.write("# Review\n\nRound 2 intro\n\n- `Highest severity: high` must be line 1\n")
        self.assertEqual(desk.finish(self.card)["awaiting"], "review")

    def test_peer_review_has_no_code_step_so_no_auto_row(self):
        desk.init(self.card, [{"id": "review", "gate": "approve"}, {"id": "review-comments", "gate": "approve"}],
                  settings={"go_back": "medium"})
        self.assertNotIn("Auto:", desk.next_block(self.card, desk.finish(self.card)))

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

    def show(self, name):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["workflow.py", "show", name]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            runpy.run_path(os.path.join(ROOT, "scripts", "workflow.py"), run_name="__main__")
        return out.getvalue(), err.getvalue()

    def test_show_marks_the_auto_gate(self):
        self.write({"auto_advance": "on"})
        self.assertIn("| build | staff-engineer |  | none (auto) | yes |", self.show("small")[0])

    def test_show_warns_when_auto_advance_cannot_apply(self):
        self.write({"auto_advance": "on"})
        path = os.path.join(self.tmp, "nogate.md")
        with open(path, "w") as f:
            f.write("---\nname: nogate\nuse_when: x\n---\n## build\ngate: approve\nwrites_code: true\n\nDo it.\n")
        out, err = self.show(path)
        self.assertIn("| build | - |  | approve | yes |", out)
        self.assertIn("warning:", err)


class SetupHookTest(unittest.TestCase):
    def setUp(self):
        self.settings = os.path.join(tempfile.mkdtemp(), "bureau.json")
        p = mock.patch.object(desk, "SETTINGS", self.settings)
        p.start()
        self.addCleanup(p.stop)

    def run_hook(self, prompt, template=TEMPLATE):
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"prompt": prompt}))), \
                mock.patch.object(setup, "TEMPLATE", template), contextlib.redirect_stdout(out):
            try:
                setup.main()
            except SystemExit as e:
                self.assertEqual(e.code, 0)
        return out.getvalue()

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

    def test_missing_template_blocks_with_its_name(self):
        out = json.loads(self.run_hook("/setup-bureau 1b", template=self.settings + ".missing"))
        self.assertEqual(out["decision"], "block")
        self.assertIn("bureau.template.json", out["reason"])
        self.assertFalse(os.path.exists(self.settings))

    def test_bad_answer_blocks_and_writes_nothing(self):
        for bad in ("/setup-bureau 1z", "/setup-bureau 9a", "/setup-bureau 1a x", "/setup-bureau 1a 1b"):
            with self.subTest(bad=bad):
                out = json.loads(self.run_hook(bad))
                self.assertEqual(out["decision"], "block")
                self.assertFalse(os.path.exists(self.settings))


if __name__ == "__main__":
    unittest.main()
