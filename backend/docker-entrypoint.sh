#!/bin/sh
# Starts as root only to hand Senti's own folders to the unprivileged "senti" user (uid 10001), then drops root for good.
# Used by both the backend and the gateway runner.
set -e
if [ "$(id -u)" = 0 ]; then
  dirs="/data /run/senti-runner"
  # the gateway's shared folder: Senti's own (default) is handed over; a folder with the company's data keeps its owner
  [ "${SENTI_GATEWAY_KEEP_OWNER:-false}" = true ] || dirs="$dirs /srv"
  for d in $dirs; do
    if [ -d "$d" ] && [ "$(stat -c %u "$d")" != 10001 ]; then chown -R 10001:10001 "$d" 2>/dev/null || true; fi
  done
  exec setpriv --reuid=10001 --regid=10001 --clear-groups --inh-caps=-all --bounding-set=-all --no-new-privs "$@"
fi
exec "$@"
