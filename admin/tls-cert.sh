#!/bin/sh
# Creates a self-signed TLS certificate on first start (shared with the backend so it can show the fingerprint).
# Macs pin this certificate at enrollment: senti enroll --backend https://HOST:8443 --fingerprint <sha256> ...
# Bring your own certificate by mounting cert.pem / key.pem into /tls.
set -e
DIR=/tls
mkdir -p "$DIR"
if [ ! -s "$DIR/cert.pem" ] || [ ! -s "$DIR/key.pem" ]; then
  HOSTS="${SENTI_TLS_HOSTS:-localhost,127.0.0.1}"
  SAN=""
  for h in $(echo "$HOSTS" | tr ',' ' '); do
    case "$h" in
      *[!0-9.]*) SAN="$SAN,DNS:$h" ;;
      *) SAN="$SAN,IP:$h" ;;
    esac
  done
  SAN="${SAN#,}"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 825 \
    -subj "/CN=Senti org backend" -addext "subjectAltName=$SAN" \
    -keyout "$DIR/key.pem" -out "$DIR/cert.pem" >/dev/null 2>&1
  chmod 600 "$DIR/key.pem"; chmod 644 "$DIR/cert.pem"
  echo "senti: created self-signed TLS certificate for $HOSTS"
fi
openssl x509 -in "$DIR/cert.pem" -noout -fingerprint -sha256 | sed 's/^/senti: /'
