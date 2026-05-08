#!/bin/sh
set -eu

# Example:
#   ./scripts/upgrade-stack.sh
#   BACKUP_DIR=./backups ./scripts/upgrade-stack.sh

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

"${SCRIPT_DIR}/backup-db.sh"
docker compose build
docker compose up -d --force-recreate

echo "Stack rebuilt and recreated. The API entrypoint applies Alembic migrations on startup."
