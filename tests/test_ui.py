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
        self.archive = tempfile.mkdtemp()
        write(f"{self.archive}/old/state.json", json.dumps({"workflow": "task", "current": "done", "steps": steps}))
        write(f"{self.archive}/old/card.md", "archived text")
        ui.ARCHIVE = self.archive

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

    def test_archive_inside_desk_is_not_a_live_card(self):
        write(f"{self.desk}/.archive/old/state.json", json.dumps({"current": "done", "steps": []}))
        self.assertNotIn(".archive/old", {r["id"] for r in ui.cards(self.desk)})
        rows = ui.cards(self.desk, os.path.join(self.desk, ".archive"))
        self.assertEqual([r["id"] for r in rows if r.get("archived")], ["old"])
        self.assertEqual([r["id"] for r in rows if r["id"] != "old"].count("old"), 0)

    def test_archived_cards_are_listed_last_and_open(self):
        rows = ui.cards(self.desk, self.archive)
        self.assertEqual([r["id"] for r in rows][-1], "old")
        self.assertTrue(rows[-1]["archived"])
        self.assertNotIn("old", {r["id"] for r in ui.cards(self.desk)})
        c = ui.card(self.desk, "old", self.archive)
        self.assertTrue(c["archived"])
        self.assertIn(b"(archived)", ui.detail_page("old", c))
        self.assertIn(b"<h2>Archived</h2>", ui.list_page())
        self.assertIsNone(ui.card(self.desk, "old"))
        self.assertIsNone(ui.card(self.desk, "../old", self.archive))

    def test_malformed_files_do_not_break_the_list(self):
        for name, state in (("list", "[]"), ("str", '"x"'), ("num", '{"current": 5, "awaiting": 5, "steps": [1, {"id": [1]}]}'),
                            ("steps", '{"current": "plan", "steps": "no"}')):
            write(f"{self.desk}/{name}/state.json", state)
        write(f"{self.desk}/null/state.json", "{}")
        write(f"{self.desk}/null/approvals.json", "null")
        write(f"{self.desk}/null/sessions.jsonl", json.dumps({"event": "claim", "session": 7}) + "\n[1]\n")
        by = {r["id"]: r for r in ui.cards(self.desk)}
        self.assertEqual(by["list"]["current"], "unreadable")
        self.assertEqual(by["num"]["awaiting"], "5")
        self.assertEqual(by["null"]["owner"], "7")
        for cid in by:
            ui.detail_page(cid, ui.card(self.desk, cid))
        ui.list_page()

    def test_symlinked_files_are_not_followed(self):
        secret = os.path.join(tempfile.mkdtemp(), "secret")
        write(secret, "TOPSECRET")
        os.symlink(secret, f"{self.desk}/done/card.md")
        os.symlink(secret, f"{self.desk}/done/note.md")
        c = ui.card(self.desk, "done")
        self.assertEqual(c["text"], "")
        self.assertEqual(c["artifacts"], [])

    def test_nested_card_query_string_and_approved_column(self):
        write(f"{self.desk}/grp/sub/state.json", json.dumps({"current": "plan", "steps": [{"id": "plan"}]}))
        self.assertIn("grp/sub", {r["id"] for r in ui.cards(self.desk)})
        srv = ui.serve(0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        for path, want in (("/card/grp/sub", "grp/sub"), ("/card/wait?x=1", "<td>yes</td>"), ("/?x=1", "awaiting approval")):
            c = http.client.HTTPConnection("127.0.0.1", port)
            c.request("GET", path)
            r = c.getresponse()
            self.assertEqual(r.status, 200, path)
            self.assertIn(want, r.read().decode())
        srv.shutdown()
        srv.server_close()

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
