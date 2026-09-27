#!/bin/sh
# Senti for employees' Macs. One line, with the invite link from your administrator:
#
#   curl -fsSL <this script> | sh -s -- 'https://…/join#s=…&k=sti_…&fp=…'
#
# What it does (everything in your user account; no administrator password):
#   1. checks the company server: its certificate must match the fingerprint in your invite
#   2. downloads Senti from that server (the version that matches it) and checks the download
#   3. installs uv (Python tooling) and, if needed, Apple's command line tools (for the Secure Enclave key)
#   4. installs Senti in ~/Library/Application Support/Senti and the `senti` command in ~/.local/bin
#   5. runs `senti join`: shows the company and your email as the server reports them, and joins only if you say yes
#
# Remove Senti again:   curl -fsSL <this script> | sh -s -- --uninstall
set -eu

APP="$HOME/Library/Application Support/Senti"
BIN="$HOME/.local/bin"
B="" G="" Y="" R="" N=""
if [ -t 1 ]; then B=$(printf '\033[1m'); G=$(printf '\033[32m'); Y=$(printf '\033[33m'); R=$(printf '\033[31m'); N=$(printf '\033[0m'); fi
step() { printf '\n%s▸ %s%s\n' "$B" "$*" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '\n%s✗ %s%s\n' "$R" "$*" "$N" >&2; exit 1; }
ask()  { # yes/no on the terminal itself (under `curl | sh` stdin is this script)
  printf '  %s [y/N] ' "$1" >/dev/tty 2>/dev/null || return 1
  read -r a </dev/tty 2>/dev/null || return 1
  case "$a" in y|Y|yes|Yes) return 0 ;; *) return 1 ;; esac
}

[ "$(uname -s)" = Darwin ] || die "Senti for employees runs on macOS."

uninstall() {
  step "Removing Senti from this Mac"
  [ "${1:-}" = "--yes" ] || ask "Remove Senti, its hooks in your AI assistants and its data on this Mac?" || die "Nothing removed."
  S="$APP/app/.venv/bin/senti"
  if [ -x "$S" ]; then
    "$S" uninstall all >/dev/null 2>&1 || true
    "$S" connect --remove >/dev/null 2>&1 || true
    "$S" service uninstall >/dev/null 2>&1 || true
    "$S" stop >/dev/null 2>&1 || true
  fi
  rm -rf "$APP" "$HOME/.senti"
  [ -L "$BIN/senti" ] && rm -f "$BIN/senti"
  ok "Senti was removed. Ask your administrator to revoke this Mac on the Devices page."
  exit 0
}

[ "${1:-}" = "--uninstall" ] && uninstall "${2:-}"
LINK="${1:-}"
[ -n "$LINK" ] || die "Usage: curl -fsSL <installer> | sh -s -- '<the invite link from your administrator>'"
shift
EXTRA="$*"   # e.g. --no-service

# ------------------------------------------------------------------ the invite link
FRAG=${LINK#*#}
[ "$FRAG" != "$LINK" ] || die "That isn't a whole invite link: copy everything, including the part after '#'."
SERVER="" KEY="" FP=""
OLDIFS=$IFS; IFS='&'
for pair in $FRAG; do
  case "$pair" in
    s=*) SERVER=${pair#s=} ;;
    k=*) KEY=${pair#k=} ;;
    fp=*) FP=$(printf '%s' "${pair#fp=}" | tr 'A-F' 'a-f' | tr -d ':') ;;
  esac
done
IFS=$OLDIFS
printf '%s' "$SERVER" | grep -Eq '^([A-Za-z0-9.-]{1,253}|\[[0-9A-Fa-f:]+\])(:[0-9]{1,5})?$' || die "The invite link has no valid server address."
printf '%s' "$KEY" | grep -Eq '^sti_[A-Za-z0-9_-]{20,100}$' || die "The invite link has no valid invite key."
[ -z "$FP" ] || printf '%s' "$FP" | grep -Eq '^[0-9a-f]{64}$' || die "The invite link has an invalid certificate fingerprint."
BASE="https://$SERVER"
printf '%sSenti setup%s for this Mac: about 2 minutes.\n' "$B" "$N"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# ------------------------------------------------------------------ 1. the company server
step "Checking the company server ($SERVER)"
if [ -n "$FP" ]; then
  # The server uses its own certificate authority. Fetch it without verification, then accept it only if it matches
  # the fingerprint in the invite; every later download is verified against it.
  curl -fsS --insecure --max-time 20 "$BASE/api/v1/tls/ca" -o "$TMP/ca.pem" \
    || die "Can't reach $SERVER. Check the network (office, VPN) or ask your administrator."
  [ "$(grep -c 'BEGIN CERTIFICATE' "$TMP/ca.pem")" = 1 ] || die "The server sent an unexpected certificate. Not installing."
  GOT=$(openssl x509 -in "$TMP/ca.pem" -outform der 2>/dev/null | shasum -a 256 | cut -d' ' -f1)
  [ "$GOT" = "$FP" ] || die "The server's certificate doesn't match your invite. Not installing: this may not be your company's server. Tell your administrator."
  CA="--cacert $TMP/ca.pem"
  ok "Certificate matches your invite"
else
  CA=""
  ok "Publicly trusted certificate"
fi
fetch() { # shellcheck disable=SC2086
  curl -fsS --max-time 300 $CA "$@"; }

# ------------------------------------------------------------------ 2. download Senti
step "Downloading Senti from your company's server"
fetch "$BASE/downloads/senti-engine.tar.gz" -o "$TMP/senti.tgz" || die "Download failed. Is the server up to date? (./senti-server update)"
fetch "$BASE/downloads/senti-engine.tar.gz.sha256" -o "$TMP/sha" || die "Download failed (checksum)."
[ "$(shasum -a 256 "$TMP/senti.tgz" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$TMP/sha")" ] || die "The download is damaged. Try again."
ok "Downloaded and checked"

# ------------------------------------------------------------------ 3. tools
step "Tools"
export PATH="$BIN:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || die "Could not install uv (https://docs.astral.sh/uv/)."
  export PATH="$BIN:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || die "uv was installed but isn't on PATH; open a new Terminal window and run this again."
fi
ok "uv $(uv --version 2>/dev/null | cut -d' ' -f2)"
if xcode-select -p >/dev/null 2>&1; then
  ok "Apple command line tools (Secure Enclave key, fast hooks)"
else
  warn "Apple's command line tools let Senti keep this Mac's key in the Secure Enclave, where it can't be copied."
  if ask "Install them now? (about 1 GB, a window opens)"; then
    xcode-select --install >/dev/null 2>&1 || true
    printf '  Click "Install" in the window that opened. Waiting'
    i=0
    while ! xcode-select -p >/dev/null 2>&1; do
      sleep 10; i=$((i + 1)); printf '.'
      # stop waiting if the installer window was closed without installing
      if [ "$i" -gt 3 ] && ! pgrep -f "Install Command Line Developer Tools" >/dev/null 2>&1; then break; fi
      [ "$i" -lt 180 ] || break
    done
    echo
  fi
  if xcode-select -p >/dev/null 2>&1; then ok "Apple command line tools installed"
  else warn "Continuing without them: Senti uses a software key (your administrator sees this on the Devices page)."; fi
fi

# ------------------------------------------------------------------ 4. install
step "Installing Senti"
mkdir -p "$APP"
if [ -x "$APP/app/.venv/bin/senti" ]; then "$APP/app/.venv/bin/senti" stop >/dev/null 2>&1 || true; fi
rm -rf "$APP/app.new" "$APP/app.old"
mkdir -p "$APP/app.new"
tar xzf "$TMP/senti.tgz" -C "$APP/app.new"
[ -d "$APP/app" ] && mv "$APP/app" "$APP/app.old"
mv "$APP/app.new" "$APP/app"
if ! (cd "$APP/app" && uv sync --frozen --no-dev --quiet); then
  rm -rf "$APP/app"; [ -d "$APP/app.old" ] && mv "$APP/app.old" "$APP/app"
  die "Could not install Senti's Python packages (network?). Nothing was changed."
fi
rm -rf "$APP/app.old"
mkdir -p "$BIN"
ln -sf "$APP/app/.venv/bin/senti" "$BIN/senti"
ok "Installed in ~/Library/Application Support/Senti (command: senti)"

# ------------------------------------------------------------------ 5. join
step "Joining your company"
# shellcheck disable=SC2086
"$BIN/senti" join "$LINK" $EXTRA
case ":$PATH:" in *":$BIN:"*) ;; *) warn "Open a new Terminal window to use the 'senti' command (it is in ~/.local/bin)." ;; esac
