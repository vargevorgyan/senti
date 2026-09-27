#!/bin/sh
# TLS for the admin panel, the device API and the MCP gateway. Runs each time the container starts.
#
# Bring your own certificate: mount cert.pem (full chain) and key.pem into /tls. Senti never touches them, and Macs use
# normal public verification (no fingerprint in invites).
#
# Otherwise Senti runs its own small certificate authority: ca.pem + ca-key.pem (10 years) sign the server certificate
# (cert.pem, about a year). Macs pin the CA once when they join, so the server certificate is renewed automatically here
# (30 days before it expires, or when SENTI_TLS_HOSTS changes) without any Mac noticing.
#
# Private keys stay in /tls (this container only). Public certificates are copied to /tls-public for the backend.
set -e
DIR=/tls
PUB=/tls-public
mkdir -p "$DIR" "$PUB"
umask 077
HOSTS="${SENTI_TLS_HOSTS:-localhost,127.0.0.1}"
SAN=""
for h in $(echo "$HOSTS" | tr ',' ' '); do
  case "$h" in
    *:*) SAN="$SAN,IP:$h" ;;                 # IPv6
    *[!0-9.]*) SAN="$SAN,DNS:$h" ;;
    *) SAN="$SAN,IP:$h" ;;
  esac
done
SAN="${SAN#,}"

publish() {  # public parts for the backend (it shows the fingerprint and serves the CA to joining Macs)
  rm -f "$PUB/ca.pem"
  [ -s "$DIR/ca.pem" ] && cp "$DIR/ca.pem" "$PUB/ca.pem"
  cp "$DIR/cert.pem" "$PUB/cert.pem"
  chmod 644 "$PUB"/*.pem; chmod 755 "$PUB"
}

if [ -s "$DIR/cert.pem" ] && [ -s "$DIR/key.pem" ] && [ ! -s "$DIR/ca-key.pem" ]; then
  if openssl x509 -in "$DIR/cert.pem" -noout -subject 2>/dev/null | grep -q "Senti org backend"; then
    echo "senti: replacing the old single self-signed certificate with Senti's own CA (Macs that joined before must join again)"
    rm -f "$DIR/cert.pem" "$DIR/key.pem"
  else
    echo "senti: using your own certificate (/tls/cert.pem); Macs verify it normally"
    publish
    exit 0
  fi
fi

if [ ! -s "$DIR/ca-key.pem" ]; then
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
    -subj "/CN=Senti CA $(openssl rand -hex 4)" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -keyout "$DIR/ca-key.pem" -out "$DIR/ca.pem" >/dev/null 2>&1
  rm -f "$DIR/cert.pem" "$DIR/hosts"
  echo "senti: created Senti's certificate authority"
fi

need_leaf=0
[ -s "$DIR/cert.pem" ] && [ -s "$DIR/key.pem" ] || need_leaf=1
[ "$(cat "$DIR/hosts" 2>/dev/null)" = "$HOSTS" ] || need_leaf=1
[ "$need_leaf" = 1 ] || openssl x509 -in "$DIR/cert.pem" -noout -checkend 2592000 >/dev/null 2>&1 || need_leaf=1
if [ "$need_leaf" = 1 ]; then
  EXT=$(mktemp)
  printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=%s\n' "$SAN" >"$EXT"
  openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -subj "/CN=Senti server" \
    -keyout "$DIR/key.new" -out "$DIR/csr" >/dev/null 2>&1
  openssl x509 -req -in "$DIR/csr" -CA "$DIR/ca.pem" -CAkey "$DIR/ca-key.pem" -set_serial "0x$(openssl rand -hex 16)" \
    -days 397 -extfile "$EXT" -out "$DIR/leaf.pem" >/dev/null 2>&1
  cat "$DIR/leaf.pem" "$DIR/ca.pem" >"$DIR/cert.new"   # full chain: server certificate, then the CA
  mv "$DIR/key.new" "$DIR/key.pem"; mv "$DIR/cert.new" "$DIR/cert.pem"
  rm -f "$DIR/csr" "$DIR/leaf.pem" "$EXT"
  echo "$HOSTS" >"$DIR/hosts"
  echo "senti: issued the server certificate for $HOSTS"
fi
chmod 600 "$DIR"/*key*.pem
chmod 644 "$DIR/cert.pem" "$DIR/ca.pem"
publish
# Macs pin this fingerprint (it's in every invite link): the CA's, so renewals need no action on any Mac
openssl x509 -in "$DIR/ca.pem" -noout -fingerprint -sha256 | sed 's/^.*=/senti: CA certificate Fingerprint=/'
