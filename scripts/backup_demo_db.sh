#!/bin/bash
# Daily backup of the demo/production Postgres database. Uses the exact same
# DATABASE_URL the app connects with (from /etc/complivibe/backend.env) so it
# always has the right grants -- no separate backup role to keep in sync.
set -euo pipefail

BACKUP_DIR="/home/ubuntu/complivibe_backups/db"
RETENTION_DAYS=14
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/complivibe_demo_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

DATABASE_URL="$(sudo grep '^DATABASE_URL=' /etc/complivibe/backend.env | cut -d= -f2-)"
# SQLAlchemy-style URLs (postgresql+psycopg://...) aren't accepted by pg_dump directly.
PG_URL="${DATABASE_URL/postgresql+psycopg/postgresql}"
PG_URL="${PG_URL/postgresql+psycopg2/postgresql}"
PG_URL="${PG_URL/postgresql+asyncpg/postgresql}"

pg_dump "$PG_URL" | gzip > "$OUT_FILE"

if [ ! -s "$OUT_FILE" ]; then
  echo "backup_demo_db: FAILED, empty output file $OUT_FILE" >&2
  exit 1
fi

gunzip -t "$OUT_FILE"
echo "backup_demo_db: OK -> $OUT_FILE ($(du -h "$OUT_FILE" | cut -f1))"

find "$BACKUP_DIR" -name 'complivibe_demo_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete
