#!/bin/sh
# Herdr plugin startup hook: start herdr-mobile detached, once.
# Reads optional overrides from $HERDR_PLUGIN_CONFIG_DIR/env (KEY=VALUE lines).
set -u
STATE="${HERDR_PLUGIN_STATE_DIR:-$HOME/.config/herdr/plugins/herdr-mobile}"
mkdir -p "$STATE"
PIDFILE="$STATE/herdr-mobile.pid"
LOG="$STATE/herdr-mobile.log"
ENVFILE="${HERDR_PLUGIN_CONFIG_DIR:-$STATE}/env"
[ -f "$ENVFILE" ] && { set -a; . "$ENVFILE"; set +a; }

if [ "${1:-}" = "--restart" ] && [ -f "$PIDFILE" ]; then
  kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"
fi
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "herdr-mobile already running (pid $(cat "$PIDFILE"))"; exit 0
fi
cd "$(dirname "$0")/.." || exit 1
nohup python3 -m herdr_mobile >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
echo "herdr-mobile started (pid $!) on http://${HERDR_MOBILE_HOST:-127.0.0.1}:${HERDR_MOBILE_PORT:-9080}"
