"""Read-only card viewer: python3 scripts/ui.py [--port 8765]  ->  http://127.0.0.1:8765

Lists the cards under desk/ and shows one card's state, approvals, text, artifacts and session log.
It reads the files; nothing here opens a file for writing.
"""
import html
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote

DESK = os.environ.get("BUREAU_DESK") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desk")


def _json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):  # hooks write these files while we read
        return default


def _text(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _card_dirs(desk):
    """Relative ids: dirs with state.json (same rule as desk.list_cards) or an intake-only card.md."""
    ids = []
    for root, dirs, files in os.walk(desk):
        dirs[:] = [d for d in dirs if d != "worktrees"]
        if "state.json" in files or ("card.md" in files and root != desk):
            ids.append(os.path.relpath(root, desk))
    return ids


def _sessions(path):
    out = []
    for line in _text(path).splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:  # torn write
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def cards(desk=DESK):
    rows = []
    for cid in _card_dirs(desk):
        d = os.path.join(desk, cid)
        sp = os.path.join(d, "state.json")
        if not os.path.exists(sp):
            row = {"id": cid, "workflow": "-", "current": "not started", "awaiting": None, "mtime": os.path.getmtime(d)}
        else:
            s = _json(sp, None)
            row = {"id": cid, "mtime": os.path.getmtime(sp)}
            row.update({"workflow": "-", "current": "unreadable", "awaiting": None} if s is None else
                       {"workflow": s.get("workflow") or "-", "current": s.get("current", "?"), "awaiting": s.get("awaiting")})
        ev = _sessions(os.path.join(d, "sessions.jsonl"))
        row["owner"] = (ev[-1].get("session") or "")[:8] if ev and ev[-1].get("event") == "claim" else None
        rows.append(row)
    return sorted(rows, key=lambda r: (not r["awaiting"], -r["mtime"]))


def card(desk, cid):
    """Detail for a card id that cards() returned, else None. The id is never joined into a path unchecked."""
    if cid not in _card_dirs(desk):
        return None
    d = os.path.join(desk, cid)
    state = _json(os.path.join(d, "state.json"), None)
    steps = [s.get("id") for s in (state or {}).get("steps", [])]
    names = sorted(n[:-3] for n in os.listdir(d)
                   if n.endswith(".md") and n != "card.md" and os.path.isfile(os.path.join(d, n)) and not os.path.islink(os.path.join(d, n)))
    names.sort(key=lambda n: (steps.index(n) if n in steps else len(steps), n))
    return {"state": state, "text": _text(os.path.join(d, "card.md")),
            "artifacts": [(n, _text(os.path.join(d, n + ".md"))) for n in names],
            "approvals": _json(os.path.join(d, "approvals.json"), {}),
            "sessions": _sessions(os.path.join(d, "sessions.jsonl"))}


CSS = "body{font:15px system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem}td,th{text-align:left;padding:.2rem .8rem}pre{white-space:pre-wrap;background:#f4f4f4;padding:1rem}.wait{background:#ffd54f;padding:0 .4rem}"


def page(title, body):
    return f"<!doctype html><meta charset=utf-8><title>{html.escape(title)}</title><style>{CSS}</style>{body}".encode()


def list_page():
    rows = "".join(
        f"<tr><td><a href='/card/{html.escape(r['id'])}'>{html.escape(r['id'])}</a></td><td>{html.escape(r['workflow'])}</td>"
        f"<td>{html.escape(r['current'])}</td><td>{'<span class=wait>awaiting approval: ' + html.escape(r['awaiting']) + '</span>' if r['awaiting'] else ''}</td>"
        f"<td>{html.escape(r['owner'] or '')}</td></tr>" for r in cards(DESK))
    return page("Bureau", f"<h1>Bureau</h1><table><tr><th>card<th>workflow<th>step<th>gate<th>owner</tr>{rows}</table>")


def detail_page(cid, c):
    s = c["state"] or {}
    steps = "".join(
        f"<tr><td>{html.escape(str(x.get('id')))}</td><td>{html.escape(str(x.get('persona', '')))}</td><td>{html.escape(str(x.get('gate', '')))}</td>"
        f"<td>{'yes' if x.get('id') in c['approvals'] else 'no'}</td></tr>" for x in s.get("steps", []))
    sess = c["sessions"]
    if sess:
        last = sess[-1]
        owner = f"owner: {last.get('session', '?')} (pid {last.get('pid', '?')})" if last.get("event") == "claim" else "no owner (last event: " + html.escape(str(last.get("event"))) + ")"
        log = "".join(f"<pre>{html.escape(json.dumps(e))}</pre>" for e in sess)
    else:
        owner, log = "no session record", ""
    arts = "".join(f"<h2>{html.escape(n)}</h2><pre>{html.escape(t)}</pre>" for n, t in c["artifacts"])
    wait = f" <span class=wait>awaiting approval: {html.escape(s['awaiting'])}</span>" if s.get("awaiting") else ""
    return page(cid, f"<p><a href='/'>all cards</a></p><h1>{html.escape(cid)}</h1><p>{html.escape(str(s.get('workflow', '-')))} / "
                f"{html.escape(str(s.get('current', 'not started')))}{wait}</p>"
                f"<table><tr><th>step<th>persona<th>gate<th>approved</tr>{steps}</table><h2>card</h2><pre>{html.escape(c['text'])}</pre>"
                f"{arts}<h2>sessions</h2><p>{html.escape(owner) if sess else owner}</p>{log}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        port = self.server.server_address[1]
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):  # DNS rebinding
            return self._send(403, b"forbidden")
        if self.path == "/":
            return self._send(200, list_page())
        if self.path.startswith("/card/"):
            cid = unquote(self.path[len("/card/"):])
            c = card(DESK, cid)
            if c is not None:
                return self._send(200, detail_page(cid, c))
        self._send(404, b"not found")

    def do_POST(self):
        self._send(405, b"read-only")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def log_message(self, *a):
        pass


def serve(port):
    return HTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    print(f"http://127.0.0.1:{port}")
    serve(port).serve_forever()
