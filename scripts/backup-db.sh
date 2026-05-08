#!/bin/sh
set -eu

# Example:
#   ./scripts/backup-db.sh
#   BACKUP_DIR=./backups ./scripts/backup-db.sh

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
TARGET_DIR="${BACKUP_DIR}/${TIMESTAMP}"

umask 077
mkdir -p "${TARGET_DIR}"

docker compose cp api:/data/app.db "${TARGET_DIR}/app.db"
chmod 600 "${TARGET_DIR}/app.db"

echo "Database backup written to ${TARGET_DIR}/app.db"
echo "This file contains sensitive application auth state; keep it out of git and public artifacts."
