FROM registry:2.8.3 AS registrybin

FROM python:3.12.9-slim-bookworm AS api-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY backend/requirements-runtime.txt ./requirements-runtime.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements-runtime.txt

FROM python:3.11.13-slim-bookworm AS auth-init-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY backend/requirements-auth-init.txt ./requirements-auth-init.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements-auth-init.txt

FROM python:3.12.9-slim-bookworm AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app

WORKDIR /srv

COPY --from=registrybin --chown=app:app /bin/registry /usr/local/bin/registry
COPY --from=api-builder /install /usr/local
COPY --chown=app:app backend ./backend
COPY --chown=app:app docker/registry-config.yml.tmpl ./docker/registry-config.yml.tmpl
COPY --chown=app:app scripts/auth-init.py ./scripts/auth-init.py
COPY --chown=app:app --chmod=755 scripts/api-entrypoint.sh ./scripts/api-entrypoint.sh

USER app

EXPOSE 8000

CMD ["./scripts/api-entrypoint.sh"]

FROM gcr.io/distroless/python3-debian12 AS auth-init

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv:/usr/local/lib/python3.11/site-packages

WORKDIR /srv

COPY --from=auth-init-builder /install /usr/local
COPY backend ./backend
COPY docker/registry-config.yml.tmpl ./docker/registry-config.yml.tmpl
COPY scripts/auth-init.py ./scripts/auth-init.py

CMD ["./scripts/auth-init.py"]

FROM node:20.18.3-alpine3.20 AS web-builder

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /web

COPY package.json package-lock.json ./
RUN npm ci

COPY app ./app
COPY jsconfig.json ./
COPY next.config.mjs ./
COPY postcss.config.mjs ./

RUN npm run build

FROM node:20.18.3-alpine3.20 AS web

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /web

RUN addgroup -g 10001 -S app && adduser -S -D -H -u 10001 -G app app

COPY --from=web-builder --chown=app:app /web/.next/standalone ./
COPY --from=web-builder --chown=app:app /web/.next/static ./.next/static

USER app

EXPOSE 3000

CMD ["node", "server.js"]
