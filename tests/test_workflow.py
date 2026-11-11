import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import desk  # noqa: E402
import workflow  # noqa: E402


class WorkflowTest(unittest.TestCase):
    def test_shipped_workflows_parse(self):
        for name in ("bugfix", "task", "small", "pr-review"):
            wf = workflow.parse(os.path.join(ROOT, "workflows", name + ".md"))
            self.assertEqual(wf["name"], name)
            self.assertTrue(wf["steps"])
            code = [s for s in wf["steps"] if s["writes_code"]]
            self.assertTrue(code, name)
            self.assertEqual(code[0]["gate"], "approve")
            for i, s in enumerate(wf["steps"]):  # an ungated code step (docs) is safe only if a gate follows it
                if s["writes_code"] and s["gate"] == "none":
                    self.assertTrue(any(t["gate"] == "approve" for t in wf["steps"][i + 1:]), f"{name}/{s['id']}")
            # the human approves something before any code is written (plan, or understand in `small`)
            before = wf["steps"][: wf["steps"].index(code[0])]
            self.assertTrue(any(s["gate"] == "approve" for s in before), name)
            self.assertTrue(all(s["instructions"] for s in wf["steps"]))

    def test_peer_review_never_writes_code_and_posts_behind_a_gate(self):
        wf = workflow.parse(os.path.join(ROOT, "workflows", "peer-review.md"))
        self.assertEqual([s["id"] for s in wf["steps"]], ["review", "draft"])
        self.assertFalse(any(s["writes_code"] for s in wf["steps"]))
        self.assertTrue(all(s["gate"] == "approve" and s["instructions"] for s in wf["steps"]))
        self.assertIn("post_review.py", wf["steps"][-1]["instructions"])

    def test_step_catalogue_parses(self):
        d = os.path.join(ROOT, "steps")
        files = sorted(f for f in os.listdir(d) if f.endswith(".md"))
        self.assertGreaterEqual(len(files), 10)
        for f in files:
            wf = workflow.parse(os.path.join(d, f))
            self.assertEqual([s["id"] for s in wf["steps"]], [f[:-3]], f)  # one step, named after its file
            self.assertEqual(wf["name"], f[:-3], f)
            self.assertTrue(wf["steps"][0]["instructions"], f)

    def test_malformed_rejected(self):
        d = tempfile.mkdtemp()
        cases = {
            "nofront.md": "## a\ngate: none\n\nx\n",
            "nouse.md": "---\nname: x\n---\n## a\n\nx\n",
            "badgate.md": "---\nname: x\nuse_when: y\n---\n## a\ngate: maybe\n\nx\n",
            "dup.md": "---\nname: x\nuse_when: y\n---\n## a\n\nx\n## a\n\ny\n",
            "nosteps.md": "---\nname: x\nuse_when: y\n---\njust text\n",
        }
        for fname, text in cases.items():
            p = os.path.join(d, fname)
            open(p, "w").write(text)
            with self.assertRaises(ValueError, msg=fname):
                workflow.parse(p)

    def test_loop_parsed_as_bool(self):
        p = os.path.join(tempfile.mkdtemp(), "l.md")
        with open(p, "w") as f:
            f.write("---\nname: l\nuse_when: y\n---\n## rounds\ngate: approve\nloop: true\n\nx\n## next\n\ny\n")
        steps = workflow.parse(p)["steps"]
        self.assertEqual([s["loop"] for s in steps], [True, False])
        card = os.path.join(tempfile.mkdtemp(), "ABC-1")
        workflow.start(p, card)
        self.assertTrue(desk.load(card)["steps"][0]["loop"])
        with open(p, "w") as f:
            f.write("---\nname: l\nuse_when: y\n---\n## rounds\nloop: true\n\nx\n")
        with self.assertRaises(ValueError):  # a loop needs a gate
            workflow.parse(p)

    def test_start_creates_run_with_own_copy(self):
        card = os.path.join(tempfile.mkdtemp(), "ABC-1")
        workflow.start("bugfix", card)
        s = desk.load(card)
        self.assertEqual((s["workflow"], s["current"]), ("bugfix", "plan"))
        self.assertTrue(os.path.isfile(os.path.join(card, "workflow.md")))
        self.assertNotIn("instructions", s["steps"][0])

    def test_list_cli(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "workflow.py"), "list"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("bugfix:", out)
        self.assertIn("task:", out)
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "workflow.py"), "steps"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("reproduce:", out)
        self.assertIn("publish:", out)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "workflow.py"), "show",
                            os.path.join(ROOT, "steps", "docs.md")], capture_output=True, text=True, check=True)
        self.assertIn("docs none journalist", r.stdout)
        self.assertIn("later gated step", r.stderr)  # shown, with the warning a run would refuse on


if __name__ == "__main__":
    unittest.main()
