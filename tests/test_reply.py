import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPLY = os.path.join(ROOT, "scripts", "reply.py")
WORKTREE = os.path.join(ROOT, "scripts", "worktree.py")
STEPS = [{"id": "fix", "gate": "approve", "writes_code": True}, {"id": "reply", "gate": "approve"}]
# stand-in for `gh`: answers the two lookups, logs every other call (args, then stdin) to $T/calls
FAKE_GH = """#!/bin/sh
case "$1 $2" in
  "pr view") echo 7 ;;
  "repo view") echo o/r ;;
  *) echo "$@" >> "$T/calls"; [ "$1 $2" = "pr comment" ] && cat >> "$T/calls" ;;
esac
exit 0
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def git(path, *args):
    return subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout


class ReplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.origin, self.clone = os.path.join(self.tmp, "origin.git"), os.path.join(self.tmp, "clone")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.clone], check=True)
        git(self.clone, "remote", "add", "origin", self.origin)
        git(self.clone, "commit", "-q", "--allow-empty", "-m", "init")
        git(self.clone, "push", "-q", "origin", "main:feat/x")
        repos = os.path.join(self.tmp, "repos.yaml")
        write(repos, f"repos:\n  clone:\n    path: {self.clone}\n    base: main\n")
        self.card = os.path.join(self.tmp, "desk", "pr-7")
        write(os.path.join(self.card, "state.json"),
              json.dumps({"card": "pr-7", "current": "reply", "awaiting": "reply", "steps": STEPS}))
        self.wt = subprocess.run([sys.executable, WORKTREE, self.card, "clone", "--repos", repos, "--branch", "feat/x"],
                                 check=True, capture_output=True, text=True).stdout.splitlines()[-1]
        write(os.path.join(self.wt, "app.py"), "x\n")
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-qm", "fix")
        self.approve(reply=True)
        write(os.path.join(self.card, "reply.json"), json.dumps(
            [{"in_reply_to": 11, "body": "Fixed in abc"}, {"in_reply_to": None, "body": "Thanks all"}]))
        self.bin = os.path.join(self.tmp, "bin")
        write(os.path.join(self.bin, "gh"), FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)

    def approve(self, **a):
        write(os.path.join(self.card, "approvals.json"), json.dumps(a))

    def run_reply(self):
        env = {**os.environ, "PATH": self.bin + os.pathsep + os.environ["PATH"], "T": self.tmp}
        return subprocess.run([sys.executable, REPLY, self.card], env=env, capture_output=True, text=True)

    def calls(self):
        try:
            with open(os.path.join(self.tmp, "calls")) as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def test_pushes_and_posts_inline_and_top_level(self):
        r = self.run_reply()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("fix", git(self.origin, "log", "--format=%s", "feat/x"))
        self.assertIn("api repos/o/r/pulls/7/comments/11/replies -f body=Fixed in abc", self.calls())
        self.assertIn("pr comment 7 --body-file -\nThanks all", self.calls())
        self.assertNotIn("resolve", self.calls())

    def test_rerun_skips_posted_replies(self):
        self.run_reply()
        self.run_reply()
        self.assertEqual(self.calls().count("Fixed in abc"), 1)

    def test_refused_cases(self):
        self.approve()
        self.assertIn("not approved", self.run_reply().stderr)
        self.approve(reply=True)
        write(os.path.join(self.wt, "dirty.py"), "x\n")
        self.assertIn("uncommitted", self.run_reply().stderr)
        os.remove(os.path.join(self.wt, "dirty.py"))
        os.remove(os.path.join(self.card, "reply.json"))
        self.assertIn("reply.json", self.run_reply().stderr)
        write(os.path.join(self.card, "state.json"),
              json.dumps({"card": "pr-7", "current": "fix", "awaiting": "fix", "steps": STEPS}))
        self.assertIn("not awaiting", self.run_reply().stderr)
        self.assertEqual(self.calls(), "")


if __name__ == "__main__":
    unittest.main()
