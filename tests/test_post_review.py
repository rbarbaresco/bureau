import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POST = os.path.join(ROOT, "scripts", "post_review.py")
STEPS = [{"id": "review", "gate": "approve"}, {"id": "draft", "gate": "approve"}]
# stand-in for `gh`: `pr view` prints $T/head; the review post logs its args to $T/calls and its stdin to $T/payload
FAKE_GH = """#!/bin/sh
case "$1 $2" in
  "pr view") cat "$T/head" ;;
  *) [ -f "$T/fail" ] && exit 1
     echo "$@" >> "$T/calls"; cat > "$T/payload"; echo "https://github.com/o/r/pull/7#pullrequestreview-1" ;;
esac
exit 0
"""
DRAFT = {"repo": "o/r", "number": 7, "commit_id": "abc123", "event": "COMMENT", "body": "Looks close.",
         "comments": [{"path": "app.py", "line": 3, "body": "Off by one here."}]}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class PostReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.card = os.path.join(self.tmp, "desk", "bureau-7")
        self.state(current="draft", awaiting="draft")
        self.approve(review=True, draft=True)
        self.draft(DRAFT)
        write(os.path.join(self.tmp, "head"), "abc123\n")
        write(os.path.join(self.tmp, "bin", "gh"), FAKE_GH)
        os.chmod(os.path.join(self.tmp, "bin", "gh"), 0o755)

    def state(self, **s):
        write(os.path.join(self.card, "state.json"), json.dumps({"card": "bureau-7", "steps": STEPS, **s}))

    def approve(self, **a):
        write(os.path.join(self.card, "approvals.json"), json.dumps(a))

    def draft(self, d):
        write(os.path.join(self.card, "draft.json"), json.dumps(d))

    def saved(self):
        with open(os.path.join(self.card, "draft.json")) as f:
            return json.load(f)

    def post(self):
        env = {**os.environ, "PATH": os.path.join(self.tmp, "bin") + os.pathsep + os.environ["PATH"], "T": self.tmp}
        return subprocess.run([sys.executable, POST, self.card], env=env, capture_output=True, text=True)

    def calls(self):
        try:
            with open(os.path.join(self.tmp, "calls")) as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def test_posts_one_review_and_records_it(self):
        r = self.post()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("api repos/o/r/pulls/7/reviews", self.calls())
        with open(os.path.join(self.tmp, "payload")) as f:
            payload = json.load(f)
        self.assertEqual(payload["commit_id"], "abc123")
        self.assertEqual(payload["event"], "COMMENT")
        self.assertEqual(payload["comments"], DRAFT["comments"])
        self.assertNotIn("repo", payload)
        self.assertEqual(self.saved()["posted"], "https://github.com/o/r/pull/7#pullrequestreview-1")

    def test_second_run_posts_nothing(self):
        self.post()
        before = self.calls()
        r = self.post()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already posted", r.stdout)
        self.assertEqual(self.calls(), before)

    def test_done_card_can_repair_a_failed_post(self):
        self.state(current="done")
        self.assertEqual(self.post().returncode, 0)
        self.assertIn("reviews", self.calls())

    def test_refuses_without_approval_or_awaiting(self):
        self.approve(review=True)
        self.assertIn("not approved", self.post().stderr)
        self.approve(review=True, draft=True)
        self.state(current="review", awaiting="review")
        self.assertIn("not awaiting", self.post().stderr)
        self.assertEqual(self.calls(), "")

    def test_refuses_when_the_head_moved(self):
        write(os.path.join(self.tmp, "head"), "def456\n")
        r = self.post()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("def456", r.stderr)
        self.assertEqual(self.calls(), "")

    def test_bad_draft_is_rejected_before_anything_posts(self):
        bad = [{}, {**DRAFT, "event": "MERGE"}, {**DRAFT, "commit_id": ""}, {**DRAFT, "number": "7"},
               {**DRAFT, "body": "", "comments": []}, {**DRAFT, "comments": [{"path": "a.py", "body": "x"}]},
               {**DRAFT, "comments": [{"path": "a.py", "line": 1, "body": " "}]}, [DRAFT]]
        for d in bad:
            self.draft(d)
            r = self.post()
            self.assertNotEqual(r.returncode, 0, d)
            self.assertIn("draft.json", r.stderr, d)
        os.remove(os.path.join(self.card, "draft.json"))
        self.assertIn("draft.json", self.post().stderr)
        self.assertEqual(self.calls(), "")

    def test_failed_post_leaves_it_unposted(self):
        write(os.path.join(self.tmp, "fail"), "")
        self.assertNotEqual(self.post().returncode, 0)
        self.assertNotIn("posted", self.saved())


if __name__ == "__main__":
    unittest.main()
