# Architecture and Runtime Notes

## Service boundaries

- FastAPI owns the identity model, personal access tokens, robot tokens, repository permissions, audit schema, and registry bearer-token issuance.
- FastAPI also owns setup state, persisted runtime settings, registry notification processing, database-backed repository/tag state, maintenance jobs, and audit/retention pruning.
- Next.js owns UI rendering, the admin shell, the repository browser, setup/login/logout screens, and dashboard UX.
- `nginx` is the only public entrypoint; the registry is reachable directly only through nginx routing.

## Current application surface

Browser-facing routes are grouped by task:

- `/`, `/login`, `/logout`, and `/setup` handle public entry, session creation, session exit, and first-boot setup.
- `/admin` shows the operator dashboard. Admin-only sections live under `/admin/maintenance`, `/admin/maintenance/inbox`, `/admin/users`, `/admin/users/[userId]`, `/admin/sessions`, `/admin/tokens`, `/admin/robots`, `/admin/robots/[robotId]`, `/admin/audit`, `/admin/permissions`, and `/admin/settings`.
- `/repos`, `/repos/[repo]`, `/repos/[repo]/tags/[tag]`, and `/repos/[repo]/tags/[tag]/history` provide the registry browser for visible repositories.

API routes mirror those surfaces:

- `/api/setup/*`, `/api/session/*`, `/api/admin/*`, `/api/repos/*`, and `/api/ui-settings` serve the UI.
- `/auth/token` is the Docker Registry bearer-token endpoint.
- `/api/internal/registry-maintenance` is the nginx maintenance gate for `/v2/`.
- `/api/internal/registry-events` receives registry push/delete notifications and updates the repository state cache.
- `/healthz`, `/api/healthz`, and `/metrics` expose process health and Prometheus-style counters.

## Runtime behavior

- Browser login is implemented and registry token issuance is backed by signed JWTs.
- On first run, the backend either completes setup from the full `.env` bootstrap values or stays locked behind the one-time setup-token wizard.
- Registry signing material is generated on first install into the Docker volumes `auth-private-data` and `auth-public-data`.
- The rendered registry config includes a signed notification endpoint so push and delete events update the database-backed repository/tag read model.
- Failed registry notifications are retained in an inbox under maintenance and can be retried from the admin UI.
- Operators can manually rebuild the registry state cache from maintenance. A persisted setting controls whether that rebuild also runs on API startup.
- Repository catalog, dashboard fan-out, tag lists, and history responses are capped by environment-configurable limits to keep the control plane responsive on larger registries.
- The default list page size, UI timezone, audit pruning retention, storage usage refresh interval, and public registry origin are runtime settings stored in SQLite.
- Login and registry-token issuance have configurable fixed-window rate limits.
- Registry garbage collection uses a maintenance gate on `/v2/` rather than stopping the registry container.
- The maintenance UI and `/v2/` gate are exercised by `./scripts/e2e-test.sh`, including live delete and garbage-collection flows.
- `docker compose build` alone does not refresh already-running containers; use `./scripts/rebuild-stack.sh` when you need the live stack to pick up new code.

## Admin UI direction

- Admin pages should default to presentation-first views, with create and short edit flows moved into dialogs or explicit edit states.
- Settings, permissions, users, robots, and similar management surfaces should converge on shared admin UI primitives instead of page-specific interaction patterns.
- Profile-style entity pages are preferred over dense form-first layouts when an operator needs to inspect state before editing it.
- The mobile admin navigation is a top-sliding command menu; non-admin users only see the repository browser entry.

## Signing material

To supply your own signing keypair:

- mount the private key to `/run/auth-private/auth-private.pem` in the API container
- mount the public certificate to `/run/auth-public/auth-cert.pem` in the API container
- mount the public certificate to `/certs/auth-cert.pem` in the registry container
