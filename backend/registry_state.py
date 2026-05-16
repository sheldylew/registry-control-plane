from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.audit import record_audit_event
from backend.models import (
    CachedManifestSummary,
    GcJob,
    RegistryEventInbox,
    RegistryStateRebuildJob,
    Repository,
    RepositoryTag,
    User,
)
from backend.registry_client import ManifestDetails, RegistryNotFoundError, ResolvedManifestDescriptor


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_cached_created_at(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def registry_event_dedupe_key(event: dict) -> str:
    return "|".join(
        [
            str(event.get("action") or ""),
            str(event.get("repository_name") or ""),
            str(event.get("tag") or ""),
            str(event.get("digest") or ""),
        ]
    )


def create_registry_event_rows(db: Session, events: list[dict]) -> list[RegistryEventInbox]:
    rows: list[RegistryEventInbox] = []
    now = utcnow()
    for event in events:
        row = RegistryEventInbox(
            action=event["action"],
            repository_name=event["repository_name"],
            tag=event.get("tag"),
            digest=event.get("digest"),
            media_type=event.get("media_type"),
            raw_payload=event.get("raw_payload") or event,
            dedupe_key=registry_event_dedupe_key(event),
            status="pending",
            attempts=0,
            received_at=now,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def upsert_repository(db: Session, *, repository_name: str, seen_at: Optional[datetime] = None) -> tuple[Repository, bool]:
    now = seen_at or utcnow()
    repository = db.scalar(select(Repository).where(Repository.name == repository_name))
    if repository is None:
        repository = Repository(
            name=repository_name,
            visibility="private",
            created_at=now,
            updated_at=now,
            last_seen_at=now,
            deleted_at=None,
        )
        try:
            with db.begin_nested():
                db.add(repository)
                db.flush()
            return repository, True
        except IntegrityError:
            repository = db.scalar(select(Repository).where(Repository.name == repository_name))
            if repository is None:
                raise

    changed = repository.deleted_at is not None
    repository.deleted_at = None
    repository.last_seen_at = now
    repository.updated_at = now
    return repository, changed


def upsert_repository_tag(
    db: Session,
    *,
    repository: Repository,
    tag_name: str,
    manifest_digest: str,
    media_type: Optional[str],
    seen_at: Optional[datetime] = None,
) -> tuple[RepositoryTag, bool]:
    now = seen_at or utcnow()
    row = db.scalar(
        select(RepositoryTag).where(
            RepositoryTag.repository_id == repository.id,
            RepositoryTag.name == tag_name,
        )
    )
    if row is None:
        row = RepositoryTag(
            repository_id=repository.id,
            name=tag_name,
            manifest_digest=manifest_digest,
            media_type=media_type,
            pushed_at=now,
            last_seen_at=now,
            deleted_at=None,
            created_at=now,
            updated_at=now,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            return row, True
        except IntegrityError:
            row = db.scalar(
                select(RepositoryTag).where(
                    RepositoryTag.repository_id == repository.id,
                    RepositoryTag.name == tag_name,
                )
            )
            if row is None:
                raise

    changed = (
        row.manifest_digest != manifest_digest
        or row.media_type != media_type
        or row.deleted_at is not None
    )
    if row.manifest_digest != manifest_digest:
        row.pushed_at = now
    row.manifest_digest = manifest_digest
    row.media_type = media_type
    row.last_seen_at = now
    row.deleted_at = None
    row.updated_at = now
    return row, changed


def upsert_cached_manifest_summary(
    db: Session,
    *,
    repository_name: str,
    manifest_digest: str,
    details: ManifestDetails,
    seen_at: Optional[datetime] = None,
) -> tuple[CachedManifestSummary, bool]:
    now = seen_at or utcnow()
    row = db.scalar(
        select(CachedManifestSummary).where(
            CachedManifestSummary.repository_name == repository_name,
            CachedManifestSummary.manifest_digest == manifest_digest,
        )
    )
    if row is None:
        row = CachedManifestSummary(
            repository_name=repository_name,
            manifest_digest=manifest_digest,
            media_type=details.media_type,
            config_digest=details.config_digest,
            total_size=details.total_size,
            created_at=parse_cached_created_at(details.created_at),
            architectures=list(details.architectures),
            history_count=details.history_count,
            children_truncated=details.children_truncated,
            history_truncated=details.history_truncated,
            cached_at=now,
            last_seen_at=now,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            return row, True
        except IntegrityError:
            row = db.scalar(
                select(CachedManifestSummary).where(
                    CachedManifestSummary.repository_name == repository_name,
                    CachedManifestSummary.manifest_digest == manifest_digest,
                )
            )
            if row is None:
                raise

    changed = (
        row.media_type != details.media_type
        or row.config_digest != details.config_digest
        or row.total_size != details.total_size
        or list(row.architectures or []) != list(details.architectures)
        or row.history_count != details.history_count
        or row.children_truncated != details.children_truncated
        or row.history_truncated != details.history_truncated
    )
    row.media_type = details.media_type
    row.config_digest = details.config_digest
    row.total_size = details.total_size
    row.created_at = parse_cached_created_at(details.created_at)
    row.architectures = list(details.architectures)
    row.history_count = details.history_count
    row.children_truncated = details.children_truncated
    row.history_truncated = details.history_truncated
    row.cached_at = now
    row.last_seen_at = now
    return row, changed


def mark_cached_manifest_summary_seen(
    db: Session,
    *,
    repository_name: str,
    manifest_digest: str,
    seen_at: Optional[datetime] = None,
) -> bool:
    row = db.scalar(
        select(CachedManifestSummary).where(
            CachedManifestSummary.repository_name == repository_name,
            CachedManifestSummary.manifest_digest == manifest_digest,
        )
    )
    if row is None:
        return False
    row.last_seen_at = seen_at or utcnow()
    return True


def remove_manifest_summary_if_unreferenced(db: Session, *, repository_name: str, manifest_digest: str) -> bool:
    active_refs = db.scalar(
        select(func.count(RepositoryTag.id))
        .join(Repository)
        .where(
            Repository.name == repository_name,
            RepositoryTag.manifest_digest == manifest_digest,
            RepositoryTag.deleted_at.is_(None),
        )
    ) or 0
    if active_refs:
        return False

    rows = db.scalars(
        select(CachedManifestSummary).where(
            CachedManifestSummary.repository_name == repository_name,
            CachedManifestSummary.manifest_digest == manifest_digest,
        )
    ).all()
    for row in rows:
        db.delete(row)
    return bool(rows)


def mark_repository_tag_deleted(
    db: Session,
    *,
    repository_name: str,
    tag_name: Optional[str] = None,
    manifest_digest: Optional[str] = None,
    deleted_at: Optional[datetime] = None,
) -> int:
    now = deleted_at or utcnow()
    query = (
        select(RepositoryTag)
        .join(Repository)
        .where(
            Repository.name == repository_name,
            RepositoryTag.deleted_at.is_(None),
        )
    )
    if tag_name:
        query = query.where(RepositoryTag.name == tag_name)
    elif manifest_digest:
        query = query.where(RepositoryTag.manifest_digest == manifest_digest)
    else:
        return 0

    rows = db.scalars(query).all()
    affected_digests = {row.manifest_digest for row in rows}
    for row in rows:
        row.deleted_at = now
        row.updated_at = now
    db.flush()
    for digest in affected_digests:
        remove_manifest_summary_if_unreferenced(db, repository_name=repository_name, manifest_digest=digest)
    return len(rows)


def mark_repository_deleted(db: Session, *, repository_name: str, deleted_at: Optional[datetime] = None) -> bool:
    now = deleted_at or utcnow()
    repository = db.scalar(select(Repository).where(Repository.name == repository_name))
    if repository is None:
        return False
    changed = repository.deleted_at is None
    repository.deleted_at = now
    repository.updated_at = now
    tags = db.scalars(
        select(RepositoryTag).where(
            RepositoryTag.repository_id == repository.id,
            RepositoryTag.deleted_at.is_(None),
        )
    ).all()
    for tag in tags:
        tag.deleted_at = now
        tag.updated_at = now
    summaries = db.scalars(
        select(CachedManifestSummary).where(CachedManifestSummary.repository_name == repository_name)
    ).all()
    for summary in summaries:
        db.delete(summary)
    return changed or bool(tags) or bool(summaries)


def warm_manifest_summary(
    db: Session,
    *,
    registry,
    settings,
    repository_name: str,
    tag: Optional[str],
    digest: Optional[str],
) -> tuple[Optional[str], Optional[str], bool]:
    reference = digest
    media_type = None
    resolved_descriptor = None
    if tag:
        descriptor = registry.resolve_manifest_descriptor(repository_name, tag)
        reference = descriptor.digest or tag
        media_type = descriptor.media_type
        if descriptor.digest:
            resolved_descriptor = descriptor
    elif digest:
        resolved_descriptor = ResolvedManifestDescriptor(digest=digest, media_type=None)
    if not reference:
        return digest, media_type, False

    details = registry.get_manifest_details(
        repository_name,
        reference,
        max_manifest_children=settings.manifest_children_max_items,
        max_history_entries=settings.history_entries_max_items,
        resolved_descriptor=resolved_descriptor,
    )
    resolved_digest = details.digest or reference or digest
    if not resolved_digest:
        return digest, media_type or details.media_type, False
    _row, changed = upsert_cached_manifest_summary(
        db,
        repository_name=repository_name,
        manifest_digest=resolved_digest,
        details=details,
    )
    return resolved_digest, media_type or details.media_type, changed


def process_registry_event_inbox_entry(session_factory, registry_factory, settings, event_id: int) -> None:
    with session_factory() as db:
        row = db.get(RegistryEventInbox, event_id)
        if row is None or row.status == "processed":
            return
        row.status = "processing"
        row.attempts += 1
        row.error = None
        db.commit()

        registry = registry_factory()
        try:
            now = utcnow()
            if row.action == "push":
                repository, _repo_changed = upsert_repository(db, repository_name=row.repository_name, seen_at=now)
                digest, media_type, _summary_changed = warm_manifest_summary(
                    db,
                    registry=registry,
                    settings=settings,
                    repository_name=row.repository_name,
                    tag=row.tag,
                    digest=row.digest,
                )
                if row.tag and digest:
                    upsert_repository_tag(
                        db,
                        repository=repository,
                        tag_name=row.tag,
                        manifest_digest=digest,
                        media_type=media_type or row.media_type,
                        seen_at=now,
                    )
            elif row.action == "delete":
                mark_repository_tag_deleted(
                    db,
                    repository_name=row.repository_name,
                    tag_name=row.tag,
                    manifest_digest=row.digest,
                    deleted_at=now,
                )

            row.status = "processed"
            row.processed_at = utcnow()
            db.commit()
        except Exception as exc:
            db.rollback()
            failed = db.get(RegistryEventInbox, event_id)
            if failed is not None:
                failed.status = "failed"
                failed.error = str(exc)
                failed.processed_at = utcnow()
                db.commit()
        finally:
            registry.close()


def registry_state_stats(db: Session) -> dict[str, object]:
    active_repositories = db.scalar(
        select(func.count(func.distinct(Repository.id)))
        .join(RepositoryTag)
        .where(
            Repository.deleted_at.is_(None),
            RepositoryTag.deleted_at.is_(None),
        )
    ) or 0
    active_tags = db.scalar(
        select(func.count(RepositoryTag.id))
        .join(Repository)
        .where(
            Repository.deleted_at.is_(None),
            RepositoryTag.deleted_at.is_(None),
        )
    ) or 0
    inbox_queued = db.scalar(
        select(func.count(RegistryEventInbox.id)).where(RegistryEventInbox.status.in_(("pending", "processing")))
    ) or 0
    inbox_failed = db.scalar(
        select(func.count(RegistryEventInbox.id)).where(RegistryEventInbox.status == "failed")
    ) or 0
    last_rebuild = db.scalar(select(RegistryStateRebuildJob).order_by(RegistryStateRebuildJob.created_at.desc()).limit(1))
    return {
        "active_repositories": int(active_repositories),
        "active_tags": int(active_tags),
        "inbox_queued": int(inbox_queued),
        "inbox_failed": int(inbox_failed),
        "last_rebuild": last_rebuild,
    }


def reconcile_registry_event_inbox_after_rebuild(
    db: Session,
    *,
    received_before: datetime,
) -> int:
    rows = db.scalars(
        select(RegistryEventInbox)
        .where(
            RegistryEventInbox.status.in_(("pending", "processing", "failed")),
            RegistryEventInbox.received_at <= received_before,
        )
        .order_by(RegistryEventInbox.received_at.asc())
    ).all()
    processed_at = utcnow()
    for row in rows:
        original_status = row.status
        row.status = "reconciled"
        if row.processed_at is None:
            row.processed_at = processed_at
        if original_status != "failed":
            row.error = None
    return len(rows)


def has_active_rebuild_job(db: Session) -> bool:
    active = db.scalar(
        select(RegistryStateRebuildJob).where(
            RegistryStateRebuildJob.status.in_(("queued", "running"))
        ).order_by(RegistryStateRebuildJob.created_at.desc())
    )
    return active is not None


def create_rebuild_job(
    db: Session,
    *,
    actor: User,
    retention_days: int = 30,
    reason: str = "manual",
) -> RegistryStateRebuildJob:
    if has_active_rebuild_job(db):
        raise ValueError("A registry state rebuild is already queued or running.")
    active_gc = db.scalar(
        select(GcJob).where(GcJob.status.in_(("queued", "running"))).order_by(GcJob.created_at.desc())
    )
    if active_gc is not None:
        raise ValueError("A maintenance job is already queued or running.")

    now = utcnow()
    job = RegistryStateRebuildJob(
        status="queued",
        requested_by=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    record_audit_event(
        db,
        actor=actor,
        action="registry_state_rebuild_requested",
        target_type="registry_state_rebuild_job",
        target_id=job.id,
        metadata_json={"requested_by": actor.username, "reason": reason},
        retention_days=retention_days,
    )
    return job


def queue_automatic_rebuild_job(db: Session, *, retention_days: int = 30) -> Optional[RegistryStateRebuildJob]:
    actor = db.scalar(
        select(User)
        .where(
            User.is_admin.is_(True),
            User.is_active.is_(True),
        )
        .order_by(User.id.asc())
        .limit(1)
    )
    if actor is None:
        return None
    try:
        return create_rebuild_job(
            db,
            actor=actor,
            retention_days=retention_days,
            reason="automatic_startup",
        )
    except ValueError:
        return None


def run_registry_state_rebuild_job(session_factory, registry_factory, settings, job_id: int) -> None:
    with session_factory() as db:
        job = db.get(RegistryStateRebuildJob, job_id)
        if job is None or job.status != "queued":
            return
        actor = db.get(User, job.requested_by)
        rebuild_started_at = utcnow()
        job.status = "running"
        job.started_at = rebuild_started_at
        job.updated_at = job.started_at
        db.commit()
        record_audit_event(
            db,
            actor=actor,
            action="registry_state_rebuild_started",
            target_type="registry_state_rebuild_job",
            target_id=job.id,
            retention_days=settings.log_retention_days,
        )

        registry = registry_factory()
        logs: list[str] = []
        seen_repositories: set[str] = set()
        seen_tags: set[tuple[str, str]] = set()
        counters = {
            "repositories_scanned": 0,
            "repositories_updated": 0,
            "repositories_deleted": 0,
            "tags_scanned": 0,
            "tags_updated": 0,
            "tags_deleted": 0,
            "manifest_summaries_updated": 0,
            "inbox_reconciled": 0,
        }
        try:
            repositories, catalog_meta = registry.list_repositories_bounded(max_pages=None)
            logs.append(
                f"catalog scan: {len(repositories)} repositories, pages_fetched={catalog_meta.get('pages_fetched', 0)}"
            )
            for repository_name in repositories:
                try:
                    tags = registry.list_tags(repository_name)
                except RegistryNotFoundError:
                    logs.append(f"skip stale catalog repository: {repository_name}")
                    continue

                now = utcnow()
                seen_repositories.add(repository_name)
                counters["repositories_scanned"] += 1
                repository, repo_changed = upsert_repository(db, repository_name=repository_name, seen_at=now)
                if repo_changed:
                    counters["repositories_updated"] += 1

                for tag_name in tags:
                    counters["tags_scanned"] += 1
                    try:
                        descriptor = registry.resolve_manifest_descriptor(repository_name, tag_name)
                    except RegistryNotFoundError:
                        logs.append(f"skip stale tag: {repository_name}:{tag_name}")
                        continue
                    if not descriptor.digest:
                        logs.append(f"skip tag without digest: {repository_name}:{tag_name}")
                        continue
                    seen_tags.add((repository_name, tag_name))

                    summary_changed = False
                    summary_cached = mark_cached_manifest_summary_seen(
                        db,
                        repository_name=repository_name,
                        manifest_digest=descriptor.digest,
                        seen_at=now,
                    )
                    if not summary_cached:
                        try:
                            details = registry.get_manifest_details(
                                repository_name,
                                descriptor.digest,
                                max_manifest_children=settings.manifest_children_max_items,
                                max_history_entries=settings.history_entries_max_items,
                                resolved_descriptor=descriptor,
                            )
                        except RegistryNotFoundError:
                            details = None
                        if details is not None:
                            _summary, summary_changed = upsert_cached_manifest_summary(
                                db,
                                repository_name=repository_name,
                                manifest_digest=descriptor.digest,
                                details=details,
                                seen_at=now,
                            )
                    _tag, tag_changed = upsert_repository_tag(
                        db,
                        repository=repository,
                        tag_name=tag_name,
                        manifest_digest=descriptor.digest,
                        media_type=descriptor.media_type,
                        seen_at=now,
                    )
                    if tag_changed:
                        counters["tags_updated"] += 1
                    if summary_changed:
                        counters["manifest_summaries_updated"] += 1

                db.commit()

            now = utcnow()
            active_tags = db.scalars(
                select(RepositoryTag)
                .join(Repository)
                .where(RepositoryTag.deleted_at.is_(None))
            ).all()
            for tag in active_tags:
                repository_name = tag.repository.name
                if repository_name not in seen_repositories or (repository_name, tag.name) not in seen_tags:
                    tag.deleted_at = now
                    tag.updated_at = now
                    counters["tags_deleted"] += 1

            active_repositories = db.scalars(select(Repository).where(Repository.deleted_at.is_(None))).all()
            for repository in active_repositories:
                if repository.name not in seen_repositories:
                    repository.deleted_at = now
                    repository.updated_at = now
                    counters["repositories_deleted"] += 1

            job = db.get(RegistryStateRebuildJob, job_id)
            if job is not None:
                counters["inbox_reconciled"] = reconcile_registry_event_inbox_after_rebuild(
                    db,
                    received_before=rebuild_started_at,
                )
                logs.append(f"inbox reconciliation: {counters['inbox_reconciled']} stale events reconciled")
                for key, value in counters.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                job.status = "succeeded"
                job.finished_at = utcnow()
                job.updated_at = job.finished_at
                job.log_output = "\n".join(logs)
            db.commit()
            record_audit_event(
                db,
                actor=actor,
                action="registry_state_rebuild_succeeded",
                target_type="registry_state_rebuild_job",
                target_id=job_id,
                metadata_json=counters,
                retention_days=settings.log_retention_days,
            )
        except Exception as exc:
            db.rollback()
            failed = db.get(RegistryStateRebuildJob, job_id)
            if failed is not None:
                failed.status = "failed"
                failed.error = str(exc)
                failed.finished_at = utcnow()
                failed.updated_at = failed.finished_at
                failed.log_output = "\n".join(logs)
                db.commit()
            record_audit_event(
                db,
                actor=actor,
                action="registry_state_rebuild_failed",
                target_type="registry_state_rebuild_job",
                target_id=job_id,
                metadata_json={"error": str(exc)},
                retention_days=settings.log_retention_days,
            )
        finally:
            registry.close()
