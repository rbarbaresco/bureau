import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import worktree  # noqa: E402


class WorktreeTest(unittest.TestCase):
    def test_coverage_files_are_ignored_once_per_clone(self):
        tmp = tempfile.mkdtemp()
        clone = os.path.join(tmp, "clone")
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        subprocess.run(["git", "-C", clone, "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        repos = os.path.join(tmp, "repos.yaml")
        with open(repos, "w") as f:
            f.write(f"repos:\n  clone:\n    path: {clone}\n    base: main\n")
        for card in ("A-1", "A-2"):
            wt = worktree.add(os.path.join(tmp, "desk", card), "clone", repos)
            for name in (".coverage", ".coverage.host.1.x"):
                open(os.path.join(wt, name), "w").close()
            status = subprocess.run(["git", "-C", wt, "status", "--short"], capture_output=True, text=True).stdout
            self.assertEqual(status, "")
        exclude = open(os.path.join(clone, ".git", "info", "exclude")).read().splitlines()
        self.assertEqual((exclude.count(".coverage"), exclude.count(".coverage.*")), (1, 1))

    def test_branch_flag_checks_out_the_remote_branch_with_upstream(self):
        tmp = tempfile.mkdtemp()
        origin, clone = os.path.join(tmp, "origin.git"), os.path.join(tmp, "clone")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", clone], check=True)
        g = ["git", "-C", clone, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(g + ["remote", "add", "origin", origin], check=True)
        subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "init"], check=True)
        subprocess.run(g + ["push", "-q", "origin", "main:feat/x"], check=True)
        repos = os.path.join(tmp, "repos.yaml")
        with open(repos, "w") as f:
            f.write(f"repos:\n  clone:\n    path: {clone}\n    base: main\n")
        wt = worktree.add(os.path.join(tmp, "desk", "pr-7"), "clone", repos, branch="feat/x")
        out = lambda *a: subprocess.run(["git", "-C", wt, *a], capture_output=True, text=True).stdout.strip()
        self.assertEqual(out("rev-parse", "--abbrev-ref", "HEAD"), "feat/x")
        self.assertEqual(out("rev-parse", "--abbrev-ref", "@{u}"), "origin/feat/x")
        self.assertNotIn("bureau/pr-7", out("branch"))

    def stale_clone(self):
        """A clone whose checked-out main is one commit behind origin/main; returns (tmp, clone, repos, origin tip)."""
        tmp = tempfile.mkdtemp()
        origin, clone, other = (os.path.join(tmp, n) for n in ("origin.git", "clone", "other"))
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        git = lambda *a: subprocess.run(["git", *a], check=True, env=env, capture_output=True, text=True).stdout.strip()
        git("init", "-q", "--bare", "-b", "main", origin)
        git("init", "-q", "-b", "main", clone)
        git("-C", clone, "remote", "add", "origin", origin)
        open(os.path.join(clone, "f"), "w").write("old\n")
        git("-C", clone, "add", "f")
        git("-C", clone, "commit", "-q", "-m", "old")
        git("-C", clone, "push", "-q", "origin", "main")
        git("clone", "-q", origin, other)
        git("-C", other, "commit", "-q", "--allow-empty", "-m", "new")
        git("-C", other, "push", "-q", "origin", "main")
        repos = os.path.join(tmp, "repos.yaml")
        with open(repos, "w") as f:
            f.write(f"repos:\n  clone:\n    path: {clone}\n    base: main\n")
        return tmp, clone, repos, git("-C", other, "rev-parse", "HEAD")

    def rev(self, repo, ref):
        return subprocess.run(["git", "-C", repo, "rev-parse", ref], capture_output=True, text=True).stdout.strip()

    def test_new_card_starts_from_the_remote_base_and_fast_forwards_a_clean_clone(self):
        tmp, clone, repos, tip = self.stale_clone()
        wt = worktree.add(os.path.join(tmp, "desk", "A-1"), "clone", repos)
        self.assertEqual(self.rev(wt, "HEAD"), tip)
        self.assertEqual(self.rev(clone, "main"), tip)
        upstream = subprocess.run(["git", "-C", wt, "rev-parse", "--abbrev-ref", "@{u}"], capture_output=True)
        self.assertNotEqual(upstream.returncode, 0)  # pr.py sets it with push -u

    def test_base_not_checked_out_in_the_clone_is_fast_forwarded_too(self):
        tmp, clone, repos, tip = self.stale_clone()
        subprocess.run(["git", "-C", clone, "switch", "-q", "-c", "other"], check=True)
        worktree.add(os.path.join(tmp, "desk", "A-1"), "clone", repos)
        self.assertEqual(self.rev(clone, "main"), tip)

    def test_dirty_clone_keeps_its_local_base_but_the_card_still_starts_from_the_remote(self):
        tmp, clone, repos, tip = self.stale_clone()
        old = self.rev(clone, "main")
        open(os.path.join(clone, "f"), "w").write("edited\n")
        wt = worktree.add(os.path.join(tmp, "desk", "A-1"), "clone", repos)
        self.assertEqual(self.rev(wt, "HEAD"), tip)
        self.assertEqual(self.rev(clone, "main"), old)
        self.assertEqual(open(os.path.join(clone, "f")).read(), "edited\n")

    def test_missing_repos_file_says_how_to_create_it(self):
        missing = os.path.join(tempfile.mkdtemp(), "repos.yaml")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "worktree.py"), "desk/A-1", "clone",
                            "--repos", missing], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn(f"cp {os.path.join(ROOT, 'repos.yaml.sample')} {missing}", r.stderr)


if __name__ == "__main__":
    unittest.main()
