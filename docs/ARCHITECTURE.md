# Architecture and Runtime Notes

## Service boundaries

- FastAPI owns the identity model, personal access tokens, robot tokens, repository permissions, audit schema, and registry bearer-token issuance.
- Next.js owns UI rendering and dashboard UX.
- `nginx` is the only public entrypoint; the registry is reachable directly only through nginx routing.

## Runtime behavior

- Browser login is implemented and registry token issuance is backed by signed JWTs.
- On first run, the backend either completes setup from the full `.env` bootstrap values or stays locked behind the one-time setup-token wizard.
- Registry signing material is generated on first install into the Docker volumes `auth-private-data` and `auth-public-data`.
- Repository catalog, dashboard fan-out, tag lists, and history responses are capped by environment-configurable limits to keep the control plane responsive on larger registries.
- Login and registry-token issuance have configurable fixed-window rate limits.
- Registry garbage collection uses a maintenance gate on `/v2/` rather than stopping the registry container.
- The maintenance UI and `/v2/` gate are exercised by `./scripts/e2e-test.sh`, including live delete and garbage-collection flows.
- `docker compose build` alone does not refresh already-running containers; use `./scripts/rebuild-stack.sh` when you need the live stack to pick up new code.

## Admin UI direction

- Admin pages should default to presentation-first views, with create and short edit flows moved into dialogs or explicit edit states.
- Settings, permissions, users, robots, and similar management surfaces should converge on shared admin UI primitives instead of page-specific interaction patterns.
- Profile-style entity pages are preferred over dense form-first layouts when an operator needs to inspect state before editing it.

## Signing material

To supply your own signing keypair:

- mount the private key to `/run/auth-private/auth-private.pem` in the API container
- mount the public certificate to `/run/auth-public/auth-cert.pem` in the API container
- mount the public certificate to `/certs/auth-cert.pem` in the registry container
