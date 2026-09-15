"""HTTP + WebSocket server. Pure stdlib."""

import json
import mimetypes
import os
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import auth, herdr, transcripts, ws

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ROOTS = [os.path.expanduser(p) for p in os.environ.get("HERDR_MOBILE_ROOTS", "").split(":") if p]

# Kind -> flag that skips approval prompts ("yolo" in the UI).
YOLO_FLAGS = {
    "claude": "--dangerously-skip-permissions",
    "codex": "--dangerously-bypass-approvals-and-sandbox",
    "gemini": "--yolo",
    "agy": "--dangerously-skip-permissions",
}
AGENT_KINDS = ["claude", "codex", "gemini", "pi", "opencode", "agy", "cline", "copilot", "amp", "shell"]


def _projects() -> list[dict]:
    out = []
    for root in ROOTS:
        try:
            for name in sorted(os.listdir(root)):
                path = os.path.join(root, name)
                if not name.startswith(".") and os.path.isdir(path):
                    out.append({"name": name, "path": path})
        except OSError:
            continue
    return out


def _pane_list() -> list[dict]:
    workspaces = {w["workspace_id"]: w for w in herdr.workspaces()}
    agents = {a["pane_id"]: a for a in herdr.agents()}
    out = []
    for p in herdr.panes():
        ws_ = workspaces.get(p["workspace_id"], {})
        a = agents.get(p["pane_id"], {})
        cwd = p.get("foreground_cwd") or p.get("cwd") or ""
        out.append({
            "pane_id": p["pane_id"],
            "terminal_id": p["terminal_id"],
            "workspace_id": p["workspace_id"],
            "workspace": ws_.get("label") or p["workspace_id"],
            "agent": p.get("agent") or a.get("agent"),
            "display_agent": p.get("display_agent") or a.get("display_agent"),
            "name": a.get("name") or p.get("label") or p.get("title"),
            "status": p.get("agent_status", "unknown"),
            "cwd": cwd,
            "project": os.path.basename(cwd.rstrip("/")) if cwd else "",
            "title": p.get("terminal_title_stripped") or p.get("terminal_title") or "",
            "focused": p.get("focused", False),
        })
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "herdr-mobile"

    def log_message(self, fmt, *args):  # quieter than the default
        if os.environ.get("HERDR_MOBILE_DEBUG"):
            super().log_message(fmt, *args)

    # ── helpers ──
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, cache=False):
        if not os.path.isfile(path):
            return self._json({"error": "not found"}, 404)
        with open(path, "rb") as fh:
            body = fh.read()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if path.endswith(".js"):
            ctype = "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _page(self, name):
        return self._file(os.path.join(STATIC, name))

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        if self.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
            return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {}

    def _secure(self) -> bool:
        return self.headers.get("X-Forwarded-Proto", "") == "https"

    def _redirect(self, to):
        self.send_response(302)
        self.send_header("Location", to)
        self.end_headers()

    # ── routing ──
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path
        if path == "/health":
            try:
                herdr.ping()
                return self._json({"ok": True})
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": str(e)}, 503)
        if path.startswith("/static/"):
            rel = os.path.normpath(path[len("/static/"):])
            if rel.startswith(".."):
                return self._json({"error": "bad path"}, 400)
            return self._file(os.path.join(STATIC, rel), cache=rel.startswith("vendor/"))
        if path == "/manifest.json":
            return self._file(os.path.join(STATIC, "manifest.json"))
        if path == "/login":
            return self._page("login.html")
        if not auth.is_authed(self.headers):
            if path.startswith("/api/"):
                return self._json({"error": "unauthorized"}, 401)
            return self._redirect("/login")

        if path == "/":
            return self._page("index.html")
        if path.startswith("/pane/"):
            return self._page("session.html")
        if path.startswith("/chat/"):
            return self._page("chat.html")

        if path == "/api/panes":
            try:
                return self._json({"panes": _pane_list()})
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e), "panes": []}, 503)
        if path == "/api/projects":
            return self._json({"projects": _projects(), "kinds": AGENT_KINDS})

        m = path.startswith("/api/panes/") and path[len("/api/panes/"):].split("/", 1)
        if m:
            pane_id = urllib.parse.unquote(m[0])
            sub = m[1] if len(m) > 1 else ""
            q = urllib.parse.parse_qs(url.query)
            try:
                if sub == "ws":
                    return self._websocket(pane_id)
                if sub == "screen":
                    lines = int(q.get("lines", ["200"])[0])
                    return self._json({"text": herdr.read(pane_id, lines=lines, ansi=True, source="visible")})
                if sub == "dialogue":
                    p = herdr.pane(pane_id)
                    d = transcripts.dialogue(p.get("agent"), p.get("foreground_cwd") or p.get("cwd"))
                    d["agent"] = p.get("agent")
                    d["status"] = p.get("agent_status")
                    return self._json(d)
                if sub == "":
                    p = herdr.pane(pane_id)
                    a = next((x for x in herdr.agents() if x["pane_id"] == pane_id), {})
                    p["name"] = a.get("name")
                    return self._json(p)
            except herdr.HerdrError as e:
                return self._json({"error": str(e)}, 404)
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            body = self._body()
            if auth.enabled() and auth.check_passcode(body.get("passcode", "")):
                self.send_response(302)
                self.send_header("Set-Cookie", auth.set_cookie_header(self._secure()))
                self.send_header("Location", "/")
                self.end_headers()
                return
            time.sleep(1)  # ponytail: crude brute-force brake
            return self._redirect("/login?bad=1")
        if not auth.is_authed(self.headers):
            return self._json({"error": "unauthorized"}, 401)

        body = self._body()
        try:
            if path == "/api/panes":
                return self._json(self._create(body))
            m = path[len("/api/panes/"):].split("/", 1) if path.startswith("/api/panes/") else None
            if m and len(m) == 2:
                pane_id = urllib.parse.unquote(m[0])
                if m[1] == "text":
                    text = str(body.get("text", ""))
                    if text:
                        herdr.send_text(pane_id, text)
                    if body.get("enter", True):
                        time.sleep(0.05)  # some TUIs drop Enter if it lands in the same read as the text
                        herdr.send_keys(pane_id, ["Enter"])
                    return self._json({"ok": True})
                if m[1] == "keys":
                    herdr.send_keys(pane_id, [str(k) for k in body.get("keys", [])])
                    return self._json({"ok": True})
                if m[1] == "close":
                    herdr.pane_close(pane_id)
                    return self._json({"ok": True})
        except herdr.HerdrError as e:
            return self._json({"error": str(e)}, 400)
        return self._json({"error": "not found"}, 404)

    def _create(self, body: dict) -> dict:
        cwd = os.path.expanduser(str(body.get("cwd") or "~"))
        if not os.path.isdir(cwd):
            raise herdr.HerdrError(f"not a directory: {cwd}")
        kind = str(body.get("kind") or "claude")
        name = str(body.get("name") or os.path.basename(cwd.rstrip("/")) or kind)[:40]
        r = herdr.workspace_create(cwd, label=name)
        pane_id = r["root_pane"]["pane_id"]
        if kind != "shell":
            args = [a for a in str(body.get("args") or "").split() if a]
            if body.get("yolo") and kind in YOLO_FLAGS:
                args.insert(0, YOLO_FLAGS[kind])
            herdr.agent_start(pane_id, kind, name, args)
        return {"ok": True, "pane_id": pane_id}

    def _websocket(self, pane_id: str):
        key = self.headers.get("Sec-WebSocket-Key")
        if self.headers.get("Upgrade", "").lower() != "websocket" or not key:
            return self._json({"error": "websocket expected"}, 400)
        terminal_id = herdr.pane(pane_id)["terminal_id"]
        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", ws.accept_key(key))
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True
        ws.bridge(self.connection, terminal_id)


def serve(host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f"herdr-mobile listening on http://{host}:{port}  (herdr socket: {herdr.socket_path()})")
    if not auth.enabled() and host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: no HERDR_MOBILE_PASSCODE set and bound to a non-loopback address")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
