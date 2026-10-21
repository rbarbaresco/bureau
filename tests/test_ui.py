import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ui  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class UiTest(unittest.TestCase):
    def setUp(self):
        self.desk = tempfile.mkdtemp()
        steps = [{"id": "plan", "persona": "architect", "gate": "approve"}, {"id": "build", "persona": "se", "gate": "none"}]
        write(f"{self.desk}/done/state.json", json.dumps({"workflow": "task", "current": "done", "steps": steps}))
        write(f"{self.desk}/wait/state.json", json.dumps({"workflow": "task", "current": "plan", "awaiting": "plan", "steps": steps}))
        write(f"{self.desk}/wait/approvals.json", json.dumps({"plan": {}}))
        write(f"{self.desk}/wait/card.md", "# hello")
        write(f"{self.desk}/wait/plan.md", "the plan <script>x</script>")
        write(f"{self.desk}/wait/zeta.md", "z")
        write(f"{self.desk}/wait/build.md", "b")
        write(f"{self.desk}/wait/sessions.jsonl",
              json.dumps({"event": "claim", "session": "abcdef123456", "pid": 1}) + "\n{torn\n")
        write(f"{self.desk}/intake/card.md", "only text")
        write(f"{self.desk}/wait/worktrees/r/state.json", "{}")
        ui.DESK = self.desk

    def test_cards_order_and_fields(self):
        rows = ui.cards(self.desk)
        self.assertEqual([r["id"] for r in rows][0], "wait")
        self.assertEqual({r["id"] for r in rows}, {"done", "wait", "intake"})
        by = {r["id"]: r for r in rows}
        self.assertEqual(by["wait"]["awaiting"], "plan")
        self.assertEqual(by["wait"]["owner"], "abcdef12")
        self.assertEqual(by["intake"]["current"], "not started")

    def test_card_detail(self):
        c = ui.card(self.desk, "wait")
        self.assertEqual([n for n, _ in c["artifacts"]], ["plan", "build", "zeta"])
        self.assertIn("plan", c["approvals"])
        self.assertEqual(len(c["sessions"]), 1)  # the torn line is skipped
        self.assertIsNone(ui.card(self.desk, "../../etc"))
        self.assertEqual(ui.card(self.desk, "done")["sessions"], [])

    def test_http(self):
        srv = ui.serve(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]

        def get(path, method="GET", host=None):
            c = http.client.HTTPConnection("127.0.0.1", port)
            c.putrequest(method, path, skip_host=True)
            c.putheader("Host", host or f"127.0.0.1:{port}")
            c.endheaders()
            r = c.getresponse()
            return r.status, r.read().decode()

        s, body = get("/")
        self.assertEqual(s, 200)
        self.assertIn("awaiting approval: plan", body)
        s, body = get("/card/wait")
        self.assertEqual(s, 200)
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>x", body)
        self.assertEqual(get("/card/..%2f..%2fetc%2fpasswd")[0], 404)
        self.assertEqual(get("/card/nope")[0], 404)
        self.assertEqual(get("/", "POST")[0], 405)
        self.assertEqual(get("/", host="evil.example")[0], 403)
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    unittest.main()
