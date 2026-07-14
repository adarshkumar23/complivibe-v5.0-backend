#!/bin/bash
# Production deploy script, run on the VPS itself (invoked over SSH by
# .github/workflows/deploy.yml via a forced-command deploy key). Assumes the
# migration-safety-gate job already re-verified a single alembic head before
# this ever runs.
set -euo pipefail

REPO_DIR="/home/ubuntu/complivibe-v4.0/complivibe-v4.0-backend"
cd "$REPO_DIR"

echo "==> Fetching latest main"
git fetch mirror main
git checkout main
git reset --hard mirror/main

echo "==> Installing dependencies"
.venv/bin/pip install -q -r requirements.txt

echo "==> Re-verifying single alembic head"
HEADS="$(.venv/bin/alembic heads | wc -l)"
if [ "$HEADS" -ne 1 ]; then
  echo "Multiple/zero alembic heads detected on the deploy target -- refusing to migrate." >&2
  .venv/bin/alembic heads
  exit 1
fi

echo "==> Running migrations"
.venv/bin/alembic upgrade head

echo "==> Restarting services"
sudo systemctl restart complivibe-backend.service

echo "==> Waiting for health check"
for i in $(seq 1 15); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null; then
    echo "==> Deploy OK, backend healthy"
    exit 0
  fi
  sleep 2
done

echo "Backend did not become healthy after restart" >&2
exit 1
