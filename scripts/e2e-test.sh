#!/bin/zsh

set -euo pipefail

# Usage:
#   ./scripts/e2e-test.sh
#   ADMIN_USERNAME=admin ADMIN_PASSWORD='change-me-now' ADMIN_EMAIL=admin@example.com ./scripts/e2e-test.sh
#
# This script:
# - rebuilds and recreates the local Docker stack via scripts/smoke-test.sh
# - seeds the Phase 4 permission matrix inside the running API container
# - exercises Docker CLI authz with real push/pull allow+deny cases
# - verifies live tag delete and empty-repository delete flows
# - verifies manual registry state rebuild repair flow
# - verifies a live GC job and the registry maintenance gate

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
if [[ "${ALLOW_DEV_DEFAULT_CREDENTIALS:-0}" == "1" ]]; then
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me-now}"
  ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
else
  : "${ADMIN_PASSWORD:?Set ADMIN_PASSWORD or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
  : "${ADMIN_EMAIL:?Set ADMIN_EMAIL or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
fi
APP_ENV="${APP_ENV:-development}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
PUBLIC_REGISTRY_ORIGIN="${PUBLIC_REGISTRY_ORIGIN:-http://localhost:8080}"

READER_USERNAME="${READER_USERNAME:-reader}"
READER_PASSWORD="${READER_PASSWORD:-reader-pass-123}"
DEVELOPER_USERNAME="${DEVELOPER_USERNAME:-developer}"
DEVELOPER_PASSWORD="${DEVELOPER_PASSWORD:-developer-pass-123}"
ROBOT_USERNAME="${ROBOT_USERNAME:-ci-sheldylew}"
ROBOT_TOKEN="${ROBOT_TOKEN:-rcr_robot_c1c1c1c1.0123456789abcdef0123456789abcdef}"
REVOKED_ROBOT_TOKEN="${REVOKED_ROBOT_TOKEN:-rcr_robot_d2d2d2d2.fedcba9876543210fedcba9876543210}"
PAGINATION_DEFAULT_PAGE_SIZE="${PAGINATION_DEFAULT_PAGE_SIZE:-25}"

FIXTURE_IMAGE="${FIXTURE_IMAGE:-localhost:8080/sheldylew/fixture:e2e}"
READER_DENIED_IMAGE="${READER_DENIED_IMAGE:-localhost:8080/sheldylew/reader-denied:e2e}"
DEVELOPER_OK_IMAGE="${DEVELOPER_OK_IMAGE:-localhost:8080/sheldylew/developer-ok:e2e}"
DEVELOPER_DENIED_IMAGE="${DEVELOPER_DENIED_IMAGE:-localhost:8080/otherns/developer-denied:e2e}"
ROBOT_OK_IMAGE="${ROBOT_OK_IMAGE:-localhost:8080/sheldylew/sheldylew.com:e2e}"
DELETE_IMAGE="${DELETE_IMAGE:-localhost:8080/sheldylew/delete-me:e2e}"
GC_IMAGE="${GC_IMAGE:-localhost:8080/sheldylew/gc-me:e2e}"

workdir="$(cd "$(dirname "$0")/.." && pwd)"
admin_cookie_jar="$(mktemp)"
admin_login_body="$(mktemp)"
trap 'rm -f "$admin_cookie_jar" "$admin_login_body"' EXIT

json_get() {
  local path="$1"
  /usr/bin/python3 -c '
import json
import sys

value = json.load(sys.stdin)
for part in sys.argv[1].split("."):
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value[part]
if isinstance(value, bool):
    print("true" if value else "false")
elif value is None:
    print("null")
else:
    print(value)
' "$path"
}

assert_paginated_collection() {
  local url="$1"
  local collection_path="$2"
  local pagination_path="$3"
  local expected_page_size="$4"
  local min_total="$5"
  local expected_page="$6"
  local body

  body="$(curl -fsS -b "$admin_cookie_jar" "$url")"
  ASSERT_PAGINATED_BODY="$body" /usr/bin/python3 - "$expected_page_size" "$min_total" "$expected_page" "$collection_path" "$pagination_path" <<'PY'
import json
import os
import sys

expected_page_size = int(sys.argv[1])
min_total = int(sys.argv[2])
expected_page = int(sys.argv[3])
collection_path = sys.argv[4]
pagination_path = sys.argv[5]

payload = json.loads(os.environ["ASSERT_PAGINATED_BODY"])

def resolve(root, path):
    value = root
    for part in path.split("."):
        value = value[part]
    return value

collection = resolve(payload, collection_path)
pagination = resolve(payload, pagination_path)
total = int(pagination["total"])
page = int(pagination["page"])
page_size = int(pagination["page_size"])
returned = len(collection)

if page != expected_page:
    raise SystemExit(f"Expected page {expected_page}, got {page}")
if page_size != expected_page_size:
    raise SystemExit(f"Expected page size {expected_page_size}, got {page_size}")
if total < min_total:
    raise SystemExit(f"Expected at least {min_total} total items, got {total}")

remaining = max(total - ((expected_page - 1) * expected_page_size), 0)
expected_returned = min(expected_page_size, remaining)
if returned != expected_returned:
    raise SystemExit(f"Expected {expected_returned} returned items, got {returned}")
if expected_page == 1 and total > expected_page_size and not pagination["has_next"]:
    raise SystemExit("Expected a next page but has_next was false")
if expected_page > 1 and not pagination["has_prev"]:
    raise SystemExit("Expected a previous page but has_prev was false")
PY
}

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

wait_for_authed_http() {
  local url="$1"
  local expected="${2:-200}"
  local cookie_jar="$3"
  local attempt

  for attempt in {1..30}; do
    local http_status
    http_status="$(curl -s -b "$cookie_jar" -o /dev/null -w '%{http_code}' "$url" || true)"
    if [[ "$http_status" == "$expected" ]]; then
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for $url to return $expected with auth." >&2
  return 1
}

docker_logout() {
  docker logout localhost:8080 >/dev/null 2>&1 || true
}

docker_login() {
  local username="$1"
  local secret="$2"
  docker_logout
  print -rn -- "$secret" | docker login localhost:8080 --username "$username" --password-stdin >/dev/null
}

expect_docker_failure() {
  local output="$1"
  local lowered
  lowered="$(print -r -- "$output" | tr '[:upper:]' '[:lower:]')"
  if [[ "$lowered" != *"denied"* && "$lowered" != *"unauthorized"* && "$lowered" != *"insufficient_scope"* ]]; then
    echo "Expected Docker command to fail with authz/authn error." >&2
    print -r -- "$output" >&2
    return 1
  fi
}

build_local_image() {
  local tag="$1"
  docker build --no-cache -t "$tag" ./smoke >/dev/null
}

admin_login() {
  curl -fsS \
    -c "$admin_cookie_jar" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" \
    "$BASE_URL/api/session/login" > "$admin_login_body"
  grep -q "\"username\":\"$ADMIN_USERNAME\"" "$admin_login_body"
}

admin_csrf() {
  /usr/bin/python3 - "$admin_cookie_jar" <<'PY'
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    for line in handle:
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.rstrip("\n").split("\t")
        if len(fields) >= 7 and fields[5] == "rcr_csrf":
            print(fields[6])
            raise SystemExit(0)
raise SystemExit("Missing rcr_csrf cookie")
PY
}

poll_gc_job() {
  local job_id="$1"
  local saw_gate="0"
  local saw_summary_gate="0"
  local attempt

  for attempt in {1..80}; do
    local v2_status
    v2_status="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/v2/" || true)"
    if [[ "$v2_status" == "503" ]]; then
      saw_gate="1"
    fi

    local summary
    summary="$(curl -fsS -b "$admin_cookie_jar" "$BASE_URL/api/admin/maintenance")"
    local gate_enabled
    gate_enabled="$(print -r -- "$summary" | json_get registry_gate_enabled)"
    if [[ "$gate_enabled" == "true" ]]; then
      saw_summary_gate="1"
    fi

    local job_status
    job_status="$(print -r -- "$summary" | /usr/bin/python3 -c '
import json
import sys

job_id = int(sys.argv[1])
payload = json.load(sys.stdin)
for job in payload["jobs"]:
    if job["id"] == job_id:
        print(job["status"])
        raise SystemExit(0)
active_job = payload.get("active_job")
if active_job and active_job["id"] == job_id:
    print(active_job["status"])
    raise SystemExit(0)
last_job = payload.get("last_job")
if last_job and last_job["id"] == job_id:
    print(last_job["status"])
    raise SystemExit(0)
print("missing")
' "$job_id")"

    if [[ "$job_status" == "succeeded" ]]; then
      if [[ "$saw_gate" != "1" && "$saw_summary_gate" != "1" ]]; then
        echo "GC job succeeded, but maintenance gate was never observed." >&2
        return 1
      fi
      return 0
    fi

    if [[ "$job_status" == "failed" ]]; then
      echo "GC job failed." >&2
      print -r -- "$summary" >&2
      return 1
    fi

    sleep 0.25
  done

  echo "Timed out waiting for GC job $job_id to finish." >&2
  return 1
}

poll_rebuild_job() {
  local job_id="$1"
  local attempt

  for attempt in {1..120}; do
    local v2_status
    v2_status="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/v2/" || true)"
    if [[ "$v2_status" == "503" ]]; then
      echo "Registry state rebuild unexpectedly enabled the maintenance gate." >&2
      return 1
    fi

    local summary
    summary="$(curl -fsS -b "$admin_cookie_jar" "$BASE_URL/api/admin/maintenance")"
    local job_status
    job_status="$(print -r -- "$summary" | /usr/bin/python3 -c '
import json
import sys

job_id = int(sys.argv[1])
payload = json.load(sys.stdin)
for job in payload["rebuild_jobs"]:
    if job["id"] == job_id:
        print(job["status"])
        raise SystemExit(0)
print("missing")
' "$job_id")"

    if [[ "$job_status" == "succeeded" ]]; then
      return 0
    fi

    if [[ "$job_status" == "failed" ]]; then
      echo "Registry state rebuild job failed." >&2
      print -r -- "$summary" >&2
      return 1
    fi

    sleep 0.25
  done

  echo "Timed out waiting for registry state rebuild job $job_id to finish." >&2
  return 1
}

cd "$workdir"

compose() {
  APP_ENV="$APP_ENV" \
  PUBLIC_REGISTRY_ORIGIN="$PUBLIC_REGISTRY_ORIGIN" \
  ADMIN_USERNAME="$ADMIN_USERNAME" \
  ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ADMIN_EMAIL="$ADMIN_EMAIL" \
  docker compose -f docker-compose.yml -f docker-compose.local.yml "$@"
}

echo "==> Running base smoke test"
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
ADMIN_EMAIL="$ADMIN_EMAIL" \
ALLOW_DEV_DEFAULT_CREDENTIALS="${ALLOW_DEV_DEFAULT_CREDENTIALS:-0}" \
APP_ENV="$APP_ENV" \
ADMIN_USERNAME="$ADMIN_USERNAME" \
ADMIN_PASSWORD="$ADMIN_PASSWORD" \
ADMIN_EMAIL="$ADMIN_EMAIL" \
./scripts/smoke-test.sh

echo "==> Seeding permission matrix"
compose exec -T -e ALLOW_PHASE4_SEED=1 api python -m backend.phase4_seed >/dev/null

echo "==> Seeding pagination fixtures"
pagination_seed_json="$(compose exec -T -e ALLOW_PHASE4_SEED=1 api python -m backend.pagination_seed)"
activity_user_id="$(print -r -- "$pagination_seed_json" | json_get activity_user_id)"
tag_repository="$(print -r -- "$pagination_seed_json" | json_get tag_repository)"

echo "==> Logging into UI as admin"
admin_login
csrf_token="$(admin_csrf)"

echo "==> Updating shared default page size"
settings_response="$(
  curl -fsS \
    -b "$admin_cookie_jar" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf_token" \
    -d "{\"public_registry_origin\":\"$PUBLIC_REGISTRY_ORIGIN\",\"ui_timezone\":\"America/Los_Angeles\",\"repository_tags_page_size\":$PAGINATION_DEFAULT_PAGE_SIZE,\"automatic_registry_state_rebuild\":false,\"storage_usage_refresh_interval_seconds\":3600}" \
    "$BASE_URL/api/admin/settings"
)"
if [[ "$(print -r -- "$settings_response" | json_get settings.repository_tags_page_size)" != "$PAGINATION_DEFAULT_PAGE_SIZE" ]]; then
  echo "Failed to update shared default page size." >&2
  print -r -- "$settings_response" >&2
  exit 1
fi
if [[ "$(print -r -- "$settings_response" | json_get registry_restart_required)" != "false" ]]; then
  echo "Page size update unexpectedly required a registry restart." >&2
  print -r -- "$settings_response" >&2
  exit 1
fi

echo "==> Verifying shared default pagination across live endpoints"
assert_paginated_collection "$BASE_URL/api/admin/users" "users" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/admin/users?page=2" "users" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/admin/users/$activity_user_id" "recent_activity" "activity_pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/admin/users/$activity_user_id?activity_page=2" "recent_activity" "activity_pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/admin/sessions" "sessions" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/admin/sessions?page=2" "sessions" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/admin/sessions?page_size=7" "sessions" "pagination" 7 50 1
assert_paginated_collection "$BASE_URL/api/admin/tokens" "tokens" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/admin/tokens?page=2" "tokens" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/admin/permissions" "permissions" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/admin/permissions?page=2" "permissions" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/admin/audit" "events" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/admin/audit?page=2" "events" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/admin/maintenance" "jobs" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/admin/maintenance?page=2" "jobs" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/repos" "repos" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/repos?page=2" "repos" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2
assert_paginated_collection "$BASE_URL/api/repos/$tag_repository/tags" "tags" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 1
assert_paginated_collection "$BASE_URL/api/repos/$tag_repository/tags?page=2" "tags" "pagination" "$PAGINATION_DEFAULT_PAGE_SIZE" 50 2

echo "==> Building fixture image"
build_local_image "$FIXTURE_IMAGE"

echo "==> Pushing admin fixture image"
docker_login "$ADMIN_USERNAME" "$ADMIN_PASSWORD"
docker push "$FIXTURE_IMAGE" >/dev/null

echo "==> Verifying reader can pull allowed repo"
docker image rm "$FIXTURE_IMAGE" >/dev/null 2>&1 || true
docker_login "$READER_USERNAME" "$READER_PASSWORD"
docker pull "$FIXTURE_IMAGE" >/dev/null

echo "==> Verifying reader cannot push"
build_local_image "$READER_DENIED_IMAGE"
docker_login "$READER_USERNAME" "$READER_PASSWORD"
if push_output="$(docker push "$READER_DENIED_IMAGE" 2>&1)"; then
  echo "Reader push unexpectedly succeeded." >&2
  exit 1
fi
expect_docker_failure "$push_output"

echo "==> Verifying developer can push allowed namespace"
build_local_image "$DEVELOPER_OK_IMAGE"
docker_login "$DEVELOPER_USERNAME" "$DEVELOPER_PASSWORD"
docker push "$DEVELOPER_OK_IMAGE" >/dev/null

echo "==> Verifying developer cannot push outside namespace"
build_local_image "$DEVELOPER_DENIED_IMAGE"
docker_login "$DEVELOPER_USERNAME" "$DEVELOPER_PASSWORD"
if push_output="$(docker push "$DEVELOPER_DENIED_IMAGE" 2>&1)"; then
  echo "Developer push to denied namespace unexpectedly succeeded." >&2
  exit 1
fi
expect_docker_failure "$push_output"

echo "==> Verifying robot can push exact allowed repo"
build_local_image "$ROBOT_OK_IMAGE"
docker_login "$ROBOT_USERNAME" "$ROBOT_TOKEN"
docker push "$ROBOT_OK_IMAGE" >/dev/null

echo "==> Verifying revoked robot token cannot log in"
docker_logout
if login_output="$(print -rn -- "$REVOKED_ROBOT_TOKEN" | docker login localhost:8080 --username "$ROBOT_USERNAME" --password-stdin 2>&1)"; then
  echo "Revoked robot token unexpectedly authenticated." >&2
  exit 1
fi
expect_docker_failure "$login_output"

echo "==> Verifying live tag delete"
build_local_image "$DELETE_IMAGE"
docker_login "$ADMIN_USERNAME" "$ADMIN_PASSWORD"
docker push "$DELETE_IMAGE" >/dev/null
wait_for_authed_http "$BASE_URL/api/repos/sheldylew/delete-me/tags/e2e" 200 "$admin_cookie_jar"
curl -fsS \
  -b "$admin_cookie_jar" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $csrf_token" \
  -d '{"confirmation":"sheldylew/delete-me:e2e"}' \
  "$BASE_URL/api/repos/sheldylew/delete-me/tags/e2e/delete" >/dev/null
wait_for_authed_http "$BASE_URL/api/repos/sheldylew/delete-me/tags/e2e" 404 "$admin_cookie_jar"

echo "==> Verifying empty repository delete prunes storage"
curl -fsS \
  -b "$admin_cookie_jar" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $csrf_token" \
  -d '{"confirmation":"sheldylew/delete-me"}' \
  "$BASE_URL/api/repos/sheldylew/delete-me/delete" >/dev/null
compose exec -T api sh -lc '[ ! -d "/var/lib/registry/docker/registry/v2/repositories/sheldylew/delete-me" ]'

echo "==> Verifying manual registry state rebuild"
rebuild_response="$(
  curl -fsS \
    -b "$admin_cookie_jar" \
    -H "X-CSRF-Token: $csrf_token" \
    -X POST \
    "$BASE_URL/api/admin/maintenance/cache/rebuild"
)"
rebuild_job_id="$(print -r -- "$rebuild_response" | json_get job.id)"
poll_rebuild_job "$rebuild_job_id"

echo "==> Preparing GC candidate"
build_local_image "$GC_IMAGE"
docker_login "$ADMIN_USERNAME" "$ADMIN_PASSWORD"
docker push "$GC_IMAGE" >/dev/null
wait_for_authed_http "$BASE_URL/api/repos/sheldylew/gc-me/tags/e2e" 200 "$admin_cookie_jar"
curl -fsS \
  -b "$admin_cookie_jar" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $csrf_token" \
  -d '{"confirmation":"sheldylew/gc-me:e2e"}' \
  "$BASE_URL/api/repos/sheldylew/gc-me/tags/e2e/delete" >/dev/null

echo "==> Verifying live GC job and maintenance gate"
gc_response="$(
  curl -fsS \
    -b "$admin_cookie_jar" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf_token" \
    -d '{"confirmation":"RUN GC","dry_run":false,"delete_untagged":false,"prune_empty_dirs":true}' \
    "$BASE_URL/api/admin/maintenance/jobs"
)"
gc_job_id="$(print -r -- "$gc_response" | json_get job.id)"
poll_gc_job "$gc_job_id"

echo "End-to-end test passed"
