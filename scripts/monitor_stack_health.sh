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

if [ -n "$FAILED" ]; then
  echo "$(date -u -Iseconds) UNHEALTHY:$FAILED" >> /var/log/complivibe/health-monitor.log
  echo "CompliVibe stack unhealthy:$FAILED" >&2
  exit 1
fi

echo "$(date -u -Iseconds) healthy" >> /var/log/complivibe/health-monitor.log
