# Backups

The `backup` service in `compose.yml` (ADR 0005) dumps the production database with `pg_dump --format=custom` and archives the Project photos (the `photos` volume, mounted read-only) with `tar`:

- **When:** every night at 01:00 UTC, and once after every deploy (the Deploy workflow's restore test).
- **Where:** `/opt/pmp/backups/pmp-YYYY-MM-DD_HHMMSS.dump` and `/opt/pmp/backups/photos-YYYY-MM-DD_HHMMSS.tar.gz` on the VM (same timestamp), readable by root only.
- **How long:** 14 days; older dumps and photo archives are deleted after each backup.

The commands below run on the VM as root, or as `github-runner` (in the `docker` group). The `backup` container has the database connection set, so `pg_dump`, `pg_restore`, `psql`, `createdb` and `dropdb` need no arguments for it.

## See the backups

```sh
docker exec pmp-backup-1 ls -l /backups
docker logs pmp-backup-1
```

## Make a backup now

```sh
docker exec pmp-backup-1 sh /backup.sh once
```

## Test a restore

Makes a backup, restores it into the scratch database `pmp_restore_test`, compares every table's row count with the live database and drops the scratch database again. It also checks that the new photo archive can be read and holds as many files as the photos folder. The Deploy workflow runs this after every deploy.

```sh
docker exec pmp-backup-1 sh /backup.sh restore-test
```

## Restore the live database

This replaces all current data with the backup, so first make a backup of the current state (`once`, above).

1. Choose the dump: `docker exec pmp-backup-1 ls -l /backups`.
2. Stop the services that use the database:
   ```sh
   docker stop pmp-backend-1 pmp-frontend-1
   ```
3. Restore (replace the file name):
   ```sh
   docker exec pmp-backup-1 sh -c 'pg_restore --clean --if-exists --no-owner --exit-on-error --dbname="$PGDATABASE" /backups/pmp-2026-10-01_010000.dump'
   ```
4. Start them again and check the site:
   ```sh
   docker start pmp-backend-1 pmp-frontend-1
   curl -sk https://10.20.10.33/api/health
   ```

Restoring an older dump also restores its Alembic version; the next deploy migrates it up again.

## Restore the photos

Restore the photo archive with the same timestamp as the dump, so the photos match the database's `photo_version` values. The `backup` container mounts the photos read-only, so this uses a short-lived container with the volume mounted read-write (replace the file name):

```sh
docker stop pmp-backend-1
docker run --rm -v pmp_photos:/photos -v /opt/pmp/backups:/backups:ro postgres:16 \
  sh -c 'find /photos -mindepth 1 -delete && tar -xzf /backups/photos-2026-10-01_010000.tar.gz -C /photos'
docker start pmp-backend-1
```
