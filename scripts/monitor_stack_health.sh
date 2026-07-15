#!/bin/bash
# Health check for the systemd-managed stack: backend, frontend, vault.
# Exits non-zero (and logs a failure line) if anything is unhealthy, so it
# works as a systemd oneshot triggered by complivibe-health-monitor.timer.
set -uo pipefail

FAILED=""

check() {
  local name="$1" url="$2" expect="$3"
  body="$(curl -s -m 5 "$url")"
  if [ $? -ne 0 ] || [[ "$body" != *"$expect"* ]]; then
    FAILED="$FAILED $name"
  fi
}

check backend  "http://127.0.0.1:8000/health" '"status":"ok"'
check frontend "http://127.0.0.1:3000"          "<"

VAULT_STATUS="$(BAO_ADDR=http://127.0.0.1:8230 /usr/local/bin/bao status -format=json 2>/dev/null)"
if [[ "$VAULT_STATUS" != *'"sealed": false'* ]]; then
  FAILED="$FAILED vault"
fi

# Backup freshness: a valid DB backup (>=100KB) must exist from within the last 26h.
# This catches BOTH a failed backup run and a stopped/misfiring timer -- the failure
# mode that went unnoticed for ~2 weeks in July 2026 (silent empty dumps). find prints
# the file only if it is both recent enough and non-trivially sized.
FRESH_BACKUP="$(find /home/ubuntu/complivibe_backups/db -name 'complivibe_demo_*.sql.gz' \
  -mmin -1560 -size +100k -print -quit 2>/dev/null)"
if [ -z "$FRESH_BACKUP" ]; then
  FAILED="$FAILED backup(stale-or-missing)"
fi

if [ -n "$FAILED" ]; then
  echo "$(date -u -Iseconds) UNHEALTHY:$FAILED" >> /var/log/complivibe/health-monitor.log
  echo "CompliVibe stack unhealthy:$FAILED" >&2
  exit 1
fi

echo "$(date -u -Iseconds) healthy" >> /var/log/complivibe/health-monitor.log
