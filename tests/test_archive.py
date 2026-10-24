import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import archive  # noqa: E402


def git(*args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clone = os.path.join(self.tmp, "clone")
        remote = os.path.join(self.tmp, "remote.git")
        git("init", "-q", "-b", "main", self.clone)
        git("-C", self.clone, "commit", "-q", "--allow-empty", "-m", "init")
        git("init", "-q", "--bare", remote)
        git("-C", self.clone, "remote", "add", "origin", remote)
        self.desk = os.path.join(self.tmp, "desk")

    def card(self, cid="A-1", current="done", worktree=True, push=True):
        d = os.path.join(self.desk, cid)
        os.makedirs(d)
        with open(os.path.join(d, "state.json"), "w") as f:
            json.dump({"current": current}, f)
        if worktree:
            wt = os.path.join(d, "worktrees", "clone")
            git("-C", self.clone, "worktree", "add", "-q", "-b", "bureau/" + cid, wt, "main")
            if push:
                git("-C", wt, "push", "-q", "-u", "origin", "bureau/" + cid)
        return d

    def refused(self, d):
        with self.assertRaises(SystemExit):
            archive.archive(d)
        self.assertTrue(os.path.isdir(d))

    def test_moves_card_and_removes_worktree(self):
        d = self.card()
        dest = archive.archive(d)
        self.assertEqual(dest, os.path.join(self.tmp, "archive", "A-1"))
        self.assertFalse(os.path.exists(d))
        self.assertTrue(os.path.exists(os.path.join(dest, "state.json")))
        self.assertFalse(os.path.exists(os.path.join(dest, "worktrees")))
        listing = subprocess.run(["git", "-C", self.clone, "worktree", "list"], capture_output=True, text=True).stdout
        self.assertNotIn("A-1", listing)

    def test_card_without_worktree(self):  # e.g. a card that only produced a Confluence page
        archive.archive(self.card(worktree=False))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "archive", "A-1")))

    def test_refuses_not_done_and_no_state(self):
        self.refused(self.card(current="build"))
        os.makedirs(os.path.join(self.desk, "B-1"))
        self.refused(os.path.join(self.desk, "B-1"))

    def test_refuses_dirty_and_unpushed(self):
        d = self.card("A-2")
        open(os.path.join(d, "worktrees", "clone", "new.txt"), "w").close()
        self.refused(d)
        d = self.card("A-3", push=False)
        self.refused(d)
        d = self.card("A-4")
        git("-C", os.path.join(d, "worktrees", "clone"), "commit", "-q", "--allow-empty", "-m", "ahead")
        self.refused(d)

    def test_refuses_existing_archive_and_bad_id(self):
        d = self.card()
        os.makedirs(os.path.join(self.tmp, "archive", "A-1"))
        self.refused(d)
        with self.assertRaises(SystemExit):
            archive.archive(os.path.join(self.desk, ".."))

    def claimed(self, me):
        """A card claimed by a live process (the test runner's parent); `me` is the pid the script sees as its claude."""
        d = self.card(worktree=False)
        with open(os.path.join(d, "sessions.jsonl"), "w") as f:
            f.write(json.dumps({"event": "claim", "session": "s", "pid": os.getppid()}) + "\n")
        from archive import sessions
        sessions.NAME = sessions.comm(os.getppid())
        self.addCleanup(setattr, sessions, "NAME", "claude")
        os.environ["BUREAU_CLAUDE_PID"] = str(me)
        self.addCleanup(os.environ.pop, "BUREAU_CLAUDE_PID", None)
        return d

    def test_refuses_card_held_by_another_live_session(self):
        self.refused(self.claimed(me=1))

    def test_archives_card_held_by_my_own_session(self):
        archive.archive(self.claimed(me=os.getppid()))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "archive", "A-1")))


if __name__ == "__main__":
    unittest.main()
