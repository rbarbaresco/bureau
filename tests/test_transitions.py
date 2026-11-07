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
        self.assertIn("Approve:   /approve ABC-1", out)
        self.assertIn(f"Review:    {self.card}/plan.md", out)
        self.assertIn("redoes plan", out)
        self.assertIn("Steps:     [ ] plan -> [ ] build -> [ ] review", out)
        self.assertNotIn("Answer the open questions", out)

    def test_next_block_ungated_continues_then_done(self):
        self.approve("plan", "build")
        for _ in range(2):
            desk.finish(self.card)
            desk.advance(self.card)
        out = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("Run:       none", out)
        self.assertIn("Needed:    nothing", out)  # STEPS has no pr step, so no PR to merge
        self.assertNotIn("/approve", out)

    def test_next_block_names_each_cards_own_id_when_two_await(self):
        other = os.path.join(os.path.dirname(self.card), "ABC-2")
        desk.init(other, STEPS)
        for card in (self.card, other):
            self.assertIn(f"/approve {os.path.basename(card)} ->", desk.next_block(card, desk.finish(card)))

    def test_next_block_ungated_mid_run_names_next_step(self):
        s = desk.load(self.card)
        s["steps"][0]["gate"] = "none"
        desk.save(self.card, s)
        out = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("continuing with build", out)

    def test_cli_finish_prints_next_block(self):
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(desk.__file__), "desk.py"), "finish", self.card],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("Approve:   /approve ABC-1", out)

    def test_next_block_gated_says_where_the_card_stands_and_what_approve_starts(self):
        card = os.path.join(tempfile.mkdtemp(), "ABC-9")
        desk.init(card, [{"id": "plan", "gate": "approve", "persona": "architect"},
                         {"id": "build", "gate": "approve", "persona": "staff-engineer"},
                         {"id": "pr", "gate": "approve"}], "task")
        out = desk.next_block(card, desk.finish(card))
        self.assertIn("Card:      ABC-9 · task · step 1 of 3", out)
        self.assertIn("/approve ABC-9 -> build starts (staff-engineer, gate approve)", out)
        with open(os.path.join(card, "approvals.json"), "w") as f:
            json.dump({"plan": True, "build": True}, f)
        for _ in range(2):
            desk.advance(card)
            out = desk.next_block(card, desk.finish(card))
        self.assertIn("Steps:     [x] plan -> [x] build -> [ ] pr", out)
        self.assertIn("pushes the branch and opens a draft PR, then the run ends", out)

    def test_next_block_running_and_done_carry_the_state_line(self):
        s = desk.load(self.card)
        s["steps"][0]["gate"] = "none"
        desk.save(self.card, s)
        self.assertIn("Card:      ABC-1 · ? · step 2 of 3", desk.next_block(self.card, desk.finish(self.card)))
        s = desk.load(self.card)
        s["current"] = "done"
        self.assertIn("Card:      ABC-1 · ? · done (3 steps)", desk.next_block(self.card, s))
        self.assertIn("Steps:     [x] plan -> [x] build -> [x] review", desk.next_block(self.card, s))

    def test_next_block_loop_says_another_round_and_what_done_starts(self):
        card = self.loop_card()
        out = desk.next_block(card, desk.finish(card))
        self.assertIn("-> another round of rounds", out)
        self.assertIn("ends the loop; review starts (-, gate none)", out)

    def test_cli_advance_prints_next_block(self):
        desk.finish(self.card)
        self.approve("plan")
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(desk.__file__), "desk.py"), "advance", self.card],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("Card:      ABC-1 · ? · step 2 of 3", out)

    def write_plan(self, text):
        with open(os.path.join(self.card, "plan.md"), "w") as f:
            f.write(text)

    def test_next_block_lists_each_open_question_by_its_short_label(self):
        self.write_plan("# P\n\n## Open questions\n1. Cap: Cut at 100 characters or first line? Default: 100\n"
                        "   wrapped on a second line\n2. Merge: Keep Run and After apart?\n3. no label here\n")
        out = desk.next_block(self.card, desk.finish(self.card))
        self.assertIn("Questions: - Cap", out)
        self.assertIn("- Merge\n", out)
        self.assertIn("- no label here\n", out)
        self.assertNotIn("100 characters", out)

    def test_next_block_says_none_when_there_are_no_open_questions(self):
        for text in ("## Open questions\nnone\n", "## Open questions\nNone.\n", "no section at all\n", None,
                     "## Open questions\n- none\n", "## Open questions\nnone (both settled by feedback)\n",
                     "## Open questions\n**None**\n", "## Open questions\n1. none\n", "## Open questions\n2) None.\n", "## Open questions\nn/a\n"):
            with self.subTest(text=text):
                if text is not None:
                    self.write_plan(text)
                self.assertIn("Questions: none\n", desk.next_block(self.card, desk.finish(self.card)))
                desk.revise(self.card, "again")

    def test_questions_edge_shapes(self):
        for text, want in (("1. Do X or Y? Default: X\n", ["Do X or Y? Default: X"]),
                           ("1. Use http://x? Default: yes\n", ["Use http://x? Default: yes"]),
                           ("Two things:\n1. A: x\n2. B: y\n", ["A", "B"]),
                           ("1. Long\n   label: text\n", ["Long label"]),
                           ("- None of these fit: pick one?\n", ["None of these fit"]),
                           ("- **Scope:** Only desk.py? Default: yes\n", ["Scope"]),
                           ("- Scope:text here\n", ["Scope:text here"]),
                           ("- Scope:\n", ["Scope"]),
                           ("- None of the helpers cover X; add one.\n", ["None of the helpers cover X; add one."]),
                           ("Should we do X?\n- details\n", ["Should we do X?", "details"]),
                           ("A plain paragraph question? Default: no\n", ["A plain paragraph question? Default: no"])):
            with self.subTest(text=text):
                self.write_plan("## Open questions\n" + text)
                self.assertEqual(desk._questions(self.card, "plan"), want)

    def test_next_block_reply_step_says_it_posts(self):
        card = os.path.join(tempfile.mkdtemp(), "PRR-1")
        desk.init(card, [{"id": "reply", "gate": "approve"}], "pr-review")
        self.assertIn("pushes the branch and posts reply.json, then the run ends", desk.next_block(card, desk.finish(card)))

    def test_next_block_done_names_the_merge_only_when_the_run_opened_a_pr(self):
        for steps, needed in (([{"id": "pr", "gate": "none"}], "merge the draft PR (yours)"),
                              ([{"id": "reply", "gate": "none"}], "nothing; the PR's author merges"),
                              ([{"id": "plan", "gate": "none"}], "nothing")):
            card = os.path.join(tempfile.mkdtemp(), "D-1")
            desk.init(card, steps)
            self.assertIn(f"Needed:    {needed}", desk.next_block(card, desk.finish(card)))

    def test_cli_next_prints_the_block_from_saved_state_without_changing_it(self):
        desk.finish(self.card)
        before = desk.load(self.card)
        out = subprocess.run([sys.executable, os.path.join(os.path.dirname(desk.__file__), "desk.py"), "next", self.card],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("Card:      ABC-1 · ? · step 1 of 3", out)
        self.assertEqual(desk.load(self.card), before)

    def test_advance_on_a_loop_round_and_into_done_print_state(self):
        card = self.loop_card()
        desk.finish(card)
        self.approve_loop(card, True)
        self.assertIn("step 1 of 2", desk.next_block(card, desk.advance(card)))
        desk.finish(card)
        self.approve_loop(card, "done")
        desk.advance(card)
        self.assertIn("done (2 steps)", desk.next_block(card, desk.finish(card)))

    def loop_card(self):
        card = os.path.join(tempfile.mkdtemp(), "LOOP-1")
        desk.init(card, [{"id": "rounds", "gate": "approve", "loop": True}, {"id": "review", "gate": "none"}])
        return card

    def approve_loop(self, card, value):
        with open(os.path.join(card, "approvals.json"), "w") as f:
            json.dump({"rounds": value}, f)

    def test_loop_round_approved_stays_on_step_and_versions_artifact(self):
        card = self.loop_card()
        for n in (1, 2):
            with open(os.path.join(card, "rounds.md"), "w") as f:
                f.write(f"round {n}\n")
            desk.finish(card)
            self.approve_loop(card, True)
            s = desk.advance(card)
            self.assertEqual((s["current"], s["awaiting"]), ("rounds", None))
            with open(os.path.join(card, f"rounds.round-{n}.md")) as f:
                self.assertEqual(f.read(), f"round {n}\n")
            self.assertFalse(os.path.exists(os.path.join(card, "rounds.md")))
            self.assertNotIn("rounds", desk._approvals(card))  # the next round needs a fresh /approve

    def test_loop_done_advances(self):
        card = self.loop_card()
        desk.finish(card)
        self.approve_loop(card, "done")
        s = desk.advance(card)
        self.assertEqual((s["current"], s["awaiting"]), ("review", None))
        self.assertEqual(desk._approvals(card), {"rounds": "done"})

    def test_next_block_loop_names_done(self):
        card = self.loop_card()
        out = desk.next_block(card, desk.finish(card))
        self.assertIn("/approve LOOP-1 done", out)

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
