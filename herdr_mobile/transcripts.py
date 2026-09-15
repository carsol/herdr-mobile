"""Read agent transcripts off disk and turn them into chat turns.

Supported: Claude Code (~/.claude/projects/<slug>/*.jsonl) and Codex CLI
(~/.codex/sessions/**/rollout-*.jsonl). Each parser returns a list of turns:
    {"role": "user"|"assistant"|"tools", "text": str, "ts": float, "tools": [str]}
"""

import glob
import json
import os
import re
from datetime import datetime, timezone

CLAUDE_DIR = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude"))
CODEX_DIR = os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex"))

_codex_cwd_cache: dict[str, str | None] = {}


def _iso(ts: str | None) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _tool_label(name: str, inp) -> str:
    inp = inp if isinstance(inp, dict) else {}
    arg = (inp.get("command") or inp.get("file_path") or inp.get("path")
           or inp.get("pattern") or inp.get("query") or inp.get("description") or "")
    arg = str(arg).strip().splitlines()[0] if arg else ""
    return f"{name} {arg[:70]}".strip()


# ── Claude Code ─────────────────────────────────────────────────────

def claude_transcript_for(cwd: str) -> str | None:
    """Newest transcript for this cwd.

    ponytail: newest-mtime wins; two Claude sessions in the same directory
    will share a chat view. Match by pid/--name if that bites.
    """
    slug = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    files = glob.glob(os.path.join(CLAUDE_DIR, "projects", slug, "*.jsonl"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def _claude_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for item in content or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text", ""))
    return "\n".join(p for p in parts if p).strip()


def parse_claude(path: str, limit: int = 80) -> list[dict]:
    turns: list[dict] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("isSidechain"):
                continue
            kind = o.get("type")
            msg = o.get("message") or {}
            ts = _iso(o.get("timestamp"))
            if kind == "user":
                content = msg.get("content")
                if isinstance(content, list) and any(
                        isinstance(i, dict) and i.get("type") == "tool_result" for i in content):
                    continue
                text = _claude_text(content)
                # Slash commands and hook output arrive as pseudo-XML; not chat.
                if not text or text.startswith("<"):
                    continue
                turns.append({"role": "user", "text": text, "ts": ts})
            elif kind == "assistant":
                tools = [_tool_label(i.get("name", "?"), i.get("input"))
                         for i in msg.get("content") or []
                         if isinstance(i, dict) and i.get("type") == "tool_use"]
                text = _claude_text(msg.get("content"))
                if text:
                    turns.append({"role": "assistant", "text": text, "ts": ts})
                if tools:
                    _append_tools(turns, tools, ts)
    return turns[-limit:]


def _append_tools(turns: list[dict], tools: list[str], ts: float) -> None:
    if turns and turns[-1]["role"] == "tools":
        turns[-1]["tools"].extend(tools)
        turns[-1]["ts"] = ts
    else:
        turns.append({"role": "tools", "text": "", "tools": list(tools), "ts": ts})


# ── Codex CLI ───────────────────────────────────────────────────────

def _codex_cwd(path: str) -> str | None:
    if path in _codex_cwd_cache:
        return _codex_cwd_cache[path]
    cwd = None
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _ in range(5):
                o = json.loads(fh.readline() or "{}")
                if o.get("type") == "session_meta":
                    cwd = (o.get("payload") or {}).get("cwd")
                    break
    except (OSError, ValueError):
        pass
    _codex_cwd_cache[path] = cwd
    return cwd


def codex_transcript_for(cwd: str) -> str | None:
    files = glob.glob(os.path.join(CODEX_DIR, "sessions", "*", "*", "*", "rollout-*.jsonl"))
    files.sort(key=os.path.getmtime, reverse=True)
    for path in files[:200]:  # ponytail: newest 200 rollouts is plenty of history
        if _codex_cwd(path) == cwd:
            return path
    return None


def _codex_text(content) -> str:
    return "\n".join(
        i.get("text", "") for i in content or []
        if isinstance(i, dict) and i.get("type") in ("input_text", "output_text", "text")
    ).strip()


def parse_codex(path: str, limit: int = 80) -> list[dict]:
    turns: list[dict] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get("payload") or {}
            ts = _iso(o.get("timestamp"))
            if o.get("type") == "event_msg" and p.get("type") == "item_completed":
                item = p.get("item") or {}
                if item.get("type") == "UserMessage":
                    text = _codex_text(item.get("content"))
                    if text:
                        turns.append({"role": "user", "text": text, "ts": ts})
            elif o.get("type") == "response_item":
                pt = p.get("type")
                if pt == "message" and p.get("role") == "assistant":
                    text = _codex_text(p.get("content"))
                    if text:
                        turns.append({"role": "assistant", "text": text, "ts": ts})
                elif pt in ("function_call", "custom_tool_call"):
                    raw = p.get("arguments") or p.get("input") or ""
                    try:
                        arg = json.loads(raw) if isinstance(raw, str) else raw
                    except ValueError:
                        arg = {"command": raw}
                    _append_tools(turns, [_tool_label(p.get("name", "?"), arg)], ts)
    return turns[-limit:]


# ── Dispatch ────────────────────────────────────────────────────────

def dialogue(agent: str | None, cwd: str | None) -> dict:
    """Return {"turns": [...] | None, "path": str | None, "active_at": float}."""
    if not cwd:
        return {"turns": None, "path": None, "active_at": 0}
    if agent == "claude":
        path = claude_transcript_for(cwd)
        turns = parse_claude(path) if path else None
    elif agent == "codex":
        path = codex_transcript_for(cwd)
        turns = parse_codex(path) if path else None
    else:
        return {"turns": None, "path": None, "active_at": 0}
    active = os.path.getmtime(path) if path else 0
    return {"turns": turns, "path": path, "active_at": active}


if __name__ == "__main__":  # smoke check against whatever transcripts exist locally
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    for agent in ("claude", "codex"):
        d = dialogue(agent, target)
        print(agent, d["path"], len(d["turns"] or []))
        for t in (d["turns"] or [])[-4:]:
            print("  ", t["role"], (t["text"] or ", ".join(t.get("tools", [])))[:90].replace("\n", " "))
