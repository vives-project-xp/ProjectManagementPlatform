# Database backups in a Compose service

The production database is backed up by a `backup` service in `compose.yml` instead of a cron job configured by hand on the VM. It runs `backup/backup.sh` in the `postgres:16` image: a `pg_dump` every night at 01:00 UTC into `/opt/pmp/backups` on the VM, deleting dumps older than 14 days. The Deploy workflow starts it like every other service, so the setup is reproducible from the repository and needs no root access to the VM. After every deploy, the workflow also takes a backup, restores it into a scratch database and compares every table's row count with the live database.

## Consequences

- The backups live on the same VM as the database: they protect against mistakes and corruption, not against losing the VM. Copying them off the VM is a later decision.
- The dumps contain password hashes, so they are readable by root only.
- Every deploy adds one extra dump; all dumps follow the same 14-day retention.
