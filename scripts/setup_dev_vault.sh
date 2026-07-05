#!/usr/bin/env bash
# Provisions a LOCAL, DEV-ONLY OpenBao server for running the secrets_service
# test suite and the migrate_secrets_to_vault.py script against a real
# vault-compatible backend, without Docker.
#
# This is NOT for production. Production points VAULT_ADDR/VAULT_TOKEN at a
# real, separately-operated OpenBao/Infisical deployment -- see
# docs/runbooks/secrets_migration_fernet_to_vault.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="$REPO_ROOT/.dev_vault"
BIN_DIR="$VAULT_DIR/bin"
BAO_VERSION="2.5.5"
BAO_BIN="$BIN_DIR/bao"
DEV_VAULT_ADDR="http://127.0.0.1:8210"
DEV_VAULT_TOKEN="dev-root-token"

mkdir -p "$BIN_DIR"

if [ ! -x "$BAO_BIN" ]; then
  echo "Downloading OpenBao v${BAO_VERSION} (dev-only, gitignored under .dev_vault/)..."
  TMP_TAR="$(mktemp)"
  curl -sL -o "$TMP_TAR" \
    "https://github.com/openbao/openbao/releases/download/v${BAO_VERSION}/bao_${BAO_VERSION}_Linux_x86_64.tar.gz"
  tar xzf "$TMP_TAR" -C "$BIN_DIR" bao
  rm -f "$TMP_TAR"
  chmod +x "$BAO_BIN"
fi

echo "OpenBao binary ready at $BAO_BIN"
echo "Start the local dev server with:"
echo "  $BAO_BIN server -dev -dev-listen-address=127.0.0.1:8210 -dev-root-token-id=$DEV_VAULT_TOKEN"
echo
echo "Add these values to .env:"
echo "  VAULT_ADDR=$DEV_VAULT_ADDR"
echo "  VAULT_TOKEN=$DEV_VAULT_TOKEN"
