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
        for name in ("bugfix", "task"):
            wf = workflow.parse(os.path.join(ROOT, "workflows", name + ".md"))
            self.assertEqual(wf["name"], name)
            self.assertTrue(wf["steps"])
            self.assertEqual([s["id"] for s in wf["steps"]].count("plan"), 1)
            code = [s for s in wf["steps"] if s["writes_code"]]
            self.assertEqual(len(code), 1)
            self.assertEqual(code[0]["gate"], "approve")
            self.assertTrue(all(s["instructions"] for s in wf["steps"]))

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

    def test_start_creates_run_with_own_copy(self):
        card = os.path.join(tempfile.mkdtemp(), "ABC-1")
        workflow.start("bugfix", card)
        s = desk.load(card)
        self.assertEqual((s["workflow"], s["current"]), ("bugfix", "triage"))
        self.assertTrue(os.path.isfile(os.path.join(card, "workflow.md")))
        self.assertNotIn("instructions", s["steps"][0])

    def test_list_cli(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "workflow.py"), "list"],
                             capture_output=True, text=True, check=True).stdout
        self.assertIn("bugfix:", out)
        self.assertIn("task:", out)


if __name__ == "__main__":
    unittest.main()
