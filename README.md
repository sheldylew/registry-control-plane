# Registry Control Plane

A self-hosted Docker Registry control plane for managing access, administration, and day-to-day registry operations.

![Registry Control Plane hero](docs/registry-control-plane-hero.png)

## Overview

This project layers a web control plane in front of a Docker Registry deployment:

- `nginx` is the public entrypoint on `http://localhost:8080`
- `registry:2` serves the registry API behind `/v2/`
- FastAPI serves app APIs, registry auth, setup, health, and operational state endpoints
- Next.js serves the landing page, login/setup screens, admin UI, and repository browser
- SQLite-backed application state persists in a Docker volume
- RS256-signed bearer tokens back Docker client authentication

## Project expectations

This is a personal project that I use for my own registry operations and share publicly so others can inspect, learn from, and adapt it. It is provided as-is, with no support commitment or guarantee that it will fit another environment.

## Feature highlights

- First-boot setup mode with a one-time setup token or full `.env` bootstrap
- Admin-managed users, browser sessions, personal access tokens, and robot tokens
- Repository-level permissions with public or private visibility controls
- Anonymous pull-only access for repositories marked `public`
- Bounded catalog, tag, manifest, and history queries for larger registries
- Database-backed repository and tag state from registry push/delete notifications
- Maintenance controls for analysis-only runs, registry-state rebuilds, garbage collection, aggressive cleanup, and notification retries
- Runtime admin settings for the public origin, UI timezone, default page size, audit retention, startup rebuilds, and storage-usage refreshes
- Audit history plus retained maintenance job logs with configurable pruning
- Non-root container runtime hardening with generated signing material kept out of git
- Operator wrapper for stack checks, backups, logs, upgrades, and offline bundle operations
- Docker-backed smoke and end-to-end verification scripts

## Screenshots

| Admin dashboard | Repository detail |
| --- | --- |
| ![Admin dashboard showing control-plane identity, token, and registry counts](docs/screenshots/admin-dashboard.jpg) | ![Repository detail showing tags, digests, architecture, and public-read controls](docs/screenshots/repository-detail.jpg) |

| Maintenance status | Runtime settings |
| --- | --- |
| ![Maintenance page showing registry health, storage usage, manifest cache, and job status](docs/screenshots/maintenance-status.jpg) | ![Settings page showing public origin, restart guidance, timezone, pagination, and retention defaults](docs/screenshots/runtime-settings.jpg) |

## Deployment model

The supported package format is Docker Compose.

- `nginx` is the only public entrypoint and publishes port `8080`
- `registry:2` stays behind nginx and serves `/v2/`
- FastAPI owns auth, identity, permissions, setup, settings, registry state, maintenance, and token issuance
- Next.js owns the public entry screens, admin shell, repository browser, and dashboard UI
- SQLite application state persists in `app-data`
- Registry blobs persist in `registry-data`
- Signing material and rendered registry auth config live in dedicated Docker volumes

For production-style runs, the stack starts in locked setup mode until it has both:

- an admin user
- a saved public registry origin

That state can be created either through the first-boot setup wizard or by supplying all four bootstrap values in `.env`.

## Quick start

Most users should start from the public GHCR images:

```bash
docker compose -f docker-compose.ghcr.yml up -d
```

Open `http://localhost:8080/`.

This uses Docker-managed named volumes for persistent state, keeps the service
bound to localhost by default, and starts in first-boot setup mode. To complete
setup through the browser, read the one-time setup token from:

```bash
docker compose -f docker-compose.ghcr.yml logs auth-init
```

The default image tag is `release`. To pin a specific version:

```bash
RCP_IMAGE_TAG=v0.1.0 docker compose -f docker-compose.ghcr.yml up -d
```

Use the bind-local variant only when you specifically want persistent state in
visible host folders under `./data`:

```bash
docker compose -f docker-compose.bind-local.yml up -d
```

For local source development:

```bash
ALLOW_DEV_DEFAULT_CREDENTIALS=1 \
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Then open `http://localhost:8080/`.

For source-based deployment or detailed production configuration, follow the deployment guide in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Routine Compose operations can also go through the wrapper:

```bash
./scripts/rcp doctor
./scripts/rcp up
./scripts/rcp logs
```

## Configuration

The minimum production-facing configuration is:

```dotenv
PUBLIC_REGISTRY_ORIGIN=https://registry.example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace-with-a-long-random-password
ADMIN_EMAIL=admin@example.com
```

The repo also supports optional controls for:

- token TTL and rate limits
- session lifetime and cookie security
- CSRF trusted origins and forwarded proxy handling
- repository list and history response bounds
- UI timezone, default list page size, storage usage refresh interval, and automatic registry-state rebuild behavior
- maintenance gate timing, audit pruning, session/token record retention, and retained job log lifetime

### Browser login from LAN hostnames

Production runs default to secure browser cookies. Login can work from `http://localhost:8080` while failing from a plain HTTP LAN hostname because browsers treat `localhost` as a trustworthy development context, but they do not send `Secure` cookies over `http://some-lan-name:8080`.

For LAN browser access, put TLS in front of the stack and access the control plane through `https://...`. If the LAN HTTPS hostname differs from `PUBLIC_REGISTRY_ORIGIN`, add it to `CSRF_TRUSTED_ORIGINS` so cookie-authenticated admin writes pass the same-origin checks.

Keep `PUBLIC_REGISTRY_ORIGIN` as the Docker registry origin used in bearer-token challenges. Do not change it only to make browser login work from a LAN hostname.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the public configuration reference.

## Verification

The repo includes two main Docker-backed verification paths:

- `./scripts/smoke-test.sh` rebuilds the local stack and checks browser login, token issuance, and Docker push/pull through the control plane
- `./scripts/e2e-test.sh` seeds the permission matrix and exercises real allow and deny cases, delete flows, and live garbage collection behavior

There are also backend, frontend, and integration test commands in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Documentation

- [Development guide](docs/DEVELOPMENT.md)
- [Deployment and operations](docs/DEPLOYMENT.md)
- [Architecture and runtime notes](docs/ARCHITECTURE.md)
- [Admin UI patterns](docs/ADMIN_UI.md)
- [CI workflow](docs/CI.md)
- [Release workflow](docs/RELEASE_WORKFLOW.md)

## License

Registry Control Plane is licensed under the GNU Affero General Public License v3.0 or later. See [LICENSE](LICENSE) for the full license text.

## Status

As of May 16, 2026, the documentation reflects the current Docker Compose runtime, first-boot setup path, admin UI and repository browser, registry notification/state-cache flow, and Docker-backed verification paths.
