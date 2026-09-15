#!/bin/sh
# Herdr plugin startup hook and actions.
set -u
STATE_ROOT="${HERDR_PLUGIN_STATE_DIR:-$HOME/.config/herdr/plugins/herdr-mobile}"
ENVFILE="${HERDR_PLUGIN_CONFIG_DIR:-$STATE_ROOT}/env"
[ -f "$ENVFILE" ] && { set -a; . "$ENVFILE"; set +a; }

SOCKET="${HERDR_SOCKET_PATH:-${HERDR_SESSION:-default}}"
case "$SOCKET" in
  default|"$HOME/.config/herdr/herdr.sock") KEY=default; DEFAULT_PORT=9080 ;;
  *) KEY=$(printf '%s' "$SOCKET" | cksum | awk '{print $1}'); DEFAULT_PORT=$((10000 + KEY % 50000)) ;;
esac
STATE="$STATE_ROOT/sessions/$KEY"
PIDFILE="$STATE/herdr-mobile.pid"
LOG="$STATE/herdr-mobile.log"
HERDR_MOBILE_PORT="${HERDR_MOBILE_PORT:-$DEFAULT_PORT}"
export HERDR_MOBILE_PORT
mkdir -p "$STATE"

HOST="${HERDR_MOBILE_HOST:-127.0.0.1}"
[ "$HOST" = "0.0.0.0" ] && HOST=$(hostname)
URL="http://$HOST:$HERDR_MOBILE_PORT"
PYTHON="${HERDR_MOBILE_PYTHON:-python3}"

if [ "${1:-}" = "--url" ]; then
  echo "$URL"
  cd "$(dirname "$0")/.." || exit 1
  "$PYTHON" -c "
import sys; from herdr_mobile import herdr
herdr.call('notification.show', {'title': 'Herdr Mobile', 'body': sys.argv[1]})" "$URL" 2>/dev/null || true
  exit 0
fi

if [ "${1:-}" = "--restart" ] && [ -f "$PIDFILE" ]; then
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE"
fi
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "herdr-mobile already running (pid $(cat "$PIDFILE"))"; exit 0
fi
cd "$(dirname "$0")/.." || exit 1
if ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  echo "herdr-mobile requires Python 3.10 or newer (set HERDR_MOBILE_PYTHON if needed)" >&2
  exit 1
fi
nohup "$PYTHON" -m herdr_mobile >>"$LOG" 2>&1 &
PID=$!
echo "$PID" >"$PIDFILE"
sleep 0.2
if ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PIDFILE"
  echo "herdr-mobile failed to start; see $LOG" >&2
  exit 1
fi
echo "herdr-mobile started (pid $PID) on $URL"
