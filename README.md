# herdr-mobile

A mobile-first web UI for [Herdr](https://herdr.dev). See every agent pane
from your phone, watch its status, attach to the real terminal, send prompts,
and read Claude Code / Codex conversations as chat bubbles.

Pure Python standard library. No build step or Python dependencies.

## Features

- **Session list** grouped by workspace, with Herdr's native agent status
  (working / blocked / done / idle) and live updates.
- **Terminal view** — xterm.js attached to the pane over a WebSocket, real
  resize, a phone-friendly key row (esc, tab, arrows, ^C…), and a prompt bar so
  you can type long messages without fighting the on-screen keyboard.
- **Chat view** for Claude Code and Codex panes — the agent's transcript
  rendered as an iMessage-style conversation, tool calls collapsed.
- **Spawn** a new agent (claude, codex, gemini, pi, opencode, …) in any
  directory, straight from the phone.
- **PWA** — add to home screen and it behaves like an app.
- Optional passcode.

## Requirements

- [Herdr](https://herdr.dev/docs/install/) 0.8 or newer, running on macOS or Linux
- Python 3.10 or newer

Install and start Herdr if needed:

```sh
curl -fsSL https://herdr.dev/install.sh | sh
herdr
```

## Install as a Herdr plugin

```sh
herdr plugin install carsol/herdr-mobile
```

The plugin starts the web UI with Herdr. Run **Show mobile URL** from Herdr's
plugin actions, or open `http://127.0.0.1:9080` on the same machine.

For development, run it directly from a checkout:

```sh
git clone https://github.com/carsol/herdr-mobile.git
cd herdr-mobile
python3 -m herdr_mobile
```

To reach it from a phone, set `HERDR_MOBILE_HOST` to your Tailscale IP (or
`0.0.0.0`) and set `HERDR_MOBILE_PASSCODE` before starting the app. Do not
expose port 9080 directly to the internet.

## Configuration

Everything is an environment variable:

| Variable | Default | Meaning |
|---|---|---|
| `HERDR_MOBILE_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` (or your Tailscale IP) to reach it from a phone. |
| `HERDR_MOBILE_PORT` | `9080` | Port. |
| `HERDR_MOBILE_PASSCODE` | *(unset)* | Require this passcode. Strongly recommended when not bound to localhost. |
| `HERDR_MOBILE_ROOTS` | *(unset)* | Colon-separated directories whose children populate the "Directory" picker. |
| `HERDR_MOBILE_TAKEOVER` | `1` | Pass `--takeover` when attaching so the phone gets input control. Set `0` to observe only. |
| `HERDR_SOCKET_PATH` / `HERDR_SESSION` | Herdr defaults | Which Herdr server to talk to. |
| `HERDR_BIN_PATH` | `herdr` | Path to the herdr binary. |

## Security

This exposes your terminals. Put it behind something you trust — Tailscale,
WireGuard, an SSH tunnel — set a passcode, and never bind it to a public
interface. There is no TLS built in; terminate HTTPS in a proxy if you need it
(the app honors `X-Forwarded-Proto` for the cookie's `Secure` flag).

## How it works

- Talks to Herdr over its local socket API (`pane.list`, `agent.list`,
  `pane.send_text`, `pane.send_keys`, `workspace.create`, `agent.start`).
- The terminal view forks `herdr terminal attach <terminal_id>` on a PTY and
  bridges it to the browser with a hand-rolled RFC 6455 WebSocket.
- Chat view reads the agent's own transcript files off disk
  (`~/.claude/projects/…`, `~/.codex/sessions/…`), matched by the pane's
  working directory.

## License

MIT. xterm.js is vendored under its own MIT license
(`herdr_mobile/static/vendor/XTERM-LICENSE`).
