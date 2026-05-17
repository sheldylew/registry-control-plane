FROM registry:2.8.3 AS registrybin

FROM --platform=$BUILDPLATFORM python:3.12.9-slim-bookworm AS api-builder

ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY backend/requirements-runtime.txt ./requirements-runtime.txt
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) pip_platforms="--platform manylinux_2_34_x86_64 --platform manylinux_2_28_x86_64 --platform manylinux_2_26_x86_64 --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64" ;; \
      arm64) pip_platforms="--platform manylinux_2_34_aarch64 --platform manylinux_2_28_aarch64 --platform manylinux_2_26_aarch64 --platform manylinux2014_aarch64 --platform manylinux_2_17_aarch64" ;; \
      *) echo "Unsupported target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    pip install \
      --no-cache-dir \
      ${pip_platforms} \
      --implementation=cp \
      --python-version=3.12 \
      --abi=cp312 \
      --abi=abi3 \
      --only-binary=:all: \
      --target=/install/lib/python3.12/site-packages \
      -r requirements-runtime.txt

FROM --platform=$BUILDPLATFORM python:3.11.13-slim-bookworm AS auth-init-builder

ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY backend/requirements-auth-init.txt ./requirements-auth-init.txt
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) pip_platforms="--platform manylinux_2_34_x86_64 --platform manylinux_2_28_x86_64 --platform manylinux_2_26_x86_64 --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64" ;; \
      arm64) pip_platforms="--platform manylinux_2_34_aarch64 --platform manylinux_2_28_aarch64 --platform manylinux_2_26_aarch64 --platform manylinux2014_aarch64 --platform manylinux_2_17_aarch64" ;; \
      *) echo "Unsupported target architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    pip install \
      --no-cache-dir \
      ${pip_platforms} \
      --implementation=cp \
      --python-version=3.11 \
      --abi=cp311 \
      --abi=abi3 \
      --only-binary=:all: \
      --target=/install/lib/python3.11/site-packages \
      -r requirements-auth-init.txt

FROM --platform=$BUILDPLATFORM alpine:3.20 AS build-metadata

ARG APP_VERSION=dev
ARG APP_REVISION=dev
ARG APP_BUILD_TIME=
ARG APP_IMAGE_TAG=

RUN mkdir -p /out/srv /out/web; \
    for path in /out/srv/build-info.env /out/web/build-info.env; do \
      { \
        printf 'APP_VERSION=%s\n' "$APP_VERSION"; \
        printf 'APP_REVISION=%s\n' "$APP_REVISION"; \
        printf 'APP_BUILD_TIME=%s\n' "$APP_BUILD_TIME"; \
        printf 'APP_IMAGE_TAG=%s\n' "$APP_IMAGE_TAG"; \
      } > "$path"; \
    done

FROM python:3.12.9-slim-bookworm AS api

ARG APP_VERSION=dev
ARG APP_REVISION=dev
ARG APP_BUILD_TIME=
ARG APP_IMAGE_TAG=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_VERSION=${APP_VERSION} \
    APP_REVISION=${APP_REVISION} \
    APP_BUILD_TIME=${APP_BUILD_TIME} \
    APP_IMAGE_TAG=${APP_IMAGE_TAG} \
    DATABASE_URL=sqlite:////data/app.db \
    REGISTRY_STORAGE_ROOT=/var/lib/registry/docker/registry/v2/repositories \
    REGISTRY_STORAGE_USAGE_ROOT=/var/lib/registry/docker/registry/v2 \
    AUTH_PRIVATE_KEY_PATH=/run/auth-private/auth-private.pem \
    AUTH_PUBLIC_CERT_PATH=/run/auth-public/auth-cert.pem \
    SETUP_TOKEN_PATH=/data/setup-token.json \
    SETUP_COMPLETE_MARKER_PATH=/data/setup-complete \
    REGISTRY_NOTIFICATIONS_TOKEN_PATH=/data/registry-events-token \
    REGISTRY_RENDERED_CONFIG_PATH=/etc/docker/registry/config.yml \
    SESSION_COOKIE_SECURE=true

WORKDIR /srv

COPY --from=build-metadata --chown=10001:10001 /out/srv/build-info.env /srv/build-info.env
COPY --from=registrybin --chown=10001:10001 /bin/registry /usr/local/bin/registry
COPY --from=api-builder /install /usr/local
COPY --chown=10001:10001 backend ./backend
COPY --chown=10001:10001 docker/registry-config.yml.tmpl ./docker/registry-config.yml.tmpl
COPY --chown=10001:10001 scripts/auth-init.py ./scripts/auth-init.py
COPY --chown=10001:10001 --chmod=755 scripts/api-entrypoint.sh ./scripts/api-entrypoint.sh

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=1m --timeout=3s --retries=12 --start-period=5s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]

CMD ["./scripts/api-entrypoint.sh"]

FROM gcr.io/distroless/python3-debian12 AS auth-init

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv:/usr/local/lib/python3.11/site-packages \
    APP_ENV=production \
    AUTH_PRIVATE_KEY_PATH=/auth-private/auth-private.pem \
    AUTH_PUBLIC_CERT_PATH=/auth-public/auth-cert.pem \
    AUTH_BOOTSTRAP_MARKER_PATH=/data/auth-bootstrap-complete \
    SETUP_TOKEN_PATH=/data/setup-token.json \
    SETUP_COMPLETE_MARKER_PATH=/data/setup-complete \
    REGISTRY_NOTIFICATIONS_TOKEN_PATH=/data/registry-events-token \
    REGISTRY_RENDERED_CONFIG_PATH=/registry-config/config.yml \
    SESSION_COOKIE_SECURE=true

WORKDIR /srv

COPY --from=auth-init-builder /install /usr/local
COPY backend ./backend
COPY docker/registry-config.yml.tmpl ./docker/registry-config.yml.tmpl
COPY scripts/auth-init.py ./scripts/auth-init.py

CMD ["./scripts/auth-init.py"]

FROM --platform=$BUILDPLATFORM node:20.18.3-alpine3.20 AS web-builder

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /web

COPY package.json package-lock.json ./
# Reuse downloaded npm tarballs inside the build step to reduce repeat fetches.
RUN --mount=type=cache,target=/root/.npm \
    npm ci \
      --cache=/root/.npm \
      --fetch-retries=5 \
      --fetch-retry-factor=2 \
      --fetch-retry-mintimeout=1000 \
      --fetch-retry-maxtimeout=30000

COPY app ./app
COPY jsconfig.json ./
COPY next.config.mjs ./
COPY postcss.config.mjs ./

RUN npm run build:docker

FROM node:20.18.3-alpine3.20 AS web

ARG APP_VERSION=dev
ARG APP_REVISION=dev
ARG APP_BUILD_TIME=
ARG APP_IMAGE_TAG=

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    APP_VERSION=${APP_VERSION} \
    APP_REVISION=${APP_REVISION} \
    APP_BUILD_TIME=${APP_BUILD_TIME} \
    APP_IMAGE_TAG=${APP_IMAGE_TAG} \
    INTERNAL_API_BASE_URL=http://api:8000
WORKDIR /web

COPY --from=build-metadata --chown=10001:10001 /out/web/build-info.env /web/build-info.env
COPY --from=web-builder --chown=10001:10001 /web/.next/standalone ./
COPY --from=web-builder --chown=10001:10001 /web/.next/static ./.next/static

USER 10001:10001

EXPOSE 3000

HEALTHCHECK --interval=1m --timeout=3s --retries=12 --start-period=10s CMD wget -q -O /dev/null "http://$(hostname):3000/"

CMD ["node", "server.js"]

FROM nginx:1.27.4-alpine AS nginx

COPY docker/nginx-main.conf /etc/nginx/nginx.conf
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
