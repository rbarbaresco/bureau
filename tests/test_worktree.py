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

    def test_missing_repos_file_says_how_to_create_it(self):
        missing = os.path.join(tempfile.mkdtemp(), "repos.yaml")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "worktree.py"), "desk/A-1", "clone",
                            "--repos", missing], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn(f"cp {os.path.join(ROOT, 'repos.yaml.sample')} {missing}", r.stderr)


if __name__ == "__main__":
    unittest.main()
