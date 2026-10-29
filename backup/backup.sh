#!/bin/sh
# Backups of the production database, the Project photos and the Chat files
# (ADR 0005, docs/backups.md). Runs in the `backup` service of compose.yml, which
# sets PGHOST/PGUSER/PGPASSWORD/PGDATABASE and mounts both folders read-only.
#
#   backup.sh               every night at BACKUP_HOUR_UTC: back up, then delete
#                           old backups
#   backup.sh once          one backup now
#   backup.sh restore-test  one backup now; the dump is restored into a scratch
#                           database and compared table by table with the live
#                           database as it was during the dump (backed up again,
#                           up to 3 times, when it changed meanwhile); the photo
#                           archive is compared file count with the photos folder,
#                           the Chat files archive with the restored chat_files rows
set -eu

BACKUP_DIR=/backups
PHOTOS_DIR=/photos
CHAT_FILES_DIR=/chat-files
KEEP_DAYS="${KEEP_DAYS:-14}"
BACKUP_HOUR_UTC="${BACKUP_HOUR_UTC:-01}"
SCRATCH_DB=pmp_restore_test

# The dumps hold password hashes: readable by root only.
umask 077

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

backup() {
  stamp="$(date -u +%Y-%m-%d_%H%M%S)"
  file="$BACKUP_DIR/pmp-$stamp.dump"
  photos="$BACKUP_DIR/photos-$stamp.tar.gz"
  chat_files="$BACKUP_DIR/chat-files-$stamp.tar.gz"
  # Written under another name first, so a failed backup never looks like one.
  if ! pg_dump --format=custom --file="$file.partial"; then
    rm -f "$file.partial"
    log "backup FAILED" >&2
    return 1
  fi
  mv "$file.partial" "$file"
  log "backup written: $file"
  if ! tar -czf "$photos.partial" -C "$PHOTOS_DIR" .; then
    rm -f "$photos.partial"
    log "photo backup FAILED" >&2
    return 1
  fi
  mv "$photos.partial" "$photos"
  log "photo backup written: $photos"
  if ! tar -czf "$chat_files.partial" -C "$CHAT_FILES_DIR" .; then
    rm -f "$chat_files.partial"
    log "chat files backup FAILED" >&2
    return 1
  fi
  mv "$chat_files.partial" "$chat_files"
  log "chat files backup written: $chat_files"
  # -mtime +N matches files at least N+1 days old, so KEEP_DAYS days remain.
  find "$BACKUP_DIR" \( -name 'pmp-*.dump' -o -name 'photos-*.tar.gz' \
    -o -name 'chat-files-*.tar.gz' \) -mtime +"$((KEEP_DAYS - 1))" -print -delete
}

newest_backup_matching() {
  ls -1 "$BACKUP_DIR"/$1 | sort | tail -n 1
}

# The number of files (not folders) in the photos folder, or in an archive of it.
photo_count() {
  find "$PHOTOS_DIR" -type f | wc -l
}

# The number of files in an archive (photos or Chat files).
archived_file_count() {
  tar -tzf "$1" | grep -v '/$' | wc -l
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
  # The site keeps writing (Chat, logins), so the live row counts are taken just
  # before and just after the dump: when they are equal, nothing changed during
  # the dump, and the restored database must hold exactly those counts.
  attempt=1
  while :; do
    before="$(row_counts "$PGDATABASE")"
    backup
    after="$(row_counts "$PGDATABASE")"
    [ "$before" = "$after" ] && break
    if [ "$attempt" -ge 3 ]; then
      log "restore test FAILED: the database kept changing during 3 backups" >&2
      exit 1
    fi
    log "the database changed during the backup; backing up again"
    attempt=$((attempt + 1))
    sleep 5
  done
  file="$(newest_backup_matching 'pmp-*.dump')"
  dropdb --if-exists "$SCRATCH_DB"
  createdb "$SCRATCH_DB"
  trap 'dropdb --if-exists "$SCRATCH_DB"' EXIT
  pg_restore --no-owner --exit-on-error --dbname="$SCRATCH_DB" "$file"
  restored="$(row_counts "$SCRATCH_DB")"
  echo "$restored"
  if [ -z "$restored" ] || [ "$before" != "$restored" ]; then
    log "restore test FAILED: $file differs from the live database" >&2
    echo "live database during the backup:" >&2
    echo "$before" >&2
    exit 1
  fi
  log "restore test passed: $file"

  photos="$(newest_backup_matching 'photos-*.tar.gz')"
  live="$(photo_count)"
  archived="$(archived_file_count "$photos")"
  echo "photos $archived"
  if [ "$live" != "$archived" ]; then
    log "photo restore test FAILED: $photos holds $archived files, not $live" >&2
    exit 1
  fi
  log "photo restore test passed: $photos"

  # Every chat_files row has one file, so the archive made with the dump holds
  # as many files as the restored table has rows.
  chat_files="$(newest_backup_matching 'chat-files-*.tar.gz')"
  rows="$(echo "$restored" | awk '$1 == "chat_files" { print $2 }')"
  archived="$(archived_file_count "$chat_files")"
  echo "chat files $archived"
  if [ "${rows:-0}" != "$archived" ]; then
    log "chat files restore test FAILED: $chat_files holds $archived files, not $rows" >&2
    exit 1
  fi
  log "chat files restore test passed: $chat_files"
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
