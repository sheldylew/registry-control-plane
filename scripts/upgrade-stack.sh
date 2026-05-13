#!/bin/sh
set -eu

# Example:
#   ./scripts/upgrade-stack.sh
#   BACKUP_DIR=./backups ./scripts/upgrade-stack.sh

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

APP_VERSION="${APP_VERSION:-$(git branch --show-current 2>/dev/null || true)}"
APP_VERSION="${APP_VERSION:-development}"
APP_REVISION="${APP_REVISION:-$(git rev-parse HEAD 2>/dev/null || true)}"
APP_REVISION="${APP_REVISION:-dev}"
APP_BUILD_TIME="${APP_BUILD_TIME:-$(date -u '+%Y-%m-%dT%H:%M:%SZ')}"
APP_IMAGE_TAG="${APP_IMAGE_TAG:-$APP_VERSION}"

"${SCRIPT_DIR}/backup-db.sh"
APP_VERSION="$APP_VERSION" \
APP_REVISION="$APP_REVISION" \
APP_BUILD_TIME="$APP_BUILD_TIME" \
APP_IMAGE_TAG="$APP_IMAGE_TAG" \
docker compose build
APP_VERSION="$APP_VERSION" \
APP_REVISION="$APP_REVISION" \
APP_BUILD_TIME="$APP_BUILD_TIME" \
APP_IMAGE_TAG="$APP_IMAGE_TAG" \
docker compose up -d --force-recreate

echo "Stack rebuilt and recreated. The API entrypoint applies Alembic migrations on startup."
