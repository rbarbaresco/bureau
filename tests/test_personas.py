import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import workflow  # noqa: E402

PERSONAS = os.path.join(ROOT, "personas")


def frontmatter(path):
    text = open(path).read()
    assert text.startswith("---\n"), f"{path}: missing frontmatter"
    head = text[4:].split("\n---\n")[0]
    return {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in head.splitlines() if ":" in l)}


class PersonaTest(unittest.TestCase):
    def test_personas_valid(self):
        files = [f for f in os.listdir(PERSONAS) if f.endswith(".md")]
        self.assertGreaterEqual(len(files), 3)
        for f in files:
            m = frontmatter(os.path.join(PERSONAS, f))
            self.assertEqual(m.get("name"), f[:-3], f)
            self.assertTrue(m.get("description"), f)
            self.assertIn(m.get("mode"), ("read-only", "writer"), f)

    def test_workflow_personas_exist_and_code_steps_are_writers(self):
        for name in ("bugfix", "task", "small"):
            for s in workflow.parse(os.path.join(ROOT, "workflows", name + ".md"))["steps"]:
                p = os.path.join(PERSONAS, s["persona"] + ".md")
                self.assertTrue(os.path.isfile(p), f"{name}/{s['id']}: persona {s['persona']}")
                if s["writes_code"]:
                    self.assertEqual(frontmatter(p)["mode"], "writer")


if __name__ == "__main__":
    unittest.main()
