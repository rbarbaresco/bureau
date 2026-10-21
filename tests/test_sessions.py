import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import sessions  # noqa: E402

HOOKS = os.path.join(ROOT, "hooks")
STEPS = [{"id": "plan", "gate": "approve"}, {"id": "build", "gate": "approve", "writes_code": True}]


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.desk = os.path.join(self.tmp, "desk")
        self.card = os.path.join(self.desk, "ABC-1")
        os.makedirs(self.card)
        with open(os.path.join(self.card, "state.json"), "w") as f:
            json.dump({"current": "plan", "awaiting": "plan", "steps": STEPS}, f)
        self.procs = []
        self.addCleanup(lambda: [p.kill() for p in self.procs])

    def claude(self):
        """A live process whose comm is `claude`, standing in for a Claude Code session."""
        exe = os.path.join(self.tmp, f"bin{len(self.procs)}", "claude")
        os.makedirs(os.path.dirname(exe))
        shutil.copy(shutil.which("sleep"), exe)
        p = subprocess.Popen([exe, "60"])
        self.procs.append(p)
        for _ in range(100):  # comm is set once exec finishes
            if sessions.comm(p.pid) == "claude":
                break
            subprocess.run(["sleep", "0.01"])
        return p.pid

    def own(self, session, pid, card=None):
        sessions.append(card or self.card, "claim", session, pid, why="new")

    def hook(self, script, payload, pid=None):
        env = {**os.environ, "BUREAU_DESK": self.desk, "BUREAU_CLAUDE_PID": str(pid or 1)}
        return subprocess.run([sys.executable, os.path.join(HOOKS, script)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env).stdout

    def gate(self, session, tool="Bash", pid=None, **inp):
        out = self.hook("gate.py", {"tool_name": tool, "tool_input": inp, "session_id": session, "cwd": self.tmp}, pid)
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"] if out else None

    def desk_cmd(self, sub, session, pid=None):
        return self.gate(session, command=f"python3 {ROOT}/scripts/desk.py {sub} {self.card}", pid=pid)

    def test_status(self):
        self.assertEqual(sessions.status(self.card, "s1"), "none")
        pid = self.claude()
        self.own("s1", pid)
        self.assertEqual(sessions.status(self.card, "s1"), "mine")
        self.assertEqual(sessions.status(self.card, "s2"), "held")
        sessions.append(self.card, "end", "s1", pid)
        self.assertEqual(sessions.status(self.card, "s2"), "free")
        self.assertEqual(sessions.status(self.card, "s1"), "free")

    def test_dead_owner_is_free(self):
        self.own("s1", 2 ** 22 + 1)  # above pid_max, so no such process
        self.assertEqual(sessions.status(self.card, "s2"), "free")

    def test_log_is_append_only(self):
        self.own("s1", 1)
        sessions.append(self.card, "end", "s1", 1)
        self.own("s2", 1)
        self.assertEqual([e["event"] for e in sessions.events(self.card)], ["claim", "end", "claim"])

    def test_gate_blocks_non_owner_on_state_commands(self):
        self.own("s1", self.claude())
        self.assertIn("held by session s1", self.desk_cmd("finish", "s2"))
        self.assertIsNone(self.desk_cmd("finish", "s1"))
        self.assertIsNone(self.desk_cmd("list", "s2"))

    def test_gate_blocks_non_owner_worktree_edit(self):
        self.own("s1", self.claude())
        wt = os.path.join(self.card, "worktrees", "r")
        os.makedirs(wt)
        reason = self.gate("s2", "Write", file_path=os.path.join(wt, "a.py"))
        self.assertIn("held by session s1", reason)

    def test_gate_free_card_asks_for_work(self):
        self.own("s1", 2 ** 22 + 1)
        self.assertIn("/work ABC-1", self.desk_cmd("finish", "s2"))

    def test_legacy_card_without_log_is_open(self):
        self.assertIsNone(self.desk_cmd("finish", "s2"))

    def test_agent_cannot_write_log(self):
        self.assertIn("hooks", self.gate("s1", "Write", file_path=os.path.join(self.card, "sessions.jsonl")))
        self.assertIn("hooks", self.gate("s1", command=f"echo x >> {self.card}/sessions.jsonl"))

    def test_gate_claims_new_card_on_init(self):
        new = os.path.join(self.desk, "NEW-1")
        pid = self.claude()
        self.gate("s1", pid=pid, command=f"python3 {ROOT}/scripts/workflow.py start task {new}")
        self.assertEqual(sessions.status(new, "s1"), "mine")
        self.assertEqual(sessions.last(new)["why"], "new")

    def test_gate_logs_resume_with_new_pid(self):
        self.own("s1", 2 ** 22 + 1)
        pid = self.claude()
        self.assertIsNone(self.desk_cmd("finish", "s1", pid=pid))
        self.assertEqual((sessions.last(self.card)["pid"], sessions.last(self.card)["why"]), (pid, "resume"))

    def test_work_claims_free_card_and_reports_past_sessions(self):
        self.own("s1", 2 ** 22 + 1)
        pid = self.claude()
        out = self.hook("owner.py", {"prompt": "/work ABC-1", "session_id": "s2"}, pid)
        self.assertIn("1 past session", out)
        self.assertIn("s1", out)
        self.assertEqual(sessions.status(self.card, "s2"), "mine")
        self.assertEqual(sessions.last(self.card)["why"], "owner-dead")
        self.assertEqual(len(sessions.events(self.card)), 2)

    def test_work_blocked_by_live_owner_even_with_take(self):
        self.own("s1", self.claude())
        out = self.hook("owner.py", {"prompt": "/work ABC-1 --take", "session_id": "s2"}, self.claude())
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertEqual(sessions.status(self.card, "s1"), "mine")

    def test_work_resolves_repo_number_ref(self):
        card = os.path.join(self.desk, "bureau-17")
        os.makedirs(card)
        out = self.hook("owner.py", {"prompt": "/work rbarbaresco/bureau#17", "session_id": "s1"}, self.claude())
        self.assertEqual(sessions.status(card, "s1"), "mine")
        self.assertNotIn("block", out)

    def test_session_end_closes_only_own_cards(self):
        other = os.path.join(self.desk, "ABC-2")
        os.makedirs(other)
        pid = self.claude()
        self.own("s1", pid)
        self.own("s2", pid, other)
        self.hook("session_end.py", {"session_id": "s1"}, pid)
        self.assertEqual(sessions.last(self.card)["event"], "end")
        self.assertEqual(sessions.last(other)["event"], "claim")

    def test_bare_approve_matches_only_callers_card(self):
        other = os.path.join(self.desk, "ABC-2")
        os.makedirs(other)
        with open(os.path.join(other, "state.json"), "w") as f:
            json.dump({"awaiting": "plan", "steps": STEPS}, f)
        self.own("s1", self.claude())
        self.own("s2", self.claude(), other)
        out = self.hook("approve.py", {"prompt": "/approve", "session_id": "s2"})
        self.assertIn("card=ABC-2", out)
        out = self.hook("approve.py", {"prompt": "/approve ABC-1", "session_id": "s2"})
        self.assertIn("card=ABC-1", out)  # explicit id stays authoritative
        out = self.hook("approve.py", {"prompt": "/approve", "session_id": "s3"})
        self.assertIn("block", out)


if __name__ == "__main__":
    unittest.main()
