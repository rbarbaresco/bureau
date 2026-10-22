import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PR = os.path.join(ROOT, "scripts", "pr.py")
WORKTREE = os.path.join(ROOT, "scripts", "worktree.py")
STEPS = [{"id": "build", "gate": "approve", "writes_code": True}, {"id": "pr", "gate": "approve"}]
# stand-in for `gh`: `pr list` prints $T/list, `pr create` records its args and stdin and prints a URL
FAKE_GH = """#!/bin/sh
case "$2" in
  list) cat "$T/list" 2>/dev/null || true ;;
  create) echo "$@" > "$T/args"; cat > "$T/body"; echo https://example.test/pull/7 ;;
esac
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def git(path, *args):
    return subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout


class PrTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        origin, self.clone = os.path.join(self.tmp, "origin.git"), os.path.join(self.tmp, "clone")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "develop", origin], check=True)
        subprocess.run(["git", "init", "-q", "-b", "develop", self.clone], check=True)
        git(self.clone, "remote", "add", "origin", origin)
        git(self.clone, "commit", "-q", "--allow-empty", "-m", "init")
        self.repos = os.path.join(self.tmp, "repos.yaml")
        write(self.repos, f"repos:\n  clone:\n    path: {self.clone}\n    base: develop\n")
        self.card = os.path.join(self.tmp, "desk", "ABC-1")
        write(os.path.join(self.card, "state.json"),
              json.dumps({"card": "ABC-1", "current": "pr", "awaiting": "pr", "steps": STEPS}))
        self.wt = subprocess.run([sys.executable, WORKTREE, self.card, "clone", "--repos", self.repos],
                                 check=True, capture_output=True, text=True).stdout.splitlines()[-1]
        write(os.path.join(self.wt, "app.py"), "x\n")
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "work")
        write(os.path.join(self.card, "pr.md"), "# Add app\n\nBody line.\n")
        self.approve(pr=True)
        self.bin = os.path.join(self.tmp, "bin")
        write(os.path.join(self.bin, "gh"), FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)

    def approve(self, **a):
        write(os.path.join(self.card, "approvals.json"), json.dumps(a))

    def run_pr(self):
        env = {**os.environ, "PATH": self.bin + os.pathsep + os.environ["PATH"], "T": self.tmp, "BUREAU_REPOS": self.repos}
        return subprocess.run([sys.executable, PR, self.card], env=env, capture_output=True, text=True)

    def read(self, name):
        with open(os.path.join(self.tmp, name)) as f:
            return f.read()

    def test_pushes_creates_draft_against_repo_base_and_records_link(self):
        r = self.run_pr()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("https://example.test/pull/7", r.stdout)
        args = self.read("args")
        for want in ("--draft", "--base develop", "--head bureau/ABC-1", "--title Add app", "--body-file -"):
            self.assertIn(want, args)
        self.assertEqual(self.read("body"), "Body line.\n")
        self.assertIn("bureau/ABC-1", git(os.path.join(self.tmp, "origin.git"), "branch"))
        md = open(os.path.join(self.card, "pr.md")).read()
        self.assertTrue(md.startswith("# Add app\n\nBody line.\n"))
        self.assertIn("## Opened\n\nhttps://example.test/pull/7", md)

    def test_existing_pr_is_reused(self):
        write(os.path.join(self.tmp, "list"), "https://example.test/pull/3\n")
        r = self.run_pr()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "args")))
        self.assertIn("https://example.test/pull/3", open(os.path.join(self.card, "pr.md")).read())

    def test_rerun_after_opened_does_not_duplicate_link(self):
        self.run_pr()
        self.run_pr()
        self.assertEqual(open(os.path.join(self.card, "pr.md")).read().count("## Opened"), 1)

    def test_refused_cases(self):
        self.approve()
        self.assertIn("not approved", self.run_pr().stderr)
        self.approve(pr=True)
        write(os.path.join(self.wt, "dirty.py"), "x\n")
        self.assertIn("uncommitted", self.run_pr().stderr)
        os.remove(os.path.join(self.wt, "dirty.py"))
        write(os.path.join(self.card, "pr.md"), "\n")
        self.assertIn("pr.md", self.run_pr().stderr)
        write(os.path.join(self.card, "state.json"),
              json.dumps({"card": "ABC-1", "current": "build", "awaiting": "build", "steps": STEPS}))
        self.assertIn("not awaiting", self.run_pr().stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "args")))


if __name__ == "__main__":
    unittest.main()
