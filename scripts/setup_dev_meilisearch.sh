#!/usr/bin/env bash
# Provisions a LOCAL, DEV-ONLY Meilisearch server for exercising /search and
# SearchIndexingService against a real search backend, without Docker.
#
# This is NOT for production. Production hosting for Meilisearch is a
# separate deployment-planning decision -- see the Phase 1 audit notes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEILI_DIR="$REPO_ROOT/.dev_meilisearch"
BIN_DIR="$MEILI_DIR/bin"
DATA_DIR="$MEILI_DIR/data"
MEILI_VERSION="1.49.0"
MEILI_BIN="$BIN_DIR/meilisearch"
DEV_MEILI_ADDR="127.0.0.1:7700"

mkdir -p "$BIN_DIR" "$DATA_DIR"

if [ ! -x "$MEILI_BIN" ]; then
  echo "Downloading Meilisearch v${MEILI_VERSION} (dev-only, gitignored under .dev_meilisearch/)..."
  curl -sSL -o "$MEILI_BIN" \
    "https://github.com/meilisearch/meilisearch/releases/download/v${MEILI_VERSION}/meilisearch-linux-amd64"
  chmod +x "$MEILI_BIN"
fi

echo "Meilisearch binary ready at $MEILI_BIN"
echo "Start the local dev server with:"
echo "  $MEILI_BIN --db-path $DATA_DIR --http-addr $DEV_MEILI_ADDR --no-analytics"
echo
echo "Add these values to .env (already the defaults in app/core/config.py):"
echo "  MEILISEARCH_ENABLED=true"
echo "  MEILISEARCH_URL=http://$DEV_MEILI_ADDR"
