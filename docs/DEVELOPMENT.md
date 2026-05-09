# Development Guide

## Local Docker workflow

The supported packaged workflow is the Docker stack. For local Docker work, use the base compose file plus `docker-compose.local.yml`, which switches the app into development mode and sets:

- `APP_ENV=development`
- `PUBLIC_REGISTRY_ORIGIN=http://localhost:8080`
- `SESSION_COOKIE_SECURE=false`
- `FORWARDED_ALLOW_IPS=*`

Build and start the local Docker stack with explicit local bootstrap values:

```bash
ADMIN_USERNAME=admin \
ADMIN_PASSWORD='set-a-local-password' \
ADMIN_EMAIL=admin@example.com \
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

For local-only convenience, you can opt into the documented bootstrap defaults:

```bash
ALLOW_DEV_DEFAULT_CREDENTIALS=1 \
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

Opt-in defaults:

- username: `admin`
- password: `change-me-now`
- email: `admin@example.com`

If you omit admin bootstrap values, the stack stays in setup mode. Read the `auth-init` container logs, open `http://localhost:8080/setup`, and enter the one-time setup token, first admin account, and local registry origin `http://localhost:8080`.

Rebuild images and replace running containers after code changes:

```bash
./scripts/rebuild-stack.sh
```

That command can start in first-boot setup mode with no credentials. Use `ALLOW_DEV_DEFAULT_CREDENTIALS=1 ./scripts/rebuild-stack.sh` only when you intentionally want the documented local admin defaults.

Open the UI:

```text
http://localhost:8080/
```

Useful endpoints:

- `GET /healthz` through nginx: `http://localhost:8080/healthz`
- `GET /api/healthz` through nginx: `http://localhost:8080/api/healthz`
- `GET /auth/token` through nginx: `http://localhost:8080/auth/token`
- `GET /v2/` through nginx: `http://localhost:8080/v2/`
- `GET /metrics` directly from the API process: `http://127.0.0.1:8000/metrics` in local direct-run mode

## Local Node workflow

Use Node `20.x`. If you use `nvm`:

```bash
source "$HOME/.nvm/nvm.sh"
nvm use 20
npm install
```

Run the full app outside Docker:

```bash
npm run dev
```

This starts both:

- Next.js on `http://localhost:3000`
- FastAPI on `http://127.0.0.1:8000`

The Next.js dev server is configured to talk to the local FastAPI process automatically. `npm run dev` shells out to `./scripts/dev-api.sh` for the backend, so `.venv` must already exist and contain the backend dependencies.

Run frontend smoke tests:

```bash
npm test
```

## Local Python workflow

This repository uses a Python virtual environment at `.venv` for all backend work. The checked-in test toolchain currently expects Python `3.10+`; this checkout is pinned to `3.11.9` via `.python-version`.

Create and activate it if you have not already:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

With `.venv` active, run only the API directly:

```bash
uvicorn backend.main:app --reload
```

Or use the same backend launcher that `npm run dev` uses:

```bash
ALLOW_DEV_DEFAULT_CREDENTIALS=1 ./scripts/dev-api.sh
```

Default local backend data is stored in `.local-data/app.db`. Inside Docker, the API uses `/data/app.db`.

## Test commands

Run backend tests:

```bash
source .venv/bin/activate
pytest backend/tests
```

Run Docker CLI integration tests:

```bash
source .venv/bin/activate
pytest tests/integration/test_docker_cli.py
```

Run the compose/runtime hardening regression checks:

```bash
source .venv/bin/activate
pytest tests/integration/test_container_hardening_files.py
```

Run the end-to-end smoke test:

```bash
ALLOW_DEV_DEFAULT_CREDENTIALS=1 \
./scripts/smoke-test.sh
```

This script rebuilds the local Docker stack, waits for nginx health, verifies browser login and admin UI rendering, checks Docker bearer-token issuance, and then performs a real Docker login, push, and pull through the control plane.

Run the extended Docker-backed end-to-end verification:

```bash
ALLOW_DEV_DEFAULT_CREDENTIALS=1 \
./scripts/e2e-test.sh
```

This script builds on the smoke test. It seeds the Phase 4 permission matrix in the running API container, then exercises real allow and deny cases for admin, reader, developer, and robot paths, plus tag delete, empty-repository delete, and live maintenance-gated garbage collection flows.

Run Alembic migrations manually:

```bash
source .venv/bin/activate
alembic -c backend/alembic.ini upgrade head
```

The API container applies Alembic migrations automatically on startup before serving requests.
