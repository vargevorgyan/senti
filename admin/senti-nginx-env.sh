#!/bin/sh
# nginx settings that depend on the install, written before nginx starts:
#   SENTI_HTTPS_PORT     where plain HTTP redirects to
#   SENTI_TRUSTED_PROXY  IPs/CIDRs of a reverse proxy in front of Senti (e.g. the host's nginx); only then is the client
#                        address taken from X-Forwarded-For, so admin allow-lists and rate limits see the real caller
set -eu
d=/etc/nginx/snippets
port=${SENTI_HTTPS_PORT:-8443}
case "$port" in ''|*[!0-9]*) echo "SENTI_HTTPS_PORT must be a number" >&2; exit 1 ;; esac
printf 'return 301 https://$host:%s$request_uri;\n' "$port" > "$d/senti-redirect.conf"
: > "$d/senti-real-ip.conf"
if [ -n "${SENTI_TRUSTED_PROXY:-}" ]; then
  for net in $(printf '%s' "$SENTI_TRUSTED_PROXY" | tr ',' ' '); do
    case "$net" in *[!0-9A-Fa-f:./]*) echo "SENTI_TRUSTED_PROXY: bad address $net" >&2; exit 1 ;; esac
    printf 'set_real_ip_from %s;\n' "$net"
  done > "$d/senti-real-ip.conf"
  printf 'real_ip_header X-Forwarded-For;\n' >> "$d/senti-real-ip.conf"
fi
