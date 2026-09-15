#!/bin/sh
# Herdr plugin action: show the mobile UI's URL as a Herdr notification.
ENVFILE="${HERDR_PLUGIN_CONFIG_DIR:-}/env"
[ -f "$ENVFILE" ] && { set -a; . "$ENVFILE"; set +a; }
HOST="${HERDR_MOBILE_HOST:-127.0.0.1}"
[ "$HOST" = "0.0.0.0" ] && HOST="$(hostname)"
URL="http://$HOST:${HERDR_MOBILE_PORT:-9080}"
echo "$URL"
cd "$(dirname "$0")/.." && python3 -c "
import sys; from herdr_mobile import herdr
herdr.call('notification.show', {'title': 'Herdr Mobile', 'body': sys.argv[1]})" "$URL" 2>/dev/null || true
