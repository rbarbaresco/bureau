import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desk  # noqa: E402
import project  # noqa: E402
import workflow  # noqa: E402

TASKS = """# Tasks

| id | title | repo | blocked by | edge |
|----|-------|------|------------|------|
| 1 | Add the parser | bureau | - | - |
| 2 | Use the parser | bureau | 1 | stated |
| 3 | Docs | bureau | 1, 2 | inferred |
"""


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.parent = os.path.join(self.tmp, "proj")
        workflow.start("project", self.parent)
        with open(os.path.join(self.parent, "tasks.md"), "w") as f:
            f.write(TASKS)

    def test_shipped_project_workflow(self):
        wf = workflow.parse(os.path.join(ROOT, "workflows", "project.md"))
        self.assertEqual([s["id"] for s in wf["steps"]], ["intake", "run"])
        self.assertTrue(wf["steps"][1]["loop"])
        self.assertFalse(any(s["writes_code"] for s in wf["steps"]))

    def test_parse_edges(self):
        t = project.parse(TASKS)
        self.assertEqual([(x["id"], x["blocked"], x["edge"]) for x in t],
                         [("1", [], "-"), ("2", ["1"], "stated"), ("3", ["1", "2"], "inferred")])

    def test_parse_rejects_unknown_blocker_cycle_duplicate(self):
        head = "| id | title | repo | blocked by | edge |\n|--|--|--|--|--|\n"
        for rows, msg in (("| 1 | A | r | 9 | stated |\n", "unknown"),
                          ("| 1 | A | r | 2 | stated |\n| 2 | B | r | 1 | stated |\n", "cycle"),
                          ("| 1 | A | r | - | - |\n| 1 | B | r | - | - |\n", "duplicate"),
                          ("| 1 | A | r | - | maybe |\n", "edge")):
            with self.assertRaisesRegex(ValueError, msg):
                project.parse(head + rows)

    def test_parse_reads_only_the_first_table(self):
        notes = TASKS + "\nWhy 3 is inferred:\n\n| file | tasks |\n|--|--|\n| a.py | 2, 3 |\n"
        self.assertEqual(len(project.parse(notes)), 3)
        self.assertEqual(len(project.parse(TASKS + "Note: a | b | c\n")), 3)  # stops at the first non-table line

    def test_parse_errors_say_what_is_wrong(self):
        head = "| id | title | repo | blocked by | edge |\n|--|--|--|--|--|\n"
        for text, msg in ((head, "no task rows"),
                          ("no table here\n", "no table"),
                          ("| id | title | repo | blocked by | edge |\n| 1 | A | r | - | - |\n", "separator"),
                          (head + "| 1 | A | r | - | - |\n| 2 | B | r |  | stated |\n", "blocked by is empty"),
                          (head + "| 1 | A | r | - | - |\n| 2 | B | r | 1 | - |\n", "edge"),
                          (head + "| 1 | A | r | - | stated |\n", "edge"),
                          (head + "| a b | A | r | - | - |\n", "bad id"),
                          (head + "| 1 | A | r | - |\n", "5 columns")):
            with self.assertRaisesRegex(ValueError, msg, msg=text):
                project.parse(text)

    def test_is_merged(self):
        kid = os.path.join(self.tmp, "kid")
        os.makedirs(kid)
        fake = lambda out, code=0: lambda *a, **k: type("R", (), {"returncode": code, "stdout": out})()
        self.assertFalse(project.is_merged(kid, fake("x")))  # no pr.md
        with open(os.path.join(kid, "pr.md"), "w") as f:
            f.write("title\n\nbody\n")
        self.assertFalse(project.is_merged(kid, fake("x")))  # not opened yet
        with open(os.path.join(kid, "pr.md"), "w") as f:
            f.write("title\n\nbody\n\n## Opened\n\nhttps://github.com/o/r/pull/1\n")
        self.assertTrue(project.is_merged(kid, fake("2026-11-07T10:00:00Z\n")))
        self.assertFalse(project.is_merged(kid, fake("\n")))
        self.assertFalse(project.is_merged(kid, fake("null\n")))
        self.assertFalse(project.is_merged(kid, fake("2026-11-07\n", code=1)))

    def test_is_merged_survives_a_missing_or_hanging_gh(self):
        kid = os.path.join(self.tmp, "kid")
        os.makedirs(kid)
        with open(os.path.join(kid, "pr.md"), "w") as f:
            f.write("t\n\n## Opened\n\nhttps://github.com/o/r/pull/1\n")

        def no_gh(*a, **k):
            raise FileNotFoundError("gh")

        def hangs(*a, **k):
            raise project.subprocess.TimeoutExpired("gh", 1)
        self.assertFalse(project.is_merged(kid, no_gh))
        self.assertFalse(project.is_merged(kid, hangs))

    def test_status_tolerates_a_child_state_without_current(self):
        project.spawn(self.parent)
        with open(os.path.join(self.parent, "proj-1", "state.json"), "w") as f:
            json.dump({"card": "proj-1"}, f)
        rows = project.status(self.parent, lambda kid: False)
        self.assertEqual(rows[0]["step"], "?")

    def test_spawn_creates_children_once(self):
        project.spawn(self.parent)
        kid = os.path.join(self.parent, "proj-2")
        s = desk.load(kid)
        self.assertEqual((s["card"], s["parent"], s["workflow"], s["current"]), ("proj-2", "proj", "task", "understand"))
        self.assertIn("Use the parser", open(os.path.join(kid, "card.md")).read())
        with open(os.path.join(kid, "marker"), "w"):
            pass
        project.spawn(self.parent)  # again: existing children are left alone
        self.assertTrue(os.path.exists(os.path.join(kid, "marker")))

    def test_frontier_comes_from_merged_not_tracker(self):
        project.spawn(self.parent)
        merged = set()
        rows = lambda: {r["id"]: r["state"] for r in project.status(self.parent, lambda kid: os.path.basename(kid) in merged)}
        self.assertEqual(rows(), {"1": "ready", "2": "waits on 1", "3": "waits on 1, 2"})
        merged.add("proj-1")
        self.assertEqual(rows(), {"1": "merged", "2": "ready", "3": "waits on 2"})

    def test_next_block_lists_children_and_stays_for_plain_cards(self):
        project.spawn(self.parent)
        block = desk.next_block(self.parent, desk.load(self.parent))
        self.assertIn("proj-1", block)
        self.assertIn("proj-3", block)
        plain = os.path.join(self.tmp, "plain")
        desk.init(plain, [{"id": "plan", "gate": "approve"}])
        self.assertNotIn("Children", desk.next_block(plain, desk.load(plain)))

    def test_doctor_does_not_ask_children_for_a_claim_log(self):
        project.spawn(self.parent)
        out = desk.doctor(os.path.join(self.parent, "proj-1"), {})
        self.assertFalse([x for x in out if "claim log" in x])


if __name__ == "__main__":
    unittest.main()
