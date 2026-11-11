import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import voice_samples  # noqa: E402


def user(text, **extra):
    return {"type": "user", "message": {"role": "user", "content": text}, **extra}


def assistant(*parts):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": p} for p in parts]
                                                        + [{"type": "tool_use", "name": "Bash", "input": {}}]}}


class VoiceSamplesTest(unittest.TestCase):
    def setUp(self):
        self.config = tempfile.mkdtemp()
        self.write("-home-me-app", "s1", [
            assistant("Here is the PR body:", "## Summary\nLots of text."),
            user("too long, drop the headings"),
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ls output"}]}},
            user("<command-message>work</command-message>"),
            user("<system-reminder>hook said hi</system-reminder>"),
            user("Another Claude session sent this message"),
            user("injected", isMeta=True),
            user("summary of the chat", isCompactSummary=True),
            user("use this: <pasted_content id=1>secret log</pasted_content> but say it plainly"),
            user("<command-message>issue</command-message>\n<command-name>/issue</command-name>\n<command-args>file the flaky test</command-args>",
                 origin={"kind": "human"}),
            user("<command-message>approve</command-message>\n<command-name>/approve</command-name>\n<command-args></command-args>"),
            user("relayed from a teammate", origin={"kind": "peer"}),
            user("typed with origin", origin={"kind": "human"}),
            user("<command-name>/model</command-name>\n<command-args>sonnet</command-args>"),  # built-in: no origin
            {"type": "weird-new-record", "x": 1},
            "not even json",
        ])
        self.write("-home-me-eval", "s3", [user("write a PR description for acme", entrypoint="sdk-cli"),
                                           user("# Plan: write the thing", entrypoint="sdk-ts")])
        self.write("-home-me-private", "s2", [user("private stuff")])

    def write(self, project, session, records):
        d = os.path.join(self.config, "projects", project)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, session + ".jsonl"), "w") as f:
            for r in records:
                f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
        time.sleep(0.01)  # distinct mtimes: newest first

    def test_keeps_only_typed_messages_with_the_draft_they_answer(self):
        out = voice_samples.extract(self.config, sessions=10, exclude=["private"])
        self.assertEqual([s["user"] for s in out],
                         ["too long, drop the headings", "use this: [pasted] but say it plainly",
                          "file the flaky test", "typed with origin"])
        self.assertIn("## Summary", out[0]["before"])
        self.assertEqual(out[0]["session"], "-home-me-app/s1")
        self.assertNotIn("secret log", json.dumps(out))

    def test_newest_sessions_first_and_capped(self):
        out = voice_samples.extract(self.config, sessions=1, exclude=[])
        self.assertEqual([s["user"] for s in out], ["private stuff"])

    def test_unreadable_or_vanished_transcript_is_skipped(self):
        bad = os.path.join(self.config, "projects", "-home-me-app", "locked.jsonl")
        with open(bad, "w") as f:
            f.write(json.dumps(user("locked")) + "\n")
        os.chmod(bad, 0)
        os.symlink(os.path.join(self.config, "gone.jsonl"), os.path.join(self.config, "projects", "-home-me-app", "gone.jsonl"))
        out = voice_samples.extract(self.config, sessions=10, exclude=["private"])
        self.assertIn("too long, drop the headings", [s["user"] for s in out])

    def test_missing_config_dir_yields_nothing(self):
        self.assertEqual(voice_samples.extract(os.path.join(self.config, "nope"), sessions=5, exclude=[]), [])

    def test_cli_writes_the_extract_and_prints_its_path(self):
        dest = os.path.join(self.config, "out.md")
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.config}
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "voice_samples.py"), "--out", dest,
                            "--exclude", "private"], capture_output=True, text=True, check=True, env=env)
        self.assertIn(dest, r.stdout)
        text = open(dest).read()
        self.assertIn("too long, drop the headings", text)
        self.assertNotIn("private stuff", text)


if __name__ == "__main__":
    unittest.main()
