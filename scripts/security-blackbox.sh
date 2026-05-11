#!/bin/zsh

set -euo pipefail

# Black-box security test runner against Dockerized stack.
# Default behavior runs for ~30 minutes.
#
# Examples:
#   ALLOW_DEV_DEFAULT_CREDENTIALS=1 ./scripts/security-blackbox.sh
#   ADMIN_PASSWORD='change-me-now' ADMIN_EMAIL=admin@example.com ./scripts/security-blackbox.sh
#   DURATION_SECONDS=1800 LOOP_SLEEP_SECONDS=1 ./scripts/security-blackbox.sh

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
if [[ "${ALLOW_DEV_DEFAULT_CREDENTIALS:-0}" == "1" ]]; then
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-change-me-now}"
  ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
else
  : "${ADMIN_PASSWORD:?Set ADMIN_PASSWORD or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
  : "${ADMIN_EMAIL:?Set ADMIN_EMAIL or ALLOW_DEV_DEFAULT_CREDENTIALS=1 for local defaults.}"
fi

BASE_URL="${BASE_URL:-http://localhost:8080}"
DURATION_SECONDS="${DURATION_SECONDS:-1800}"
LOOP_SLEEP_SECONDS="${LOOP_SLEEP_SECONDS:-1}"
ATTACKER_ORIGIN="${ATTACKER_ORIGIN:-https://evil.example}"
HEAVY_CHECK_EVERY_ROUNDS="${HEAVY_CHECK_EVERY_ROUNDS:-10}"

READER_USERNAME="${READER_USERNAME:-reader}"
READER_PASSWORD="${READER_PASSWORD:-reader-pass-123}"
DEVELOPER_USERNAME="${DEVELOPER_USERNAME:-developer}"
DEVELOPER_PASSWORD="${DEVELOPER_PASSWORD:-developer-pass-123}"

workdir="$(cd "$(dirname "$0")/.." && pwd)"
admin_cookie_jar="$(mktemp)"
admin_login_body="$(mktemp)"
trap 'rm -f "$admin_cookie_jar" "$admin_login_body"' EXIT

fail() {
  print -u2 -- "[FAIL] $1"
  exit 1
}

expect_status() {
  local expected="$1"
  local got="$2"
  local label="$3"
  [[ "$got" == "$expected" ]] || fail "$label expected HTTP $expected, got $got"
}

basic_auth() {
  local username="$1"
  local secret="$2"
  /usr/bin/python3 - "$username" "$secret" <<'PY'
import base64
import sys
raw = f"{sys.argv[1]}:{sys.argv[2]}".encode("utf-8")
print("Basic " + base64.b64encode(raw).decode("ascii"))
PY
}

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' "$@"
}

wait_for_http() {
  local url="$1"
  local expected="${2:-200}"
  local i
  for i in {1..60}; do
    local http_status
    http_status="$(http_code "$url" || true)"
    if [[ "$http_status" == "$expected" ]]; then
      return 0
    fi
    sleep 1
  done
  fail "Timed out waiting for $url -> $expected"
}

admin_login() {
  curl -fsS -c "$admin_cookie_jar" -H "Content-Type: application/json" \
    -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}" \
    "$BASE_URL/api/session/login" > "$admin_login_body"
}

admin_csrf() {
  /usr/bin/python3 - "$admin_cookie_jar" <<'PY'
import sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 7 and parts[5] == "rcr_csrf":
            print(parts[6])
            raise SystemExit(0)
raise SystemExit("missing rcr_csrf")
PY
}

run_stack_and_seed() {
  cd "$workdir"
  compose() {
    docker compose -f docker-compose.yml -f docker-compose.local.yml "$@"
  }

  print -- "==> Booting stack via smoke-test"
  ADMIN_USERNAME="$ADMIN_USERNAME" \
  ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  ADMIN_EMAIL="$ADMIN_EMAIL" \
  ALLOW_DEV_DEFAULT_CREDENTIALS="${ALLOW_DEV_DEFAULT_CREDENTIALS:-0}" \
  ./scripts/smoke-test.sh

  print -- "==> Seeding Phase 4 users/permissions"
  compose exec -T -e ALLOW_PHASE4_SEED=1 api python -m backend.phase4_seed >/dev/null

  wait_for_http "$BASE_URL/healthz" 200
}

check_auth_bypass() {
  local s1 s2
  s1="$(http_code "$BASE_URL/api/admin/users")"
  expect_status 401 "$s1" "unauthenticated admin list"

  s2="$(http_code "$BASE_URL/api/repos")"
  expect_status 401 "$s2" "unauthenticated repo list"
}

check_token_forgery_and_misuse() {
  local bad_basic
  bad_basic="$(basic_auth "$READER_USERNAME" "wrong-password")"

  local s1
  s1="$(http_code -H "Authorization: $bad_basic" "$BASE_URL/auth/token?service=sheldylew-registry&scope=repository:sheldylew/app:pull,push,delete")"
  expect_status 401 "$s1" "bad basic credentials token request"

  local s2
  s2="$(http_code -H "Authorization: Bearer forged.not.a.jwt" "$BASE_URL/api/session/me")"
  expect_status 401 "$s2" "forged bearer against UI session endpoint"

  local dev_basic
  dev_basic="$(basic_auth "$DEVELOPER_USERNAME" "$DEVELOPER_PASSWORD")"
  local s3
  s3="$(http_code -H "Authorization: $dev_basic" "$BASE_URL/auth/token?service=sheldylew-registry&scope=registry:catalog:*")"
  expect_status 200 "$s3" "developer catalog overreach token request"
}

check_path_traversal() {
  admin_login
  local csrf
  csrf="$(admin_csrf)"

  local s
  s="$(http_code \
    -b "$admin_cookie_jar" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf" \
    -d '{"confirmation":"../escape"}' \
    "$BASE_URL/api/repos/%2E%2E/escape/delete")"
  if [[ "$s" != "400" && "$s" != "404" ]]; then
    fail "path traversal repository delete expected HTTP 400/404, got $s"
  fi
}

check_cors_abuse() {
  admin_login
  local csrf
  csrf="$(admin_csrf)"

  local s1
  s1="$(http_code \
    -b "$admin_cookie_jar" \
    -H "Origin: $ATTACKER_ORIGIN" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf" \
    -d '{"name":"xsite-attempt"}' \
    "$BASE_URL/api/admin/tokens")"
  expect_status 403 "$s1" "cross-site origin on destructive endpoint"

  local s2
  s2="$(http_code \
    -b "$admin_cookie_jar" \
    -H "Sec-Fetch-Site: cross-site" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf" \
    -d '{"dry_run":true,"delete_untagged":false,"prune_empty_dirs":false}' \
    "$BASE_URL/api/admin/maintenance/jobs")"
  expect_status 403 "$s2" "cross-site fetch metadata on destructive endpoint"
}

check_destructive_ops_and_escalation() {
  local reader_basic
  reader_basic="$(basic_auth "$READER_USERNAME" "$READER_PASSWORD")"

  local s1
  s1="$(http_code -H "Authorization: $reader_basic" "$BASE_URL/auth/token?service=sheldylew-registry&scope=repository:sheldylew/app:delete")"
  expect_status 200 "$s1" "reader delete scope escalation request"

  local login_status
  login_status="$(curl -sS -o /dev/null -w '%{http_code}' -c "$admin_cookie_jar" -H 'Content-Type: application/json' -d "{\"username\":\"$READER_USERNAME\",\"password\":\"$READER_PASSWORD\"}" "$BASE_URL/api/session/login")"
  expect_status 200 "$login_status" "reader login"
  local csrf
  csrf="$(admin_csrf)"

  local s2
  s2="$(http_code \
    -b "$admin_cookie_jar" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf" \
    -d '{"confirmation":"sheldylew/app:e2e"}' \
    "$BASE_URL/api/repos/sheldylew/app/tags/e2e/delete")"
  if [[ "$s2" != "403" && "$s2" != "404" ]]; then
    fail "reader destructive tag delete expected HTTP 403/404, got $s2"
  fi

  local s3
  s3="$(http_code \
    -b "$admin_cookie_jar" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf" \
    -d '{"confirmation":"sheldylew/app"}' \
    "$BASE_URL/api/repos/sheldylew/app/delete")"
  expect_status 403 "$s3" "reader destructive repository delete"
}

check_registry_api_misuse() {
  local s1
  s1="$(http_code "$BASE_URL/v2/_catalog")"
  if [[ "$s1" != "401" && "$s1" != "403" ]]; then
    fail "anonymous registry catalog probe expected 401/403, got $s1"
  fi

  local s2
  s2="$(http_code "$BASE_URL/v2/nonexistent/repo/manifests/latest")"
  if [[ "$s2" != "401" && "$s2" != "403" && "$s2" != "404" ]]; then
    fail "registry manifest misuse expected 401/403/404, got $s2"
  fi
}

check_public_pull_paths() {
  admin_login
  local csrf
  csrf="$(admin_csrf)"

  local visibility_status
  visibility_status="$(http_code \
    -b "$admin_cookie_jar" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $csrf" \
    -d '{"repository_name":"sheldylew/fixture","visibility":"public"}' \
    "$BASE_URL/api/admin/repositories/visibility")"
  expect_status 200 "$visibility_status" "set fixture repository public visibility"

  local s1
  s1="$(http_code "$BASE_URL/auth/token?service=sheldylew-registry&scope=repository:sheldylew/fixture:pull")"
  expect_status 200 "$s1" "anonymous public pull token request"

  local s2
  s2="$(http_code "$BASE_URL/auth/token?service=sheldylew-registry&scope=repository:sheldylew/fixture:pull,push")"
  expect_status 401 "$s2" "anonymous public push token request"
}

run_random_scenario() {
  local pick
  pick="$(( (RANDOM % 7) + 1 ))"
  case "$pick" in
    1) check_auth_bypass ;;
    2) check_token_forgery_and_misuse ;;
    3) check_path_traversal ;;
    4) check_cors_abuse ;;
    5) check_destructive_ops_and_escalation ;;
    6) check_registry_api_misuse ;;
    7) check_public_pull_paths ;;
    *) fail "invalid scenario pick: $pick" ;;
  esac
}

run_phase_mix() {
  local phase="$1"
  case "$phase" in
    warmup)
      check_auth_bypass
      check_token_forgery_and_misuse
      check_registry_api_misuse
      check_public_pull_paths
      ;;
    steady)
      run_random_scenario
      run_random_scenario
      run_random_scenario
      ;;
    spike)
      check_auth_bypass
      check_token_forgery_and_misuse
      check_path_traversal
      check_cors_abuse
      check_destructive_ops_and_escalation
      check_registry_api_misuse
      check_public_pull_paths
      run_random_scenario
      run_random_scenario
      ;;
    *)
      fail "unknown phase: $phase"
      ;;
  esac
}

main() {
  run_stack_and_seed

  print -- "==> Running black-box security scenarios for ${DURATION_SECONDS}s with phased randomized mix"
  local deadline
  deadline="$(( $(date +%s) + DURATION_SECONDS ))"
  local round=0

  while [[ "$(date +%s)" -lt "$deadline" ]]; do
    round="$((round + 1))"
    local now remaining phase
    now="$(date +%s)"
    remaining="$((deadline - now))"

    if [[ "$round" -le 5 ]]; then
      phase="warmup"
    elif (( round % 7 == 0 )); then
      phase="spike"
    else
      phase="steady"
    fi

    print -- "--> Round $round phase=$phase remaining=${remaining}s"
    run_phase_mix "$phase"

    if (( round % HEAVY_CHECK_EVERY_ROUNDS == 0 )); then
      print -- "----> Heavy full-pass check"
      check_auth_bypass
      check_token_forgery_and_misuse
      check_path_traversal
      check_cors_abuse
      check_destructive_ops_and_escalation
      check_registry_api_misuse
      check_public_pull_paths
    fi

    sleep "$((LOOP_SLEEP_SECONDS + (RANDOM % 2)))"
  done

  print -- "Security black-box test passed (${round} rounds)."
}

main "$@"
