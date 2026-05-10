# Deployment and Operations

## Deployment shape

The Docker stack is the supported package format for this project.

Start by copying the example environment file:

```bash
cp .env.example .env
```

Deployment shape:

- leave `PUBLIC_REGISTRY_ORIGIN`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `ADMIN_EMAIL` blank to use the first-boot wizard
- or set all four values to complete first-boot setup automatically from `.env`
- review `TOKEN_ISSUER`, `TOKEN_SERVICE`, `TOKEN_TTL_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_TRUSTED_ORIGINS`, `WEB_SESSION_RETENTION_DAYS`, `TOKEN_RECORD_RETENTION_DAYS`, `FORWARDED_ALLOW_IPS`, and `RCP_HTTP_BIND`
- start with `docker compose up --build -d`

## Configuration reference

### Required for automated bootstrap

- `PUBLIC_REGISTRY_ORIGIN`: public origin used in registry auth challenges and copied pull commands. In production this must be `https://...`.
- `ADMIN_USERNAME`: first admin username.
- `ADMIN_PASSWORD`: first admin password.
- `ADMIN_EMAIL`: first admin email address.

### Security and request handling

- `SESSION_COOKIE_SECURE`: must stay `true` in production.
- `SESSION_LIFETIME_SECONDS`: browser session lifetime in seconds. Defaults to `28800`.
- `CSRF_TRUSTED_ORIGINS`: comma-separated trusted origins for browser requests when the app sits behind a public origin or proxy.
- `FORWARDED_ALLOW_IPS`: forwarded-header trust setting passed to the API runtime. The built-in nginx overwrites inbound `X-Forwarded-For` with its direct peer address before proxying to the API; keep that behavior unless your outer proxy also strips spoofed forwarding headers before traffic reaches this stack.
- `LOGIN_RATE_LIMIT_ATTEMPTS` and `LOGIN_RATE_LIMIT_WINDOW_SECONDS`: browser login rate-limit settings.
- `AUTH_TOKEN_RATE_LIMIT_ATTEMPTS` and `AUTH_TOKEN_RATE_LIMIT_WINDOW_SECONDS`: registry bearer-token issuance rate-limit settings.
- `SETUP_RATE_LIMIT_ATTEMPTS` and `SETUP_RATE_LIMIT_WINDOW_SECONDS`: first-boot setup token retry limits.

### Registry and response sizing

- `TOKEN_ISSUER`: JWT issuer presented to the Docker registry.
- `TOKEN_SERVICE`: service name used in registry auth challenges.
- `TOKEN_TTL_SECONDS`: lifetime of issued Docker bearer tokens. Defaults to `900`.
- `REGISTRY_CATALOG_MAX_PAGES`: max backend page fetches when walking the catalog.
- `DASHBOARD_MAX_REPOSITORIES`: max repositories returned to the dashboard.
- `REPOSITORY_TAGS_MAX_ITEMS`: max tags returned for a repository view.
- `MANIFEST_CHILDREN_MAX_ITEMS`: max manifest-child entries returned for a manifest detail view.
- `HISTORY_ENTRIES_MAX_ITEMS`: max history entries returned for a repository view.

### Maintenance and retention

- `LOG_RETENTION_DAYS`: retention window for audit events and completed maintenance job logs. Defaults to `30`.
- `WEB_SESSION_RETENTION_DAYS`: retention window for expired or revoked browser session rows. Defaults to `30`.
- `TOKEN_RECORD_RETENTION_DAYS`: retention window for expired or revoked PAT and robot-token rows. Defaults to `90`.
- `MAINTENANCE_MIN_GATE_SECONDS`: minimum time the destructive maintenance gate stays up during a destructive GC run.

### Network and binding

- `RCP_HTTP_BIND`: nginx bind target, defaulting to `127.0.0.1:8080`.

If you are publishing the stack behind another reverse proxy, keep `RCP_HTTP_BIND` localhost-only and terminate public TLS at the outer proxy.

## HTTPS on a LAN with Traefik

Traefik can provide HTTPS for a private LAN deployment even though this project does not terminate TLS itself.

The important boundary is the client-facing hop:

- browsers send login credentials and session cookies to the control plane
- Docker clients send account passwords, PATs, or robot tokens to `/auth/token`
- those secrets are protected in transit only if the client connects over `https://`

Traefik solves that by terminating TLS in front of this stack and forwarding the decrypted request to this project's built-in nginx over local HTTP. That means:

- client to Traefik: encrypted
- Traefik to this project's nginx: typically plain HTTP on the same host or trusted internal network
- built-in nginx to `api`, `web`, and `registry`: plain internal container traffic

This is a good fit for LAN use because it keeps the registry control plane private behind a single HTTPS origin such as `https://registry.lan.example` while preserving the current Compose stack unchanged.

### Why this matters for this project

This repo is already structured for outer-proxy TLS termination:

- `RCP_HTTP_BIND` defaults to `127.0.0.1:8080`, so the built-in nginx can stay host-local
- production requires `PUBLIC_REGISTRY_ORIGIN` to use `https://...`
- production requires `SESSION_COOKIE_SECURE=true`
- the Docker registry auth realm is rendered from `PUBLIC_REGISTRY_ORIGIN`, so Docker clients will be challenged against your HTTPS origin rather than a plain HTTP address

If you expose `http://` directly on the LAN instead, browser logins and Docker credentials can be intercepted by any actor that can observe that network segment. PATs and robot tokens are operationally safer than reusing account passwords, but they are still bearer secrets and should not be sent over LAN HTTP.

### Recommended Traefik shape

Use Traefik as the only LAN-facing listener:

- Traefik listens on `:443`
- Traefik presents a certificate trusted by your LAN clients
- Traefik routes `https://registry.lan.example` to `http://127.0.0.1:8080`
- this project keeps `RCP_HTTP_BIND=127.0.0.1:8080`
- `PUBLIC_REGISTRY_ORIGIN` is set to `https://registry.lan.example`

With that shape:

- browser sessions use secure cookies
- Docker `login`, `pull`, and `push` talk to the HTTPS origin
- `/auth/token` challenges and copied pull commands point at the same HTTPS origin

### Certificate options on a LAN

Traefik does not require a public internet deployment to provide HTTPS. Common LAN options are:

- use an internal CA such as a homelab PKI and trust that CA on client machines
- use publicly trusted certificates if the LAN hostname is publicly resolvable and reachable for ACME validation
- use DNS-based ACME validation if you control the domain and want trusted certs without exposing the service directly

For an internal-only hostname, the usual approach is an internal CA plus distributing that CA certificate to the browsers, Docker hosts, and CI runners that need to trust the registry origin.

### Project settings to align

For a Traefik-backed LAN deployment, keep these values aligned:

```dotenv
APP_ENV=production
RCP_HTTP_BIND=127.0.0.1:8080
PUBLIC_REGISTRY_ORIGIN=https://registry.lan.example
SESSION_COOKIE_SECURE=true
CSRF_TRUSTED_ORIGINS=https://registry.lan.example
```

Notes:

- `PUBLIC_REGISTRY_ORIGIN` is the user-visible and Docker-visible origin
- `CSRF_TRUSTED_ORIGINS` should include the HTTPS origin Traefik serves
- if first-boot setup has already completed, changing `PUBLIC_REGISTRY_ORIGIN` later must be done from `/admin/settings`, then `docker compose restart registry`

### Security model summary

Traefik secures this project on a LAN by encrypting the only hop that carries user and Docker credentials from clients into the stack. The built-in nginx remains an internal HTTP proxy, which is acceptable when it is bound to localhost or another non-public interface. In other words, Traefik does not change this project's authentication model; it makes that model safe to expose to LAN clients by putting TLS on the outside.

## Packaging notes

- `docker compose` automatically reads `.env`
- the base compose file defaults to `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, and a localhost-only nginx bind
- production starts in locked setup mode when no admin or saved registry origin exists
- while setup is incomplete, login, admin APIs, repository APIs, and registry-token issuance return controlled setup-required errors
- the first-boot setup token is generated by `auth-init`, stored only as a SHA-256 hash in the private app-data volume, and printed once in `auth-init` logs
- production registry origins must use `https://`; only local development allows `http://localhost:8080`
- full `.env` bootstrap requires all four values: `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_EMAIL`, and `PUBLIC_REGISTRY_ORIGIN`
- local Docker runs should include `docker-compose.local.yml`, which switches cookies and app mode back to development
- `auth-init` renders the initial registry config, prepares ownership, generates signing material on first install, and generates the one-time setup token when needed
- the API container runs `alembic upgrade head` on boot
- services use `restart: unless-stopped`
- external container images are pinned to fixed tags instead of floating tags
- persistent state lives in the named Docker volumes `app-data`, `registry-data`, `auth-private-data`, `auth-public-data`, and `registry-config-data`
- nginx publishes the host bind to container port `8080`, not port `80`, because the runtime stays non-root end-to-end

## First-boot wizard

Bring the stack up and inspect the setup token:

```bash
docker compose up --build -d
docker compose logs auth-init
```

Open `/setup` at the public origin, enter the one-time setup token from the logs, create the first admin, and save the public registry origin.

After setup completes, restart only the registry so it reloads the rendered auth realm:

```bash
docker compose restart registry
```

## Automated bootstrap

For automated production bootstrap, set all four setup values in `.env` before first start:

```dotenv
PUBLIC_REGISTRY_ORIGIN=https://registry.example.com
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace-with-a-long-random-password
ADMIN_EMAIL=admin@example.com
```

After setup, the saved registry origin in SQLite is the source of truth. Changing `PUBLIC_REGISTRY_ORIGIN` in `.env` later does not override the saved value; update it from `/admin/settings`, then run `docker compose restart registry`.

## Data and backups

Persistent state lives in named Docker volumes:

- `app-data`: SQLite application state, setup markers, and hashed setup token state
- `registry-data`: registry blobs and metadata
- `auth-private-data`: generated signing private key
- `auth-public-data`: generated signing certificate
- `registry-config-data`: rendered registry auth configuration

`./scripts/backup-db.sh` backs up only the API database from `app-data`. It does not back up registry blobs or the signing/config volumes.

## Upgrades

Before an upgrade:

```bash
./scripts/backup-db.sh
```

To rebuild and apply an upgrade:

```bash
./scripts/upgrade-stack.sh
```

That workflow:

- copies `/data/app.db` out of the running API container
- rebuilds the images
- recreates the stack
- lets the API apply migrations on startup

If you only need to refresh containers after source changes without treating it as an upgrade step, `./scripts/rebuild-stack.sh` is still fine.

## Restore notes

If you need to restore from a database backup, stop the stack, replace the live `app.db` inside the `app-data` volume with the saved copy, then start the stack again so the API can run migrations if needed.

Restoring only `app.db` does not restore:

- pushed registry content in `registry-data`
- generated signing material
- rendered registry config state outside the database

Treat database backups as application-state backups, not full registry disaster-recovery snapshots.
