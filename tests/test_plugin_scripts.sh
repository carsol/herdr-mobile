#!/bin/sh
set -eu

tmp=$(mktemp -d)
pid=
trap '[ -z "$pid" ] || kill "$pid" 2>/dev/null || true; rm -rf "$tmp"' EXIT
export HERDR_PLUGIN_STATE_DIR="$tmp/state"
export HERDR_PLUGIN_CONFIG_DIR="$tmp/config"
mkdir -p "$HERDR_PLUGIN_CONFIG_DIR"

url() {
  HERDR_SOCKET_PATH="$1" sh scripts/plugin-start.sh --url | head -n 1
}

test "$(url "$HOME/.config/herdr/herdr.sock")" = "http://127.0.0.1:9080"
one=$(url "$HOME/.config/herdr/sessions/one/herdr.sock")
two=$(url "$HOME/.config/herdr/sessions/two/herdr.sock")
test "$one" != "$two"
test "${one##*:}" -ge 10000
test "${one##*:}" -lt 60000
test "$(find "$HERDR_PLUGIN_STATE_DIR/sessions" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" = 3

HERDR_SOCKET_PATH="$HOME/.config/herdr/sessions/start/herdr.sock" \
  HERDR_MOBILE_PORT=0 HERDR_MOBILE_PYTHON="${PYTHON_BIN:-python3}" \
  sh scripts/plugin-start.sh >/dev/null
pidfile=$(find "$HERDR_PLUGIN_STATE_DIR/sessions" -name herdr-mobile.pid -type f)
pid=$(cat "$pidfile")
kill -0 "$pid"
