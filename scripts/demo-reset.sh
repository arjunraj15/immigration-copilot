#!/usr/bin/env bash
# Reset the local database to a clean demo state: the 100 intake-only cases, no documents, empty audit trails.
# Run it before every take or judging session. It never rebuilds or recreates a container.
#
#   1. back up the whole database and the AI prompts
#   2. drop and rebuild the schema with the migrations
#   3. put the prompts back, so edits made in the AI management page survive
#   4. set the audit checkpoint file aside, because every chain starts again
#   5. load the intake files (make seed-intake)
#
# Files already stored under /app/storage are not removed. New uploads get new ids and never read an old file.

set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/tmp/teamecho-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

db()      { docker compose exec -T db psql -U casedesk -d casedesk -v ON_ERROR_STOP=1 -q "$@"; }
backend() { docker compose exec -T backend "$@"; }

echo "1/5 Backing up to $BACKUP_DIR"
docker compose exec -T db pg_dump -U casedesk -d casedesk -Fc > "$BACKUP_DIR/full-$STAMP.dump"
docker compose exec -T db pg_dump -U casedesk -d casedesk --data-only --column-inserts --no-owner -t prompts -t prompt_versions > "$BACKUP_DIR/prompts-$STAMP.sql"

echo "2/5 Rebuilding the schema"
db -c "DROP SCHEMA public CASCADE" -c "CREATE SCHEMA public" -c "DROP EXTENSION IF EXISTS vector CASCADE" >/dev/null 2>&1
backend alembic upgrade head >/dev/null

echo "3/5 Restoring the prompts"
{ echo "BEGIN; SET session_replication_role = replica; TRUNCATE prompts, prompt_versions RESTART IDENTITY CASCADE;"; cat "$BACKUP_DIR/prompts-$STAMP.sql"; echo "COMMIT;"; } | db >/dev/null

echo "4/5 Resetting the audit checkpoint"
backend sh -c 'f=${AUDIT_CHECKPOINT_FILE:-/app/storage/audit_checkpoint.json}; [ -f "$f" ] && mv "$f" "$f.before_reset_'"$STAMP"'" || true'

echo "5/5 Loading the intake files"
backend python -m app.cases.seed --intake-only

echo
db -At -c "select 'cases ' || count(*) from cases" -c "select 'uploads ' || count(*) from uploads" -c "select 'prompts ' || count(*) from prompts" -c "select 'audit rows ' || count(*) from audit_log"
echo "Done. Backup: $BACKUP_DIR/full-$STAMP.dump"
