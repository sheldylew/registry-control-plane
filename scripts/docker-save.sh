#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/docker-save.sh [--tag TAG] [--output DIR] [--image-prefix PREFIX] [--platform PLATFORM]

Build the project's Docker images and export them into a local releases directory
using `docker save`.

  Options:
  --tag TAG              Image tag to apply to all project images (default: latest)
  --output DIR           Release output directory (default: ./releases/<tag>)
  --image-prefix PREFIX  Prefix for built image names (default: registry-control-plane)
  --platform PLATFORM    Docker platform to build for (default: linux/amd64, or host platform)
  --arch ARCH            Shortcut for Raspberry Pi and common architectures
  -f, --force           Force overwrite of an existing release directory
  -h, --help            Show this help

  Example:
  ./scripts/docker-save.sh --tag v1.2.3 --output releases/2026-05-09
  ./scripts/docker-save.sh --output releases/latest
EOF
}

IMAGE_PREFIX="registry-control-plane"
OUTPUT_DIR=""
IMAGE_TAG=""
PLATFORM=""
PLATFORM_SOURCE=""
FORCE_OVERWRITE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      IMAGE_TAG="${2:?missing value for --tag}"
      shift 2
      ;;
    --output)
      OUTPUT_DIR="${2:?missing value for --output}"
      shift 2
      ;;
    --image-prefix)
      IMAGE_PREFIX="${2:?missing value for --image-prefix}"
      shift 2
      ;;
    --platform)
      PLATFORM="${2:?missing value for --platform}"
      PLATFORM_SOURCE="explicit --platform"
      shift 2
      ;;
    --arch)
      arch="${2:?missing value for --arch}"
      shift 2
      case "$arch" in
        amd64|x86_64|x86-64)
          PLATFORM="linux/amd64"
          PLATFORM_SOURCE="explicit --arch (${arch})"
          ;;
        arm64|aarch64|arm64v8|linux/arm64|linux/arm64/v8|arm-v8|arm64-v8|raspberry|rpi|raspberry-pi)
          PLATFORM="linux/arm64"
          PLATFORM_SOURCE="explicit --arch (${arch})"
          ;;
        armv7|arm/v7|armv7l|arm32|arm32v7|linux/arm/v7)
          PLATFORM="linux/arm/v7"
          PLATFORM_SOURCE="explicit --arch (${arch})"
          ;;
        *)
          PLATFORM="$arch"
          PLATFORM_SOURCE="explicit --platform (${arch})"
          ;;
      esac
      ;;
    -f|--force)
      FORCE_OVERWRITE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

[[ -z "${IMAGE_TAG}" ]] && IMAGE_TAG="latest"
if [[ -z "${PLATFORM}" ]]; then
  host_arch="$(uname -m)"
  case "$(uname -m)" in
    x86_64|amd64)
      PLATFORM="linux/amd64"
      PLATFORM_SOURCE="auto-detected host (${host_arch})"
      ;;
    aarch64|arm64)
      PLATFORM="linux/arm64"
      PLATFORM_SOURCE="auto-detected host (${host_arch})"
      ;;
    *)
      PLATFORM="linux/amd64"
      PLATFORM_SOURCE="auto-detected host (${host_arch})"
      ;;
  esac
fi
PLATFORM_SOURCE="${PLATFORM_SOURCE:-computed from input flags or default}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE_DIR="${OUTPUT_DIR:-"$ROOT_DIR/releases/$IMAGE_TAG"}"

if [[ -d "$RELEASE_DIR" ]]; then
  if [[ "$FORCE_OVERWRITE" -eq 1 ]]; then
    rm -rf "$RELEASE_DIR"
  else
    if [[ -t 0 ]]; then
      read -r -p "Release directory '$RELEASE_DIR' already exists. Overwrite it? [y/N] " _overwrite_reply
      case "$_overwrite_reply" in
        [Yy]|[Yy][Ee][Ss])
          rm -rf "$RELEASE_DIR"
          ;;
        *)
          echo "Aborting without making changes."
          exit 1
          ;;
      esac
    else
      echo "Release directory '$RELEASE_DIR' already exists. Use --force to overwrite it." >&2
      exit 1
    fi
  fi
fi

mkdir -p "$RELEASE_DIR"

cd "$ROOT_DIR"

services=("api" "web" "auth-init" "nginx")
AUTH_INIT_IMAGE=""
API_IMAGE=""
WEB_IMAGE=""
NGINX_IMAGE=""
for service in "${services[@]}"; do
  image_name="${IMAGE_PREFIX}-${service}:${IMAGE_TAG}"

  case "$service" in
    auth-init)
      AUTH_INIT_IMAGE="$image_name"
      ;;
    api)
      API_IMAGE="$image_name"
      ;;
    web)
      WEB_IMAGE="$image_name"
      ;;
    nginx)
      NGINX_IMAGE="$image_name"
      ;;
  esac
done

if ! docker buildx inspect >/dev/null 2>&1; then
  echo "docker buildx is required for this script." >&2
  exit 1
fi

echo "==> Building images with docker buildx bake for ${PLATFORM}"
docker buildx bake \
  -f docker-bake.hcl \
  --var "IMAGE_PREFIX=$IMAGE_PREFIX" \
  --var "IMAGE_TAG=$IMAGE_TAG" \
  --var "PLATFORM=$PLATFORM" \
  validate-amd64

for service in "${services[@]}"; do
  image_name="${IMAGE_PREFIX}-${service}:${IMAGE_TAG}"
  echo "==> Exporting $image_name"
  docker save --output "$RELEASE_DIR/${service}-${IMAGE_TAG}.tar" "$image_name"
done

if [[ -z "$AUTH_INIT_IMAGE" || -z "$API_IMAGE" || -z "$WEB_IMAGE" || -z "$NGINX_IMAGE" ]]; then
  echo "Failed to capture all built image names." >&2
  exit 1
fi

cat >"$RELEASE_DIR/docker-compose.yml" <<EOF
services:
  auth-init:
    image: ${AUTH_INIT_IMAGE}
    user: "0:0"
    restart: "no"
    command:
      - ./scripts/auth-init.py
    environment:
      APP_ENV: \${APP_ENV:-production}
      PUBLIC_REGISTRY_ORIGIN: \${PUBLIC_REGISTRY_ORIGIN:-}
      TOKEN_ISSUER: \${TOKEN_ISSUER:-sheldylew-registry}
      TOKEN_SERVICE: \${TOKEN_SERVICE:-sheldylew-registry}
      AUTH_PRIVATE_KEY_PATH: /auth-private/auth-private.pem
      AUTH_PUBLIC_CERT_PATH: /auth-public/auth-cert.pem
      AUTH_BOOTSTRAP_MARKER_PATH: /data/auth-bootstrap-complete
      SETUP_TOKEN_PATH: /data/setup-token.json
      SETUP_COMPLETE_MARKER_PATH: /data/setup-complete
      REGISTRY_RENDERED_CONFIG_PATH: /registry-config/config.yml
      ADMIN_USERNAME: \${ADMIN_USERNAME:-}
      ADMIN_PASSWORD: \${ADMIN_PASSWORD:-}
      ADMIN_EMAIL: \${ADMIN_EMAIL:-}
      SESSION_COOKIE_SECURE: \${SESSION_COOKIE_SECURE:-true}
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    volumes:
      - app-data:/data
      - registry-data:/var/lib/registry
      - auth-private-data:/auth-private
      - auth-public-data:/auth-public
      - registry-config-data:/registry-config

  nginx:
    image: ${NGINX_IMAGE}
    restart: unless-stopped
    user: "101:101"
    ports:
      - "\${RCP_HTTP_BIND:-127.0.0.1:8080}:8080"
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - FOWNER
      - DAC_OVERRIDE
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    depends_on:
      api:
        condition: service_healthy
      web:
        condition: service_healthy
      registry:
        condition: service_started

  api:
    image: ${API_IMAGE}
    restart: unless-stopped
    environment:
      APP_ENV: \${APP_ENV:-production}
      DATABASE_URL: sqlite:////data/app.db
      REGISTRY_INTERNAL_URL: http://registry:5000
      REGISTRY_STORAGE_ROOT: /var/lib/registry/docker/registry/v2/repositories
      PUBLIC_REGISTRY_ORIGIN: \${PUBLIC_REGISTRY_ORIGIN:-}
      CSRF_TRUSTED_ORIGINS: \${CSRF_TRUSTED_ORIGINS:-}
      TOKEN_ISSUER: \${TOKEN_ISSUER:-sheldylew-registry}
      TOKEN_SERVICE: \${TOKEN_SERVICE:-sheldylew-registry}
      TOKEN_TTL_SECONDS: \${TOKEN_TTL_SECONDS:-900}
      REGISTRY_CATALOG_MAX_PAGES: \${REGISTRY_CATALOG_MAX_PAGES:-10}
      DASHBOARD_MAX_REPOSITORIES: \${DASHBOARD_MAX_REPOSITORIES:-50}
      REPOSITORY_TAGS_MAX_ITEMS: \${REPOSITORY_TAGS_MAX_ITEMS:-100}
      MANIFEST_CHILDREN_MAX_ITEMS: \${MANIFEST_CHILDREN_MAX_ITEMS:-25}
      HISTORY_ENTRIES_MAX_ITEMS: \${HISTORY_ENTRIES_MAX_ITEMS:-50}
      LOGIN_RATE_LIMIT_ATTEMPTS: \${LOGIN_RATE_LIMIT_ATTEMPTS:-5}
      LOGIN_RATE_LIMIT_WINDOW_SECONDS: \${LOGIN_RATE_LIMIT_WINDOW_SECONDS:-60}
      AUTH_TOKEN_RATE_LIMIT_ATTEMPTS: \${AUTH_TOKEN_RATE_LIMIT_ATTEMPTS:-10}
      AUTH_TOKEN_RATE_LIMIT_WINDOW_SECONDS: \${AUTH_TOKEN_RATE_LIMIT_WINDOW_SECONDS:-60}
      AUTH_PRIVATE_KEY_PATH: /run/auth-private/auth-private.pem
      AUTH_PUBLIC_CERT_PATH: /run/auth-public/auth-cert.pem
      SETUP_TOKEN_PATH: /data/setup-token.json
      SETUP_COMPLETE_MARKER_PATH: /data/setup-complete
      REGISTRY_GC_CONFIG_PATH: /etc/docker/registry/config.yml
      REGISTRY_RENDERED_CONFIG_PATH: /etc/docker/registry/config.yml
      REGISTRY_CONFIG_TEMPLATE_PATH: /srv/docker/registry-config.yml.tmpl
      FORWARDED_ALLOW_IPS: \${FORWARDED_ALLOW_IPS:-*}
      ADMIN_USERNAME: \${ADMIN_USERNAME:-}
      ADMIN_PASSWORD: \${ADMIN_PASSWORD:-}
      ADMIN_EMAIL: \${ADMIN_EMAIL:-}
      SESSION_COOKIE_SECURE: \${SESSION_COOKIE_SECURE:-true}
    user: "10001:10001"
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    volumes:
      - app-data:/data
      - registry-data:/var/lib/registry
      - auth-private-data:/run/auth-private:ro
      - auth-public-data:/run/auth-public:ro
      - registry-config-data:/etc/docker/registry
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - |
          import urllib.request
          urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=2)
      interval: 5s
      timeout: 3s
      retries: 12
      start_period: 5s
    depends_on:
      auth-init:
        condition: service_completed_successfully

  web:
    image: ${WEB_IMAGE}
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_BASE_PATH: /api
      NEXT_PUBLIC_AUTH_TOKEN_PATH: /auth/token
      NEXT_PUBLIC_REGISTRY_BASE_PATH: /v2/
      INTERNAL_API_BASE_URL: http://api:8000
    user: "10001:10001"
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    healthcheck:
      test:
        - CMD-SHELL
        - wget -q -O /dev/null "http://\$(hostname):3000/login"
      interval: 5s
      timeout: 3s
      retries: 12
      start_period: 10s

  registry:
    image: registry:2.8.3
    restart: unless-stopped
    user: "10001:10001"
    volumes:
      - registry-data:/var/lib/registry
      - registry-config-data:/etc/docker/registry:ro
      - auth-public-data:/certs:ro
    environment:
      REGISTRY_HTTP_ADDR: 0.0.0.0:5000
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp
    depends_on:
      auth-init:
        condition: service_completed_successfully

volumes:
  app-data:
  registry-data:
  auth-private-data:
  auth-public-data:
  registry-config-data:
EOF

cat >"$RELEASE_DIR/README.md" <<EOF
Release package for image tag: ${IMAGE_TAG}
Built for platform: ${PLATFORM}
Platform source: ${PLATFORM_SOURCE}

Loaded images:

- ${AUTH_INIT_IMAGE}
- ${API_IMAGE}
- ${WEB_IMAGE}
- ${NGINX_IMAGE}

Load images:

1. Load each image tarball:

   - docker load -i api-${IMAGE_TAG}.tar
   - docker load -i auth-init-${IMAGE_TAG}.tar
   - docker load -i web-${IMAGE_TAG}.tar
   - docker load -i nginx-${IMAGE_TAG}.tar

2. Start the stack:

   docker compose -f docker-compose.yml up -d
EOF

echo "Release package prepared at: $RELEASE_DIR"
