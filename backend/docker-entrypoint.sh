#!/bin/sh
# Starts as root only to hand Senti's own folders to the unprivileged "senti" user (uid 10001), then drops root for good.
# Used by both the backend and the gateway runner.
set -e
if [ "$(id -u)" = 0 ]; then
  for d in /data /run/senti-runner /srv; do
    if [ -d "$d" ] && [ "$(stat -c %u "$d")" != 10001 ]; then chown -R 10001:10001 "$d" 2>/dev/null || true; fi
  done
  exec setpriv --reuid=10001 --regid=10001 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs "$@"
fi
exec "$@"
