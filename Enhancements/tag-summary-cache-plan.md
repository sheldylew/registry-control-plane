# Digest-Keyed Tag Summary Cache Plan

## Summary

Implement a read-through cache for manifest-derived tag summary fields so repeated loads of `GET /api/repos/{repo}/tags` stop recomputing `Size`, `Created`, `Arch`, and `History count` for unchanged manifests. Keep tag enumeration and tag-to-digest resolution live against the registry. Persist cached summaries in SQLite keyed by `(repository_name, manifest_digest)`.

## Phase 0: Baseline and Design

- Document the current cost model:
  - `GET /v2/<repo>/tags/list` returns only tag names
  - each visible tag currently triggers manifest and config/blob fan-out
  - tags are mutable pointers; manifest digests are immutable cache identities
- Keep phase 1 scoped to the tag summary list endpoint only.
- Treat the cache as digest-keyed and read-through first, without event-driven warming.

## Phase 1: Read-Through Digest Cache

### Persistence

- Add `CachedManifestSummary` in `backend/models.py`.
- Add Alembic migration `0006_cached_manifest_summaries.py`.
- Table shape:
  - `id`
  - `repository_name`
  - `manifest_digest`
  - `media_type`
  - `config_digest`
  - `total_size`
  - `created_at`
  - `architectures`
  - `history_count`
  - `children_truncated`
  - `history_truncated`
  - `cached_at`
  - `last_seen_at`
- Constraints and indexes:
  - unique on `(repository_name, manifest_digest)`
  - index on `(repository_name, last_seen_at)`

### Registry Client Refactor

- Add `ResolvedManifestDescriptor` in `backend/registry_client.py`.
- Add `resolve_manifest_descriptor(repository_name, reference)`.
- Use `HEAD /v2/{repo}/manifests/{reference}` with the existing manifest `Accept` set.
- Return:
  - `digest` from `Docker-Content-Digest`
  - `media_type` from `Content-Type`
- Keep `get_manifest_details()` as the cold-path source of truth.
- Refactor `get_manifest_details()` to reuse the `HEAD` resolver instead of duplicating it.

### Route-Level Cache Flow

- Change only `GET /api/repos/{repo}/tags`.
- Preserve current authz, pagination, visibility, truncation, and response shape.
- New request flow:
  1. authorize as today
  2. fetch all tags via `tags/list`
  3. slice the current page
  4. resolve each visible tag to its current digest with `HEAD`
  5. skip tags whose manifest resolution returns `404`
  6. query cached summaries for `(repo_name, digest)` in one DB read
  7. return cache hits immediately
  8. dedupe cache misses by digest
  9. fetch full manifest details only for those misses
  10. persist new cache rows
  11. update `last_seen_at` for cache hits
  12. serialize the same JSON contract as before
- Keep `TagSummary.tag` bound to the live tag name, not any cached source tag.
- Persist digest-derived metadata from `ManifestDetails`.
- Normalize cached `created_at` as timezone-aware UTC.
- Serialize cached `created_at` back to ISO8601 `Z` strings.

### Concurrency

- Use background threads only for cold-path manifest-detail fetches.
- Do not share a SQLAlchemy `Session` across threads.
- Do not share a `RegistryClient` instance across threads.
- Worker design:
  - main thread resolves digests and loads cache rows
  - main thread identifies unique cache misses
  - each worker creates its own registry client from `request.app.state.registry_client_factory()`
  - each worker fetches `get_manifest_details()` for one digest/reference
  - workers return plain data only
  - the main thread performs DB inserts and updates
- Bound worker count to `min(8, len(unique_cache_misses))`.
- If a cold-path fetch returns `RegistryNotFoundError`, skip only that row and keep the page alive.
- Preserve current failure behavior for real non-404 registry errors.

### Helper Functions

- Add helpers for:
  - formatting cached timestamps
  - building `TagSummary` from a cached row plus live tag
  - upserting `CachedManifestSummary` from `ManifestDetails`
  - loading cold-path manifest details through thread-safe client creation
- Do not add public cache-admin endpoints in phase 1.

## Phase 2: Proactive Warming and Invalidation

- Add an optional push/delete notification path from the registry.
- On push:
  - resolve the tag to its digest
  - compute and store the digest summary eagerly
- On delete:
  - remove tag bindings if a tag-mapping layer is later added
  - keep digest summaries eligible for age-based cleanup
- Keep live `HEAD` resolution in the request path even with warming enabled.

## Phase 3: Lifecycle and Observability

- Add age-based pruning for digest summaries no longer seen.
- Run pruning from startup and/or maintenance flows, not every request.
- Add metrics or counters for:
  - cache hits
  - cache misses
  - cache writes
  - stale-tag skips
- Add cache status reporting only if later operational usage justifies it.

## Test Plan

### Backend API Coverage

- Cache miss populates a DB row and returns the expected summary.
- Second request for the same digest uses the cache and avoids full manifest-detail fetch.
- Retagging to a new digest creates a second cache row and updates the live response.
- Multiple tags pointing to the same digest trigger one cold-path fetch.
- Stale tags that resolve to `404` are skipped without failing the whole page.
- Pagination and truncation metadata remain unchanged.
- Authz and visibility behavior remain unchanged for admins and non-admins.

### Fake Registry Harness

- Add support for:
  - digest resolution
  - explicit tag-to-digest mappings
  - mutable retag sequences across requests
  - separate counters for digest-resolution and full-detail fetches

### Broader Verification

- Run targeted tests:
  - `backend/tests/test_api.py`
  - `backend/tests/test_registry_client.py`
  - `backend/tests/test_security_actor_scenarios.py`
- Run the full backend suite:
  - `source .venv/bin/activate && pytest backend/tests`
- Run Docker-backed validation on the local stack:
  - rebuild through the repo’s smoke path
  - seed live actors
  - verify anonymous denial, allowed reader access, denied reader access
  - verify repeated admin tag-page loads
  - retag a live image and confirm the new digest appears while the cache retains both digest rows

## Assumptions

- Phase 1 applies only to the tag summary list endpoint.
- Cache identity is `(repository_name, manifest_digest)`.
- Live `HEAD /manifests/<tag>` remains authoritative for current tag binding.
- Cache rows are not proactively pruned or warmed in phase 1.
- Cache writes happen synchronously in the request after cold fetches complete.
- Cold-path parallelism is limited to registry reads; DB work stays on the main request thread.
