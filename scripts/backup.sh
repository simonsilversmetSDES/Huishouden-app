#!/bin/sh
# Nachtelijke SQLite-backup met retentie (spec §11).
# Draait in de 'backup'-container; maakt meteen bij opstart een backup en
# daarna elke 24 uur. Bestanden ouder dan BACKUP_RETENTION_DAYS worden verwijderd.
set -e

apk add --no-cache sqlite >/dev/null

DB=/data/db/huishouden.db
DIR=/data/backups
RETENTION="${BACKUP_RETENTION_DAYS:-30}"

while true; do
    if [ "${BACKUP_ENABLED:-true}" = "true" ] && [ -f "$DB" ]; then
        mkdir -p "$DIR"
        STAMP=$(date +%Y%m%d)
        sqlite3 "$DB" ".backup '$DIR/huishouden-$STAMP.db'"
        echo "Backup gemaakt: huishouden-$STAMP.db"
        find "$DIR" -name 'huishouden-*.db' -mtime +"$RETENTION" -delete
    fi
    sleep 86400
done
