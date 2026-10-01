#!/bin/sh
# Backups of the production database (ADR 0005, docs/backups.md). Runs in the
# `backup` service of compose.yml, which sets PGHOST/PGUSER/PGPASSWORD/PGDATABASE.
#
#   backup.sh               every night at BACKUP_HOUR_UTC: dump, then delete old dumps
#   backup.sh once          one dump now
#   backup.sh restore-test  one dump now, restored into a scratch database and
#                           compared table by table with the live database
set -eu

BACKUP_DIR=/backups
KEEP_DAYS="${KEEP_DAYS:-14}"
BACKUP_HOUR_UTC="${BACKUP_HOUR_UTC:-01}"
SCRATCH_DB=pmp_restore_test

# The dumps hold password hashes: readable by root only.
umask 077

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

backup() {
  file="$BACKUP_DIR/pmp-$(date -u +%Y-%m-%d_%H%M%S).dump"
  # Written under another name first, so a failed dump never looks like a backup.
  if ! pg_dump --format=custom --file="$file.partial"; then
    rm -f "$file.partial"
    log "backup FAILED" >&2
    return 1
  fi
  mv "$file.partial" "$file"
  log "backup written: $file"
  # -mtime +N matches files at least N+1 days old, so KEEP_DAYS days remain.
  find "$BACKUP_DIR" -name 'pmp-*.dump' -mtime +"$((KEEP_DAYS - 1))" -print -delete
}

newest_backup() {
  ls -1 "$BACKUP_DIR"/pmp-*.dump | sort | tail -n 1
}

# One line per table: its name and row count.
row_counts() {
  psql --dbname="$1" --tuples-only --no-align --command="
    SELECT table_name || ' ' || (xpath('/row/c/text()', query_to_xml(
      format('SELECT count(*) AS c FROM public.%I', table_name), false, true, '')))[1]
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
    ORDER BY table_name"
}

restore_test() {
  backup
  file="$(newest_backup)"
  dropdb --if-exists "$SCRATCH_DB"
  createdb "$SCRATCH_DB"
  trap 'dropdb --if-exists "$SCRATCH_DB"' EXIT
  pg_restore --no-owner --exit-on-error --dbname="$SCRATCH_DB" "$file"
  live="$(row_counts "$PGDATABASE")"
  restored="$(row_counts "$SCRATCH_DB")"
  echo "$restored"
  if [ -z "$restored" ] || [ "$live" != "$restored" ]; then
    log "restore test FAILED: $file differs from the live database" >&2
    exit 1
  fi
  log "restore test passed: $file"
}

seconds_until_next_run() {
  now="$(date -u +%s)"
  next="$(date -u -d "today $BACKUP_HOUR_UTC:00" +%s)"
  if [ "$next" -le "$now" ]; then
    next="$(date -u -d "tomorrow $BACKUP_HOUR_UTC:00" +%s)"
  fi
  echo "$((next - now))"
}

case "${1:-nightly}" in
  once) backup ;;
  restore-test) restore_test ;;
  nightly)
    # Sleep in the background, so `docker compose stop` ends the wait at once.
    trap 'exit 0' TERM INT
    log "nightly backups at $BACKUP_HOUR_UTC:00 UTC, kept $KEEP_DAYS days"
    while true; do
      sleep "$(seconds_until_next_run)" &
      wait $!
      # A failed night is logged; the next night tries again.
      backup || true
    done
    ;;
  *)
    echo "usage: backup.sh [once|restore-test]" >&2
    exit 2
    ;;
esac
