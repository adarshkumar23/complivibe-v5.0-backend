#!/bin/bash
# Daily backup of the production/demo Postgres database.
#
# CREDENTIALS: this script dumps as the local `postgres` superuser over Unix-socket
# peer authentication (pg_hba.conf: `local all postgres peer`) -- it uses NO password.
# This is deliberate and fixes two prior production incidents:
#
#   1) Credential drift (2026-07-15). The app role `complivibe_user` has a ROTATABLE
#      password. The previous script copied that password out of /etc/complivibe/backend.env.
#      When the role password was rotated server-side, the *unchanged* env file silently
#      went from working (manual run 2026-07-14 06:27) to "password authentication failed"
#      (timer run 2026-07-15 02:30). The live app only survived on its existing pooled
#      connections; the batch backup, which opens a fresh connection each run, broke first.
#      Peer auth is tied to the OS user, not a secret, so it cannot drift.
#
#   2) "permission denied for table alembic_version". `complivibe_user` did not have the
#      grants to LOCK/dump every object. The `postgres` superuser can dump everything
#      regardless of per-table grants.
#
# Only the DATABASE *NAME* is read from the app config, so the backup always targets
# whatever database the app is actually pointed at -- without ever touching its password.
set -euo pipefail

BACKUP_DIR="/home/ubuntu/complivibe_backups/db"
RETENTION_DAYS=14
MIN_BYTES=100000          # a real dump is ~4MB gz; anything under 100KB is broken/empty
MIN_TABLES=100            # sanity floor; prod currently has ~399 tables
HEALTH_LOG="/var/log/complivibe/health-monitor.log"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/complivibe_demo_${TIMESTAMP}.sql.gz"
TMP_FILE="${OUT_FILE}.partial"

mkdir -p "$BACKUP_DIR"

# fail LOUDLY: non-zero exit (systemd marks the unit `failed`) AND a line in the
# health-monitor log, which the 5-minute health monitor and any human both read.
# The old script could silently "succeed" on an empty pg_dump because it had no
# pipefail and only an `[ -s ]` check (a 20-byte gzip-of-empty passes `-s`).
fail() {
  local msg="backup_demo_db: FAILED -- $1"
  echo "$msg" >&2
  echo "$(date -u -Iseconds) BACKUP-FAILED: $1" >> "$HEALTH_LOG" 2>/dev/null || true
  rm -f "$TMP_FILE"
  exit 1
}

# Parse the DB name (never the password) from the app's own DATABASE_URL.
DATABASE_URL="$(sudo grep '^DATABASE_URL=' /etc/complivibe/backend.env | head -n1 | cut -d= -f2-)" \
  || fail "could not read DATABASE_URL from /etc/complivibe/backend.env"
DB_NAME="$(printf '%s' "$DATABASE_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
[ -n "$DB_NAME" ] || fail "could not parse database name from DATABASE_URL"

# Dump as the postgres superuser over peer auth. pipefail ensures a pg_dump failure
# fails the whole pipeline (the old bug: pg_dump could fail and gzip still exit 0).
if ! sudo -n -u postgres pg_dump "$DB_NAME" | gzip > "$TMP_FILE"; then
  fail "pg_dump/gzip pipeline failed for database '$DB_NAME'"
fi

# Validate the artifact BEFORE publishing it under its final name.
BYTES="$(stat -c%s "$TMP_FILE" 2>/dev/null || echo 0)"
[ "$BYTES" -ge "$MIN_BYTES" ] || fail "dump too small: $BYTES bytes (< $MIN_BYTES) for '$DB_NAME'"
gunzip -t "$TMP_FILE" || fail "gzip integrity check failed for $TMP_FILE"
TABLES="$(gunzip -c "$TMP_FILE" | grep -c '^CREATE TABLE ' || true)"
[ "$TABLES" -ge "$MIN_TABLES" ] || fail "only $TABLES tables in dump (< $MIN_TABLES) for '$DB_NAME'"

# Atomic publish: a partial/failed dump never occupies a real backup filename, so the
# freshness monitor can't be fooled by a truncated file.
mv -f "$TMP_FILE" "$OUT_FILE"
echo "backup_demo_db: OK -> $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1), $TABLES tables, db=$DB_NAME)"

find "$BACKUP_DIR" -name 'complivibe_demo_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete
