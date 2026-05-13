#!/bin/zsh

set -euo pipefail

# Usage:
#   ./scripts/smoke-test.sh
#   ADMIN_USERNAME=admin ADMIN_PASSWORD='change-me-now' ADMIN_EMAIL=admin@example.com ./scripts/smoke-test.sh
#   BASE_URL=http://localhost:8080 SMOKE_IMAGE=localhost:8080/test/smoke:phase3 ./scripts/smoke-test.sh

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
if [[ "${ALLOW_DEV_DEFAULT_CREDENTIALS:-0}" == "1" ]]; then
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me-now}"
  ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
else
  : "${ADMIN_PASSWORD:?Set ADMIN_PASSWORD or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
  : "${ADMIN_EMAIL:?Set ADMIN_EMAIL or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
fi
APP_ENV="${APP_ENV:-development}"
APP_VERSION="${APP_VERSION:-$(git branch --show-current 2>/dev/null || true)}"
APP_VERSION="${APP_VERSION:-development}"
APP_REVISION="${APP_REVISION:-$(git rev-parse HEAD 2>/dev/null || true)}"
APP_REVISION="${APP_REVISION:-dev}"
APP_BUILD_TIME="${APP_BUILD_TIME:-$(date -u '+%Y-%m-%dT%H:%M:%SZ')}"
APP_IMAGE_TAG="${APP_IMAGE_TAG:-$APP_VERSION}"
REGISTRY_SERVICE="${REGISTRY_SERVICE:-sheldylew-registry}"
SMOKE_IMAGE="${SMOKE_IMAGE:-localhost:8080/test/smoke:phase3}"
BASE_URL="${BASE_URL:-http://localhost:8080}"

workdir="$(cd "$(dirname "$0")/.." && pwd)"
cookie_jar="$(mktemp)"
login_body="$(mktemp)"
trap 'rm -f "$cookie_jar" "$login_body"' EXIT

wait_for_http() {
  local url="$1"
  local expected="${2:-200}"
  local attempt

  for attempt in {1..30}; do
    local http_status
    http_status="$(curl -s -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$http_status" == "$expected" ]]; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for $url to return $expected" >&2
  return 1
}

cd "$workdir"

compose() {
  docker compose -f docker-compose.yml -f docker-compose.local.yml "$@"
}

# Always rebuild from source so UI/backend changes are reflected in the running stack.
echo "==> Starting Docker stack"
echo "==> Rebuilding Docker stack without cache"
APP_ENV="$APP_ENV" \
APP_VERSION="$APP_VERSION" \
APP_REVISION="$APP_REVISION" \
APP_BUILD_TIME="$APP_BUILD_TIME" \
APP_IMAGE_TAG="$APP_IMAGE_TAG" \
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
ADMIN_EMAIL="$ADMIN_EMAIL" \
compose build --no-cache

# Recreate containers after the rebuild so nginx, web, api, and registry all use the latest images.
echo "==> Recreating Docker stack"
APP_ENV="$APP_ENV" \
APP_VERSION="$APP_VERSION" \
APP_REVISION="$APP_REVISION" \
APP_BUILD_TIME="$APP_BUILD_TIME" \
APP_IMAGE_TAG="$APP_IMAGE_TAG" \
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
ADMIN_EMAIL="$ADMIN_EMAIL" \
compose up -d --force-recreate

# Wait for the front-door health check before making authenticated requests.
echo "==> Waiting for API health"
wait_for_http "$BASE_URL/healthz" 200

# Verify the browser-facing login page is serving through nginx.
echo "==> Verifying login page renders through nginx"
curl -fsS "$BASE_URL/login" | grep -q "Sign in"

# Exercise the session login API and store cookies for the authenticated page check.
echo "==> Verifying browser login API"
curl -fsS \
  -c "$cookie_jar" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" \
  "$BASE_URL/api/session/login" > "$login_body"
grep -q "\"username\":\"$ADMIN_USERNAME\"" "$login_body"

# Confirm the authenticated admin UI renders with the issued session cookie.
echo "==> Verifying authenticated admin page render"
curl -fsS -b "$cookie_jar" "$BASE_URL/admin" | grep -q "Signed in as"

# Verify registry token issuance before running Docker CLI flows.
echo "==> Verifying registry bearer-token issuance"
curl -fsS -u "$ADMIN_USERNAME:$ADMIN_PASSWORD" \
  "$BASE_URL/auth/token?service=$REGISTRY_SERVICE&scope=repository:test/smoke:pull,push" | grep -q '"token"'

# Rebuild the smoke image from source each run so registry push/pull tests use fresh content.
echo "==> Building smoke image"
docker build --no-cache -t "$SMOKE_IMAGE" ./smoke

# Authenticate the Docker CLI against the local registry through the control plane.
echo "==> Verifying Docker login"
print -rn -- "$ADMIN_PASSWORD" | docker login localhost:8080 --username "$ADMIN_USERNAME" --password-stdin >/dev/null

# Push validates write auth and registry upload routing.
echo "==> Verifying Docker push"
docker push "$SMOKE_IMAGE" >/dev/null

# Remove the local tag first so the final pull proves a real registry download path.
echo "==> Verifying Docker pull"
docker image rm "$SMOKE_IMAGE" >/dev/null 2>&1 || true
docker pull "$SMOKE_IMAGE" >/dev/null

echo "Smoke test passed"
