#!/bin/zsh

set -euo pipefail

# Usage:
#   ./scripts/rebuild-stack.sh
#   ALLOW_DEV_DEFAULT_CREDENTIALS=1 ./scripts/rebuild-stack.sh
#   ADMIN_USERNAME=admin ADMIN_PASSWORD='change-me-now' ADMIN_EMAIL=admin@example.com ./scripts/rebuild-stack.sh
#
# This script fixes the stale-container problem by rebuilding the compose images
# and then force-recreating the running containers so nginx serves the new code.

ADMIN_USERNAME="${ADMIN_USERNAME:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-}"
if [[ "${ALLOW_DEV_DEFAULT_CREDENTIALS:-0}" == "1" ]]; then
  ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me-now}"
  ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
fi
APP_ENV="${APP_ENV:-development}"

workdir="$(cd "$(dirname "$0")/.." && pwd)"

cd "$workdir"

compose() {
  docker compose -f docker-compose.yml -f docker-compose.local.yml "$@"
}

echo "==> Building Docker images"
APP_ENV="$APP_ENV" \
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
ADMIN_EMAIL="$ADMIN_EMAIL" \
compose build

echo "==> Recreating running containers"
APP_ENV="$APP_ENV" \
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
ADMIN_EMAIL="$ADMIN_EMAIL" \
compose up -d --force-recreate

echo "Stack refreshed"
