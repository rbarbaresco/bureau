import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REWORK = os.path.join(ROOT, "scripts", "rework.py")
# stand-in for `gh`: `pr list` / `pr view` / `api` print $T/list, $T/view, $T/threads (a missing file fails the call)
FAKE_GH = """#!/bin/sh
echo "$@" >> "$T/calls"
case "$1 $2" in
  "pr list") cat "$T/list" ;;
  "pr view") cat "$T/view" ;;
  "api graphql") cat "$T/threads" ;;
  *) exit 1 ;;
esac
"""
PR = {"url": "https://example.test/pull/7", "number": 7, "state": "OPEN"}
VIEW = {"author": {"login": "me"}, "commits": [{"committedDate": "2026-01-02T00:00:00Z"}], "reviews": [], "comments": []}


def threads(*nodes):
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {"totalCount": len(nodes), "nodes": list(nodes)}}}}}


def thread(resolved=False, replied=False):
    nodes = [{"databaseId": 11, "author": {"login": "bob"}, "body": "rename this", "url": "u", "createdAt": "2026-01-03T00:00:00Z"}]
    if replied:
        nodes.append({"databaseId": 12, "author": {"login": "me"}, "body": "done", "url": "u2", "createdAt": "2026-01-04T00:00:00Z"})
    return {"isResolved": resolved, "isOutdated": False, "path": "a.py", "line": 3, "comments": {"totalCount": len(nodes), "nodes": nodes}}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class ReworkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.card = os.path.join(self.tmp, "desk", "ABC-1")
        write(os.path.join(self.card, "state.json"), json.dumps({"card": "ABC-1", "current": "done", "steps": [{"id": "pr"}]}))
        write(os.path.join(self.card, "pr.md"), "# Title\n\nBody\n\n## Opened\n\nhttps://example.test/pull/7\n")
        os.makedirs(os.path.join(self.card, "worktrees", "clone"))
        self.put("list", [PR])
        self.put("view", VIEW)
        self.put("threads", threads(thread()))
        self.bin = os.path.join(self.tmp, "bin")
        write(os.path.join(self.bin, "gh"), FAKE_GH)
        os.chmod(os.path.join(self.bin, "gh"), 0o755)
        self.repos = os.path.join(self.tmp, "repos.yaml")
        write(self.repos, "repos:\n")

    def put(self, name, data):
        write(os.path.join(self.tmp, name), json.dumps(data))

    def run_rework(self, card=None):
        env = {**os.environ, "PATH": self.bin + os.pathsep + os.environ["PATH"], "T": self.tmp, "BUREAU_REPOS": self.repos}
        return subprocess.run([sys.executable, REWORK, card or self.card], env=env, capture_output=True, text=True)

    def refused(self, *needles):
        r = self.run_rework()
        self.assertNotEqual(r.returncode, 0, r.stdout)
        for n in needles:
            self.assertIn(n, r.stderr)

    def test_prints_unresolved_threads_for_an_open_pr(self):
        r = self.run_rework()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["pr"]["number"], 7)
        self.assertEqual(out["repo"], "clone")
        self.assertEqual(out["threads"][0]["comments"]["nodes"][0]["body"], "rename this")

    def test_graphql_call_uses_the_gh_placeholders_and_thread_comment_ids(self):
        self.run_rework()
        calls = self.read("calls")
        self.assertIn("api graphql", calls)
        self.assertIn("owner={owner}", calls)
        self.assertIn("repo={repo}", calls)
        self.assertIn("databaseId", calls)

    def read(self, name):
        with open(os.path.join(self.tmp, name)) as f:
            return f.read()

    def test_reopened_card_in_a_rework_step_can_fetch_again(self):
        for step in ("feedback", "apply", "rework-review-2"):
            write(os.path.join(self.card, "state.json"), json.dumps({"card": "ABC-1", "current": step, "steps": [{"id": step}]}))
            self.assertEqual(self.run_rework().returncode, 0, step)

    def test_thread_the_author_spoke_last_in_is_flagged_and_still_feedback(self):
        self.put("threads", threads(thread(replied=True), thread()))
        out = json.loads(self.run_rework().stdout)
        self.assertEqual([t["author_last"] for t in out["threads"]], [True, False])

    def test_author_only_replying_will_do_still_starts_a_rework(self):
        self.put("threads", threads(thread(replied=True)))
        self.assertEqual(self.run_rework().returncode, 0)

    def test_truncated_thread_does_not_claim_the_author_spoke_last(self):
        t = thread(replied=True)
        t["comments"]["totalCount"] = 25
        self.put("threads", threads(t))
        self.assertFalse(json.loads(self.run_rework().stdout)["threads"][0]["author_last"])

    def test_new_top_level_comment_carries_its_url(self):
        self.put("view", {**VIEW, "comments": [{"author": {"login": "bob"}, "body": "also this", "createdAt": "2026-01-05T00:00:00Z", "url": "c"}]})
        self.assertEqual(json.loads(self.run_rework().stdout)["comments"][0]["url"], "c")

    def test_deleted_account_comment_does_not_crash(self):
        self.put("view", {**VIEW, "comments": [{"author": None, "body": "ghost", "createdAt": "2026-01-05T00:00:00Z"}]})
        self.assertEqual(self.run_rework().returncode, 0)

    def test_an_open_pr_is_preferred_over_an_older_merged_one_on_the_same_branch(self):
        self.put("list", [{**PR, "state": "MERGED", "number": 3}, PR])
        self.assertEqual(json.loads(self.run_rework().stdout)["pr"]["number"], 7)

    def test_refuses_without_a_local_card(self):
        r = self.run_rework(os.path.join(self.tmp, "desk", "NOPE-1"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("/work", r.stderr)

    def test_refuses_a_card_still_in_progress(self):
        write(os.path.join(self.card, "state.json"), json.dumps({"card": "ABC-1", "current": "build", "steps": [{"id": "build"}]}))
        self.refused("build", "/work ABC-1")

    def test_refuses_when_no_pr_was_opened(self):
        write(os.path.join(self.card, "pr.md"), "# Title\n\nBody\n")
        self.refused("No PR was opened", "/work ABC-1")

    def test_refuses_when_worktree_and_branch_are_gone(self):
        os.rmdir(os.path.join(self.card, "worktrees", "clone"))
        self.refused("Worktree")

    def test_branch_without_worktree_names_the_repo_to_recreate_it(self):
        os.rmdir(os.path.join(self.card, "worktrees", "clone"))
        clone = os.path.join(self.tmp, "clone")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        subprocess.run(["git", "-C", clone, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"], check=True)
        subprocess.run(["git", "-C", clone, "branch", "bureau/ABC-1"], check=True)
        write(self.repos, f"repos:\n  clone:\n    path: {clone}\n")
        r = self.run_rework()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["repo"], "clone")

    def test_refuses_a_merged_pr(self):
        self.put("list", [{**PR, "state": "MERGED"}])
        self.refused("MERGED", "example.test/pull/7")

    def test_refuses_when_there_is_no_pr_for_the_branch(self):
        self.put("list", [])
        self.refused("No PR found")

    def test_refuses_when_gh_fails(self):
        os.remove(os.path.join(self.tmp, "list"))
        self.refused("failed")

    def test_refuses_when_everything_is_resolved(self):
        self.put("threads", threads(thread(resolved=True)))
        self.refused("no review to check", "example.test/pull/7")

    def test_a_review_comment_after_the_last_commit_counts(self):
        self.put("threads", threads())
        self.put("view", {**VIEW, "reviews": [{"author": {"login": "bob"}, "body": "please add a test", "submittedAt": "2026-01-03T00:00:00Z"}]})
        self.assertEqual(self.run_rework().returncode, 0)

    def test_comments_before_the_last_commit_or_by_the_author_do_not(self):
        self.put("threads", threads())
        self.put("view", {**VIEW, "comments": [
            {"author": {"login": "bob"}, "body": "old", "createdAt": "2026-01-01T00:00:00Z"},
            {"author": {"login": "me"}, "body": "mine", "createdAt": "2026-01-03T00:00:00Z"}]})
        self.refused("no review to check")


if __name__ == "__main__":
    unittest.main()
