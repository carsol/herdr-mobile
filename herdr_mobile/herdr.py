"""Thin client for the Herdr socket API (newline-delimited JSON over a Unix socket)."""

import json
import os
import socket
import uuid


class HerdrError(Exception):
    pass


def socket_path() -> str:
    explicit = os.environ.get("HERDR_SOCKET_PATH")
    if explicit:
        return explicit
    base = os.path.expanduser("~/.config/herdr")
    session = os.environ.get("HERDR_SESSION")
    if session:
        return os.path.join(base, "sessions", session, "herdr.sock")
    return os.path.join(base, "herdr.sock")


def call(method: str, params: dict | None = None, timeout: float = 15) -> dict:
    # ponytail: one connection per request; herdr closes the socket after every reply anyway.
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(timeout)
    try:
        s.connect(socket_path())
        req = {"id": uuid.uuid4().hex, "method": method, "params": params or {}}
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    finally:
        s.close()
    if not buf:
        raise HerdrError("empty reply from herdr")
    resp = json.loads(buf)
    if "error" in resp:
        err = resp["error"]
        raise HerdrError(err.get("message") or err.get("code") or "herdr error")
    return resp["result"]


def ping() -> dict:
    return call("ping")


def workspaces() -> list[dict]:
    return call("workspace.list")["workspaces"]


def panes() -> list[dict]:
    return call("pane.list")["panes"]


def agents() -> list[dict]:
    return call("agent.list")["agents"]


def pane(pane_id: str) -> dict:
    return call("pane.get", {"pane_id": pane_id})["pane"]


def process_info(pane_id: str) -> dict:
    return call("pane.process_info", {"pane_id": pane_id})["process_info"]


def read(pane_id: str, lines: int = 200, ansi: bool = False, source: str = "visible") -> str:
    r = call("pane.read", {
        "pane_id": pane_id, "source": source, "lines": lines,
        "format": "ansi" if ansi else "text", "strip_ansi": not ansi,
    })
    return r["read"]["text"]


def send_text(pane_id: str, text: str) -> None:
    call("pane.send_text", {"pane_id": pane_id, "text": text})


def send_keys(pane_id: str, keys: list[str]) -> None:
    call("pane.send_keys", {"pane_id": pane_id, "keys": keys})


def workspace_create(cwd: str, label: str | None = None) -> dict:
    return call("workspace.create", {"cwd": cwd, "label": label, "focus": False})


def agent_start(pane_id: str, kind: str, name: str, args: list[str]) -> dict:
    return call("agent.start", {
        "pane_id": pane_id, "kind": kind, "name": name, "args": args,
    }, timeout=60)


def pane_close(pane_id: str) -> None:
    call("pane.close", {"pane_id": pane_id})


def workspace_close(workspace_id: str) -> None:
    call("workspace.close", {"workspace_id": workspace_id})
