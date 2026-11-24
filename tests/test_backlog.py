"""Bureau's backlog view and hit log (#129): short versions only, refreshed daily, hits counted, comments opt-in."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import backlog  # noqa: E402
import desk  # noqa: E402

ISSUES = [{"number": 111, "title": "Gate friction", "labels": [{"name": "enhancement"}],
           "body": "**Short:** The gate denies reads.\r\nFix it.\r\n\r\n## Problem\nlong text " + "x" * 5000},
          {"number": 109, "title": "Rethink project", "labels": [], "body": "## Problem\nno short version"}]


def run_ok(stdout=""):
    return subprocess.CompletedProcess([], 0, stdout, "")


class ShortTest(unittest.TestCase):
    def test_marker_at_top(self):
        self.assertEqual(backlog.short("**Short:** one\ntwo\n\n## Problem\nbody"), "one\ntwo")

    def test_no_marker_or_not_at_top(self):
        self.assertEqual(backlog.short("## Problem\nbody"), "")
        self.assertEqual(backlog.short("intro\n\n**Short:** late"), "")
        self.assertEqual(backlog.short(None), "")

    def test_stops_at_a_heading_without_a_blank_line(self):
        self.assertEqual(backlog.short("**Short:** a\n## Problem\nlong"), "a")
        self.assertEqual(backlog.short("**Short:** a\n**Problem**\nlong"), "a")
        self.assertEqual(backlog.short("**Short:** a\n#111 covers part."), "a\n#111 covers part.")

    def test_capped_at_three_lines(self):
        self.assertEqual(backlog.short("**Short:** a\nb\nc\nd\ne"), "a\nb\nc")
        self.assertLessEqual(len(backlog.short("**Short:** " + "y" * 2000)), 400)


class ViewTest(unittest.TestCase):
    def setUp(self):
        self.desk = tempfile.mkdtemp()
        self.path = os.path.join(self.desk, "backlog.md")

    def test_missing_view_is_built_from_short_versions_only(self):
        with mock.patch.object(subprocess, "run", return_value=run_ok(json.dumps(ISSUES))) as run:
            out = backlog.view(self.desk)
        self.assertEqual(run.call_args.kwargs["cwd"], backlog.ROOT)
        self.assertIn("#111 Gate friction [labels: enhancement]\n  The gate denies reads.\n  Fix it.\n#109 Rethink project\n", out)
        self.assertNotIn("long text", out)

    def test_fresh_view_is_not_refetched(self):
        with open(self.path, "w") as f:
            f.write("#1 cached\n")
        with mock.patch.object(subprocess, "run") as run:
            self.assertEqual(backlog.view(self.desk), "#1 cached\n")
        run.assert_not_called()

    def test_stale_view_is_refreshed_and_kept_when_gh_fails(self):
        with open(self.path, "w") as f:
            f.write("#1 cached\n")
        later = time.time() + 3 * backlog.DAY
        with mock.patch.object(subprocess, "run", return_value=run_ok(json.dumps(ISSUES))):
            self.assertIn("#111", backlog.view(self.desk, now=later))
        failed = subprocess.CompletedProcess([], 1, "", "HTTP 502")
        with mock.patch.object(subprocess, "run", return_value=failed):
            out = backlog.view(self.desk, now=later)
        self.assertIn("refreshing failed: HTTP 502", out)
        self.assertIn("#111", out)

    def test_no_view_and_gh_down_does_not_raise(self):
        with mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 60)):
            self.assertIn("unavailable", backlog.view(self.desk))
            self.assertIn("unavailable", backlog.summary(self.desk))

    def test_unexpected_json_is_not_cached(self):
        for bad in ("null", "{}", "[1]"):
            with mock.patch.object(subprocess, "run", return_value=run_ok(bad)):
                self.assertIn("unavailable", backlog.view(self.desk))
            self.assertFalse(os.path.exists(self.path))

    def test_titles_drop_labels(self):
        self.assertEqual(backlog.titles("x\n#5 A [b] c [labels: bug,enhancement]\n  short\n#6 Fix parser [WIP]"),
                         {"5": "A [b] c", "6": "Fix parser [WIP]"})


class HitTest(unittest.TestCase):
    def setUp(self):
        self.desk = tempfile.mkdtemp()
        self.card = os.path.join(self.desk, "skills-14")
        desk.init(self.card, [{"id": "plan", "gate": "approve"}], settings={"issue_comments": "off"})
        with open(os.path.join(self.desk, "backlog.md"), "w") as f:
            f.write("Bureau's open issues:\n#111 Gate friction\n  short\n#109 Rethink project\n")

    def hits(self):
        with open(os.path.join(self.desk, "backlog-hits.jsonl")) as f:
            return [json.loads(line) for line in f]

    def set_comments(self, value):
        s = desk.load(self.card)
        s["settings"]["issue_comments"] = value
        desk.save(self.card, s)

    def test_hit_is_logged_without_a_tracker_write_by_default(self):
        with mock.patch.object(subprocess, "run") as run:
            backlog.hit("111", self.card, "sed -n denied", self.desk, today="2026-11-24")
        run.assert_not_called()
        self.assertEqual(self.hits(), [{"issue": 111, "card": "skills-14", "date": "2026-11-24", "what": "sed -n denied"}])

    def test_comment_only_when_the_card_setting_is_on(self):
        self.set_comments("on")
        with mock.patch.object(subprocess, "run", return_value=run_ok()) as run:
            backlog.hit("#111", self.card, "sed -n denied on private/path", self.desk, today="2026-11-24")
        self.assertEqual(run.call_args.args[0],  # another repo's card: no card id or free text on Bureau's repo
                         ["gh", "issue", "comment", "111", "--body", "Hit again (2026-11-24) on a card outside Bureau."])
        cases = {("bureau",): "Hit again on c: sed -n denied",  # only Bureau's worktree: id and text
                 ("bureau", "billing"): "Hit again (2026-11-24) on a card outside Bureau.",
                 ("billing",): "Hit again (2026-11-24) on a card outside Bureau.",  # a `bureau-` slug is not enough
                 (): "Hit again (2026-11-24) on a card outside Bureau."}
        for i, (wts, body) in enumerate(cases.items()):
            card = os.path.join(self.desk, f"bureau-{i}", "c")
            desk.init(card, [{"id": "plan", "gate": "approve"}], settings={"issue_comments": "on"})
            for w in wts:
                os.makedirs(os.path.join(card, "worktrees", w))
            with mock.patch.object(subprocess, "run", return_value=run_ok()) as run:
                backlog.hit("111", card, "sed -n denied", self.desk, today="2026-11-24")
            self.assertEqual(run.call_args.args[0][-1], body, wts)

    def test_no_view_offline_still_logs_and_posts_nothing(self):
        self.set_comments("on")
        os.remove(os.path.join(self.desk, "backlog.md"))
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("gh")) as run:
            msg = backlog.hit("111", self.card, "x", self.desk)
        self.assertEqual(run.call_count, 1)  # the failed refresh, no comment
        self.assertIn("nothing was posted", msg)
        self.assertEqual(len(self.hits()), 1)
        open(os.path.join(self.desk, "backlog.md"), "w").close()  # an empty, truncated view: no IndexError
        with mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("gh")):
            backlog.hit("111", self.card, "x", self.desk)
        self.assertEqual(len(self.hits()), 2)

    def test_issue_not_in_the_view_is_refused(self):
        with mock.patch.object(subprocess, "run") as run, self.assertRaises(ValueError):
            backlog.hit("131", self.card, "x", self.desk)
        run.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.desk, "backlog-hits.jsonl")))

    def test_template_offers_the_setting_hit_reads(self):
        with open(os.path.join(ROOT, "bureau.template.json")) as f:
            q = next(q for q in json.load(f) if q["key"] == "issue_comments")
        self.assertEqual([v for v, _ in q["options"]], ["off", "on"])
        self.assertEqual(q["suggest"], "off")

    def test_failed_comment_keeps_the_log_line(self):
        self.set_comments("on")
        with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "offline")):
            msg = backlog.hit("111", self.card, "x", self.desk)
        self.assertIn("failed: offline", msg)
        self.assertEqual(len(self.hits()), 1)

    def test_not_a_card(self):
        with self.assertRaises(ValueError):
            backlog.hit("111", os.path.join(self.desk, "nope"), "x", self.desk)

    def test_summary_ranks_open_issues_and_drops_closed_ones(self):
        for n in (109, 111, 111):
            backlog.hit(str(n), self.card, "x", self.desk)
        with open(os.path.join(self.desk, "backlog-hits.jsonl"), "a") as f:
            f.write('{"issue": 42, "card": "c"}\n{"issue": 1')  # an issue closed since, and a torn line
        out = backlog.summary(self.desk).splitlines()
        self.assertEqual(out[0], "  2  #111 Gate friction (last: skills-14)")
        self.assertEqual(out[1], "  1  #109 Rethink project (last: skills-14)")
        self.assertNotIn("#42", "\n".join(out))
        self.assertEqual(out[-1], "0 open issue(s) with no hits logged.")


if __name__ == "__main__":
    unittest.main()
