import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import trial  # noqa: E402

G = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]


class TrialTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.main = os.path.join(self.tmp, "bureau")
        subprocess.run(["git", "init", "-q", "-b", "main", self.main], check=True)
        subprocess.run(G + ["-C", self.main, "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        subprocess.run(["git", "-C", self.main, "branch", "bureau/x"], check=True)
        os.makedirs(os.path.join(self.main, "desk"))
        open(os.path.join(self.main, "repos.yaml"), "w").close()

    def test_branch_checked_out_elsewhere_gets_a_detached_checkout_on_the_real_desk(self):
        busy = os.path.join(self.tmp, "card")  # the branch is taken, like a card worktree
        subprocess.run(["git", "-C", self.main, "worktree", "add", "-q", busy, "bureau/x"], check=True)
        dest = trial.add("bureau/x", self.main)
        self.assertEqual(dest, os.path.join(self.tmp, "bureau-trial-bureau-x"))
        head = subprocess.run(["git", "-C", dest, "symbolic-ref", "-q", "HEAD"], capture_output=True)
        self.assertNotEqual(head.returncode, 0)  # detached
        for name in ("desk", "repos.yaml"):
            self.assertEqual(os.path.realpath(os.path.join(dest, name)), os.path.realpath(os.path.join(self.main, name)))

    def test_existing_destination_is_refused(self):
        os.makedirs(os.path.join(self.tmp, "bureau-trial-main"))
        with self.assertRaises(SystemExit):
            trial.add("main", self.main)


if __name__ == "__main__":
    unittest.main()
