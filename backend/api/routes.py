import hmac
from pathlib import Path
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import String, and_, func, literal, not_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.audit import record_audit_event
from backend.auth.passwords import hash_password, verify_password
from backend.auth.pats import authenticate_personal_access_token, issue_personal_access_token, issue_robot_token
from backend.auth.permissions import (
    can_access_repository,
    validate_repository_name,
    validate_repository_pattern,
)
from backend.auth.sessions import create_session, revoke_session, revoke_user_sessions
from backend.config import Settings
from backend.maintenance import MaintenanceService, mark_storage_usage_snapshot_stale
from backend.metrics import increment as increment_metric
from backend.models import (
    AuditEvent,
    CachedManifestSummary,
    GcJob,
    PersonalAccessToken,
    RegistryEventInbox,
    RegistryStateRebuildJob,
    Repository,
    RepositoryPermission,
    RepositoryTag,
    RobotAccount,
    RobotToken,
    User,
    WebSession,
)
from backend.registry_client import HistoryVariant, ManifestDetails, RegistryClient, RegistryNotFoundError, TagSummary
from backend.registry_state import (
    create_rebuild_job,
    create_registry_event_rows,
    mark_repository_deleted,
    mark_repository_tag_deleted,
    process_registry_event_inbox_entry,
    registry_state_stats,
    run_registry_state_rebuild_job,
)
from backend.setup import (
    AUDIT_LOG_RETENTION_DAYS_KEY,
    AUTOMATIC_REGISTRY_STATE_REBUILD_KEY,
    DEFAULT_AUDIT_LOG_RETENTION_DAYS,
    DEFAULT_REPOSITORY_TAGS_PAGE_SIZE,
    DEFAULT_STORAGE_USAGE_REFRESH_INTERVAL_SECONDS,
    DEFAULT_UI_TIMEZONE,
    PUBLIC_REGISTRY_ORIGIN_KEY,
    REPOSITORY_TAGS_PAGE_SIZE_KEY,
    RESTART_COMMAND,
    SetupError,
    STORAGE_USAGE_REFRESH_INTERVAL_SECONDS_KEY,
    UI_TIMEZONE_KEY,
    automatic_registry_state_rebuild_enabled,
    complete_setup,
    effective_audit_log_retention_days,
    effective_default_page_size,
    effective_public_registry_origin,
    effective_storage_usage_refresh_interval_seconds,
    effective_ui_timezone,
    render_registry_config_to_path,
    saved_public_registry_origin,
    set_app_setting,
    setup_required,
    setup_status,
    validate_audit_log_retention_days,
    validate_default_page_size,
    validate_public_registry_origin,
    validate_storage_usage_refresh_interval_seconds,
    validate_ui_timezone,
    verify_setup_token,
)


router = APIRouter(prefix="/api")

MAX_SHORT_TEXT_LENGTH = 255
MAX_EMAIL_LENGTH = 320
MAX_PASSWORD_LENGTH = 512
MAX_DESCRIPTION_LENGTH = 2000
REGISTRY_NOTIFICATION_HEADER = "Authorization"
REGISTRY_NOTIFICATION_MANIFEST_MEDIA_TYPES = {
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}
SHARED_MANIFEST_TAG_SAMPLE_SIZE = 5


def _normalize_required_text(value: str, *, field_name: str, max_length: int = MAX_SHORT_TEXT_LENGTH) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer.")
    return normalized


def _normalize_optional_text(value: Optional[str], *, field_name: str, max_length: int = MAX_DESCRIPTION_LENGTH) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer.")
    return normalized


def _validate_password(value: str) -> str:
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer.")
    if not value.strip():
        raise ValueError("Password is required.")
    return value


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
    }


def _user_audit_label(user: User) -> str:
    return user.deleted_username or user.username


def _deleted_user_identity(db: Session, user: User) -> tuple[str, str]:
    base = f"deleted-user-{user.id}"
    for attempt in range(8):
        suffix = "" if attempt == 0 else f"-{secrets.token_hex(4)}"
        username = f"{base}{suffix}"
        email = f"{base}{suffix}@deleted.invalid"
        conflict = db.scalar(
            select(User.id)
            .where(
                User.id != user.id,
                or_(User.username == username, User.email == email),
            )
            .limit(1)
        )
        if conflict is None:
            return username, email
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not prepare deleted user identity.")


def _serialize_web_session(web_session: WebSession, *, user: User, current_session_id: Optional[int]) -> dict:
    return {
        "id": web_session.id,
        "user": _serialize_user(user),
        "is_current": web_session.id == current_session_id,
        "created_at": web_session.created_at.isoformat(),
        "last_seen_at": web_session.last_seen_at.isoformat(),
        "expires_at": web_session.expires_at.isoformat(),
        "revoked_at": web_session.revoked_at.isoformat() if web_session.revoked_at else None,
    }


def _serialize_token(token: PersonalAccessToken) -> dict:
    return {
        "id": token.id,
        "name": token.name,
        "token_prefix": token.token_prefix,
        "created_at": token.created_at.isoformat(),
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "revoked_at": token.revoked_at.isoformat() if token.revoked_at else None,
    }


def _serialize_robot(robot: RobotAccount) -> dict:
    return {
        "id": robot.id,
        "name": robot.name,
        "description": robot.description,
        "is_active": robot.is_active,
        "created_at": robot.created_at.isoformat(),
        "tokens": [
            {
                "id": token.id,
                "name": token.name,
                "token_prefix": token.token_prefix,
                "created_at": token.created_at.isoformat(),
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
                "revoked_at": token.revoked_at.isoformat() if token.revoked_at else None,
            }
            for token in robot.robot_tokens
        ],
    }


def _serialize_permission(permission: RepositoryPermission, subject_name: Optional[str] = None) -> dict:
    return {
        "id": permission.id,
        "subject_type": permission.subject_type,
        "subject_id": permission.subject_id,
        "subject_name": subject_name,
        "repository_pattern": permission.repository_pattern,
        "can_pull": permission.can_pull,
        "can_push": permission.can_push,
        "can_delete": permission.can_delete,
        "created_at": permission.created_at.isoformat(),
    }


def _serialize_repository(repository: Repository) -> dict:
    return {
        "id": repository.id,
        "name": repository.name,
        "visibility": repository.visibility,
        "created_at": repository.created_at.isoformat(),
    }


def _visible_repository_condition(user: User):
    if user.is_admin:
        return None

    subject_type = "user"
    subject_id = user.id
    public_repository = Repository.visibility == "public"
    exact_permission_exists = (
        select(RepositoryPermission.id)
        .where(
            RepositoryPermission.subject_type == subject_type,
            RepositoryPermission.subject_id == subject_id,
            RepositoryPermission.repository_pattern == Repository.name,
        )
        .exists()
    )
    exact_pull_exists = (
        select(RepositoryPermission.id)
        .where(
            RepositoryPermission.subject_type == subject_type,
            RepositoryPermission.subject_id == subject_id,
            RepositoryPermission.repository_pattern == Repository.name,
            RepositoryPermission.can_pull.is_(True),
        )
        .exists()
    )
    wildcard_prefix = func.substr(
        RepositoryPermission.repository_pattern,
        1,
        func.length(RepositoryPermission.repository_pattern) - 2,
    )
    wildcard_pull_exists = (
        select(RepositoryPermission.id)
        .where(
            RepositoryPermission.subject_type == subject_type,
            RepositoryPermission.subject_id == subject_id,
            RepositoryPermission.repository_pattern.like("%/*"),
            RepositoryPermission.can_pull.is_(True),
            Repository.name.like(wildcard_prefix + literal("/%")),
        )
        .exists()
    )
    return or_(
        public_repository,
        exact_pull_exists,
        and_(not_(exact_permission_exists), wildcard_pull_exists),
    )


def _serialize_entity_activity(events: list[AuditEvent], actor_names: dict[int, str]) -> list[dict]:
    return [
        _serialize_audit_event(
            event,
            actor_names.get(event.actor_id) if event.actor_type == "user" and event.actor_id is not None else event.actor_type,
        )
        for event in events
    ]


def get_db(request: Request) -> Session:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_registry_client(request: Request) -> RegistryClient:
    return request.app.state.registry_client_factory()


def get_maintenance_service(request: Request) -> MaintenanceService:
    return request.app.state.maintenance_service_factory()


def require_setup_complete(db: Session, settings: Settings) -> None:
    if setup_required(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Setup must be completed before this endpoint is available.",
        )


def _get_authenticated_user(request: Request, db: Session) -> tuple[Optional[object], Optional[User]]:
    cookie_name = request.app.state.settings.session_cookie_name
    raw_session = request.cookies.get(cookie_name)
    if not raw_session:
        return None, None

    from backend.auth.sessions import authenticate_session

    return authenticate_session(db, raw_session) or (None, None)


def _subject_for_user(user: User) -> dict[str, object]:
    return {
        "subject_type": "user",
        "subject_id": user.id,
        "is_admin": user.is_admin,
    }


def _shared_manifest_tag_metadata_by_digest(
    db: Session,
    *,
    repository_id: int,
    manifest_digests: list[str],
) -> dict[str, dict[str, object]]:
    if not manifest_digests:
        return {}

    counts = {
        digest: int(count or 0)
        for digest, count in db.execute(
            select(RepositoryTag.manifest_digest, func.count(RepositoryTag.id))
            .where(
                RepositoryTag.repository_id == repository_id,
                RepositoryTag.deleted_at.is_(None),
                RepositoryTag.manifest_digest.in_(manifest_digests),
            )
            .group_by(RepositoryTag.manifest_digest)
        ).all()
    }

    metadata: dict[str, dict[str, object]] = {}
    for digest, count in counts.items():
        tag_names = db.scalars(
            select(RepositoryTag.name)
            .where(
                RepositoryTag.repository_id == repository_id,
                RepositoryTag.deleted_at.is_(None),
                RepositoryTag.manifest_digest == digest,
            )
            .order_by(RepositoryTag.name.asc())
            .limit(SHARED_MANIFEST_TAG_SAMPLE_SIZE)
        ).all()
        metadata[digest] = {
            "shared_manifest_tag_count": count,
            "shared_manifest_tags": list(tag_names),
        }
    return metadata


def _shared_manifest_tag_metadata(
    db: Session,
    *,
    repository_id: int,
    manifest_digest: Optional[str],
) -> dict[str, object]:
    if not manifest_digest:
        return {"shared_manifest_tag_count": 0, "shared_manifest_tags": []}
    return _shared_manifest_tag_metadata_by_digest(
        db,
        repository_id=repository_id,
        manifest_digests=[manifest_digest],
    ).get(manifest_digest, {"shared_manifest_tag_count": 0, "shared_manifest_tags": []})


def _serialize_manifest(details: ManifestDetails, *, shared_manifest_metadata: Optional[dict[str, object]] = None) -> dict:
    payload = {
        "name": details.name,
        "tag": details.tag,
        "digest": details.digest,
        "media_type": details.media_type,
        "config_digest": details.config_digest,
        "config_media_type": details.config_media_type,
        "layers": details.layers,
        "total_size": details.total_size,
        "architectures": details.architectures,
        "created_at": details.created_at,
        "history_count": details.history_count,
        "children_truncated": details.children_truncated,
        "history_truncated": details.history_truncated,
    }
    payload.update(shared_manifest_metadata or {"shared_manifest_tag_count": 0, "shared_manifest_tags": []})
    return payload


def _serialize_tag_summary(summary: TagSummary, *, shared_manifest_metadata: Optional[dict[str, object]] = None) -> dict:
    payload = {
        "tag": summary.tag,
        "digest": summary.digest,
        "media_type": summary.media_type,
        "total_size": summary.total_size,
        "architectures": summary.architectures,
        "created_at": summary.created_at,
        "history_count": summary.history_count,
        "children_truncated": summary.children_truncated,
        "history_truncated": summary.history_truncated,
    }
    payload.update(shared_manifest_metadata or {"shared_manifest_tag_count": 0, "shared_manifest_tags": []})
    return payload


def _format_cached_created_at(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_optional_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat()


def _cached_manifest_summary_stats(db: Session) -> dict[str, Optional[object]]:
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    totals = db.execute(
        select(
            func.count(CachedManifestSummary.id),
            func.count(func.distinct(CachedManifestSummary.repository_name)),
            func.min(CachedManifestSummary.cached_at),
            func.max(CachedManifestSummary.cached_at),
            func.max(CachedManifestSummary.last_seen_at),
        )
    ).one()
    seen_last_24h = db.scalar(
        select(func.count(CachedManifestSummary.id)).where(CachedManifestSummary.last_seen_at >= recent_cutoff)
    )
    return {
        "summaries_total": int(totals[0] or 0),
        "repositories_total": int(totals[1] or 0),
        "seen_last_24h": int(seen_last_24h or 0),
        "oldest_cached_at": _serialize_optional_datetime(totals[2]),
        "newest_cached_at": _serialize_optional_datetime(totals[3]),
        "newest_last_seen_at": _serialize_optional_datetime(totals[4]),
    }


def _build_tag_summary_from_cache(row: CachedManifestSummary, *, tag: str) -> TagSummary:
    return TagSummary(
        tag=tag,
        digest=row.manifest_digest,
        media_type=row.media_type,
        total_size=row.total_size,
        architectures=list(row.architectures or []),
        created_at=_format_cached_created_at(row.created_at),
        history_count=row.history_count,
        children_truncated=row.children_truncated,
        history_truncated=row.history_truncated,
    )


def _get_active_repository(db: Session, *, repository_name: str) -> Repository:
    repository = db.scalar(
        select(Repository).where(
            Repository.name == repository_name,
            Repository.deleted_at.is_(None),
        )
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")
    return repository


def _get_active_repository_tag(
    db: Session,
    *,
    repository: Repository,
    tag_name: str,
) -> RepositoryTag:
    tag = db.scalar(
        select(RepositoryTag).where(
            RepositoryTag.repository_id == repository.id,
            RepositoryTag.name == tag_name,
            RepositoryTag.deleted_at.is_(None),
        )
    )
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository tag not found.")
    return tag


def _require_registry_notification_auth(request: Request) -> None:
    expected_token = getattr(request.app.state, "registry_notifications_token", None)
    received_header = request.headers.get(REGISTRY_NOTIFICATION_HEADER, "")
    expected_header = f"Bearer {expected_token}" if expected_token else ""
    if not expected_header or not hmac.compare_digest(received_header, expected_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registry event authentication failed.")


def _is_manifest_notification_media_type(media_type: Optional[str]) -> bool:
    return media_type in REGISTRY_NOTIFICATION_MANIFEST_MEDIA_TYPES


def _normalize_registry_notification_events(payload: dict) -> list[dict[str, Optional[str]]]:
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        return []

    normalized_events: list[dict[str, Optional[str]]] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        target = raw_event.get("target") if isinstance(raw_event.get("target"), dict) else {}
        action = raw_event.get("action")
        repository_name = target.get("repository") or raw_event.get("repository")
        media_type = target.get("mediaType")
        if action not in {"push", "delete"} or not isinstance(repository_name, str):
            continue
        # Distribution delete notifications omit target.mediaType, while push
        # notifications include it for manifests and indexes. Only require a
        # manifest media type for push events so digest-based delete events
        # still invalidate cached rows.
        if action == "push" and not _is_manifest_notification_media_type(media_type):
            continue
        normalized_events.append(
            {
                "action": action,
                "repository_name": repository_name,
                "tag": raw_event.get("tag") or target.get("tag"),
                "digest": target.get("digest"),
                "media_type": media_type,
                "raw_payload": raw_event,
            }
        )
    return normalized_events


def _serialize_history_variant(variant: HistoryVariant) -> dict:
    return {
        "platform": variant.platform,
        "manifest_digest": variant.manifest_digest,
        "config_digest": variant.config_digest,
        "created_at": variant.created_at,
        "entries": variant.entries,
        "entry_count": len(variant.entries),
        "history_truncated": variant.history_truncated,
    }


def _log_output_line_count(log_output: Optional[str]) -> int:
    if not log_output:
        return 0
    return len([line for line in log_output.split("\n") if line])


def _serialize_gc_job(job: GcJob, *, include_log_output: bool = True) -> dict:
    log_output = job.log_output or ""
    return {
        "id": job.id,
        "status": job.status,
        "requested_by": job.requested_by,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "dry_run": job.dry_run,
        "delete_untagged": job.delete_untagged,
        "prune_empty_dirs": job.prune_empty_dirs,
        "bytes_before": job.bytes_before,
        "bytes_after": job.bytes_after,
        "log_output": job.log_output if include_log_output else None,
        "log_output_available": bool(log_output),
        "log_output_line_count": _log_output_line_count(log_output),
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _serialize_registry_state_rebuild_job(
    job: RegistryStateRebuildJob,
    *,
    include_log_output: bool = True,
) -> dict:
    log_output = job.log_output or ""
    return {
        "id": job.id,
        "status": job.status,
        "requested_by": job.requested_by,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "repositories_scanned": job.repositories_scanned,
        "repositories_updated": job.repositories_updated,
        "repositories_deleted": job.repositories_deleted,
        "tags_scanned": job.tags_scanned,
        "tags_updated": job.tags_updated,
        "tags_deleted": job.tags_deleted,
        "manifest_summaries_updated": job.manifest_summaries_updated,
        "log_output": job.log_output if include_log_output else None,
        "log_output_available": bool(log_output),
        "log_output_line_count": _log_output_line_count(log_output),
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _serialize_registry_event_inbox_entry(row: RegistryEventInbox) -> dict:
    return {
        "id": row.id,
        "action": row.action,
        "repository_name": row.repository_name,
        "tag": row.tag,
        "digest": row.digest,
        "media_type": row.media_type,
        "raw_payload": row.raw_payload,
        "dedupe_key": row.dedupe_key,
        "status": row.status,
        "attempts": row.attempts,
        "error": row.error,
        "received_at": row.received_at.isoformat(),
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def _serialize_audit_event(event: AuditEvent, actor_label: Optional[str]) -> dict:
    return {
        "id": event.id,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "actor_label": actor_label,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "metadata_json": event.metadata_json,
        "created_at": event.created_at.isoformat(),
    }


def _count_active_tokens(tokens: list[object]) -> int:
    return sum(1 for token in tokens if getattr(token, "revoked_at", None) is None)


def _bucket_counts(items: list[datetime], days: int = 7) -> list[dict]:
    today = datetime.utcnow().date()
    buckets: list[dict] = []
    for offset in range(days - 1, -1, -1):
        day = today.fromordinal(today.toordinal() - offset)
        count = sum(1 for item in items if item.date() == day)
        buckets.append({"label": day.strftime("%a"), "count": count})
    return buckets


def _is_pull_token_event(event: AuditEvent) -> bool:
    metadata = event.metadata_json or {}
    granted_scope = metadata.get("granted_scope") or []
    for scope in granted_scope:
        if scope.get("type") != "repository":
            continue
        if "pull" in (scope.get("actions") or []):
            return True
    return False


def _pull_token_events(db: Session, *, since: Optional[datetime] = None) -> list[AuditEvent]:
    filters = [
        AuditEvent.action == "registry_token_issued",
        AuditEvent.target_type == "registry_token",
    ]
    if since is not None:
        filters.append(AuditEvent.created_at >= since)
    events = db.scalars(
        select(AuditEvent)
        .where(*filters)
        .order_by(AuditEvent.created_at.desc())
    ).all()
    return [event for event in events if _is_pull_token_event(event)]


def _registry_activity_trend(db: Session, *, days: int = 7) -> dict[str, list[dict]]:
    start_date = datetime.utcnow().date() - timedelta(days=days - 1)
    start_at = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    registry_events = db.scalars(
        select(RegistryEventInbox)
        .where(
            RegistryEventInbox.received_at >= start_at,
            RegistryEventInbox.action.in_(("push", "delete")),
        )
        .order_by(RegistryEventInbox.received_at.desc())
    ).all()
    pull_token_events = _pull_token_events(db, since=start_at)
    return {
        "pushes": _bucket_counts([event.received_at for event in registry_events if event.action == "push"], days=days),
        "pull_tokens": _bucket_counts([event.created_at for event in pull_token_events], days=days),
        "deletions": _bucket_counts([event.received_at for event in registry_events if event.action == "delete"], days=days),
    }


def _dashboard_user_detail(user: User) -> str:
    return user.email


def _dashboard_token_detail(is_admin_subject: bool) -> str:
    if is_admin_subject:
        return "Token issued"
    return "Token hidden for non-admin account"


def _dashboard_robot_token_detail() -> str:
    return "Token hidden for automation account"


def _dashboard_activity(
    users: list[User],
    pats: list[PersonalAccessToken],
    robots: list[RobotAccount],
    robot_tokens: list[RobotToken],
) -> list[dict]:
    events: list[dict] = []
    for user in users:
        events.append(
            {
                "type": "user_created",
                "title": f"User {user.username} provisioned",
                "timestamp": user.created_at.isoformat(),
                "detail": _dashboard_user_detail(user),
            }
        )
    for token in pats:
        events.append(
            {
                "type": "pat_created",
                "title": f"PAT {token.name} issued",
                "timestamp": token.created_at.isoformat(),
                "detail": _dashboard_token_detail(token.user.is_admin),
            }
        )
    for robot in robots:
        events.append(
            {
                "type": "robot_created",
                "title": f"Robot {robot.name} created",
                "timestamp": robot.created_at.isoformat(),
                "detail": robot.description or "Automation identity",
            }
        )
    for token in robot_tokens:
        events.append(
            {
                "type": "robot_token_created",
                "title": f"Robot token {token.name} issued",
                "timestamp": token.created_at.isoformat(),
                "detail": _dashboard_robot_token_detail(),
            }
        )

    events.sort(key=lambda item: item["timestamp"], reverse=True)
    return events[:8]


def require_authenticated_user(request: Request, db: Session = Depends(get_db)) -> User:
    require_setup_complete(db, request.app.state.settings)
    _session, user = _get_authenticated_user(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


def require_admin_user(user: User = Depends(require_authenticated_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return user


def _same_origin(url: str, expected_origin: str) -> bool:
    parts = urlsplit(url)
    actual_origin = f"{parts.scheme}://{parts.netloc}"
    return actual_origin == expected_origin


def _expected_request_origins(request: Request) -> set[str]:
    settings = request.app.state.settings
    origins = set()
    public_origin = getattr(request.app.state, "public_registry_origin", None) or settings.public_registry_origin
    if public_origin:
        origins.add(public_origin)
    origins.update(settings.csrf_trusted_origins)
    origins.add(str(request.base_url).rstrip("/"))
    return origins


def _validate_same_origin_request(request: Request) -> None:
    expected_origins = _expected_request_origins(request)
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    fetch_site = request.headers.get("Sec-Fetch-Site")

    if origin:
        if origin not in expected_origins:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin.")
        return
    if referer:
        if not any(_same_origin(referer, expected_origin) for expected_origin in expected_origins):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin.")
        return
    if fetch_site and fetch_site not in {"same-origin", "none"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid request origin.")


def _validate_csrf_token(request: Request, db: Session) -> None:
    submitted = request.headers.get("X-CSRF-Token")
    if not submitted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF token.")
    web_session, _current_user = _get_authenticated_user(request, db)
    if web_session is None or web_session.csrf_token != submitted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")


def require_csrf(request: Request, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)) -> User:
    _validate_same_origin_request(request)
    _validate_csrf_token(request, db)
    return user


def require_csrf_token(request: Request, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)) -> User:
    _validate_csrf_token(request, db)
    return user


class LoginPayload(BaseModel):
    username: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Username")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class CreateUserPayload(BaseModel):
    username: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    email: EmailStr
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH)
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Username")

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        email = str(value).strip()
        if len(email) > MAX_EMAIL_LENGTH:
            raise ValueError(f"Email must be {MAX_EMAIL_LENGTH} characters or fewer.")
        return email

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class ResetUserPasswordPayload(BaseModel):
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH)
    current_password: Optional[str] = Field(default=None, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password(value)


class CreatePatPayload(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    expires_at: Optional[datetime] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Token name")


class CreateRobotPayload(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Robot name")

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional_text(value, field_name="Description")


class CreateRobotTokenPayload(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    expires_at: Optional[datetime] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Robot token name")


class DeleteRobotPayload(BaseModel):
    confirmation: str = Field(min_length=1)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Confirmation")


class DeleteTagPayload(BaseModel):
    confirmation: str = Field(min_length=1)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Confirmation")


class DeleteTagsPayload(BaseModel):
    tags: list[str] = Field(min_length=1, max_length=100)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        normalized_tags: list[str] = []
        seen_tags: set[str] = set()
        for tag in value:
            normalized = _normalize_required_text(tag, field_name="Tag")
            if normalized in seen_tags:
                continue
            seen_tags.add(normalized)
            normalized_tags.append(normalized)
        if not normalized_tags:
            raise ValueError("At least one tag is required.")
        return normalized_tags


class DeleteRepositoryPayload(BaseModel):
    confirmation: str = Field(min_length=1)

    @field_validator("confirmation")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Confirmation")


class CreateGcJobPayload(BaseModel):
    dry_run: bool = True
    delete_untagged: bool = False
    prune_empty_dirs: bool = False


class UpsertPermissionPayload(BaseModel):
    subject_type: str = Field(min_length=1, max_length=32)
    subject_id: int = Field(gt=0)
    repository_pattern: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    can_pull: bool = False
    can_push: bool = False
    can_delete: bool = False

    @field_validator("subject_type")
    @classmethod
    def validate_subject_type(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Subject type", max_length=32).lower()

    @field_validator("repository_pattern")
    @classmethod
    def validate_repository_pattern(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Repository pattern")


class UpsertRepositoryVisibilityPayload(BaseModel):
    repository_name: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    visibility: str = Field(min_length=1, max_length=32)

    @field_validator("repository_name")
    @classmethod
    def validate_repository_name(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Repository name")

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Visibility", max_length=32).lower()


class SetupCompletePayload(BaseModel):
    setup_token: str = Field(min_length=1, max_length=512)
    admin_username: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH)
    public_registry_origin: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)

    @field_validator("setup_token")
    @classmethod
    def validate_setup_token(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Setup token", max_length=512)

    @field_validator("admin_username")
    @classmethod
    def validate_admin_username(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Admin username")

    @field_validator("admin_email")
    @classmethod
    def validate_admin_email(cls, value: EmailStr) -> str:
        email = str(value).strip()
        if len(email) > MAX_EMAIL_LENGTH:
            raise ValueError(f"Email must be {MAX_EMAIL_LENGTH} characters or fewer.")
        return email

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, value: str) -> str:
        return _validate_password(value)

    @field_validator("public_registry_origin")
    @classmethod
    def validate_public_origin_text(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Public registry origin")


class UpdateSettingsPayload(BaseModel):
    public_registry_origin: str = Field(min_length=1, max_length=MAX_SHORT_TEXT_LENGTH)
    ui_timezone: str = Field(min_length=1, max_length=128)
    repository_tags_page_size: int = Field(default=DEFAULT_REPOSITORY_TAGS_PAGE_SIZE, ge=1, le=100)
    audit_log_retention_days: int = Field(default=DEFAULT_AUDIT_LOG_RETENTION_DAYS, ge=1)
    automatic_registry_state_rebuild: bool = False
    storage_usage_refresh_interval_seconds: int = Field(
        default=DEFAULT_STORAGE_USAGE_REFRESH_INTERVAL_SECONDS,
        ge=0,
        le=86400,
    )

    @field_validator("public_registry_origin")
    @classmethod
    def validate_public_origin_text(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Public registry origin")

    @field_validator("ui_timezone")
    @classmethod
    def validate_ui_timezone_text(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="UI timezone", max_length=128)


def _setup_response(*, setup_complete: bool, registry_restart_required: bool) -> dict:
    return {
        "ok": True,
        "setup_complete": setup_complete,
        "registry_restart_required": registry_restart_required,
        "restart_command": RESTART_COMMAND if registry_restart_required else None,
    }


@router.get("/setup/status")
def get_setup_status(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    status_payload = setup_status(db, settings)
    public_origin = status_payload.public_registry_origin or getattr(request.app.state, "public_registry_origin", None)
    return {
        "setup_required": status_payload.setup_required,
        "public_registry_origin": public_origin,
        "env_bootstrap_available": status_payload.env_bootstrap_available,
        "env_bootstrap_partial": status_payload.env_bootstrap_partial,
        "registry_restart_required": status_payload.registry_restart_required,
    }


@router.post("/setup/complete")
def complete_first_boot_setup(
    payload: SetupCompletePayload,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    client_host = request.client.host if request.client and request.client.host else "unknown"
    rate_limit_key = f"{client_host}:setup"
    rate_limiter = request.app.state.setup_rate_limiter
    retry_after = rate_limiter.retry_after(rate_limit_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many setup attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if not setup_required(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup has already been completed.")
    if not verify_setup_token(settings, payload.setup_token):
        rate_limiter.add_failure(rate_limit_key)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid setup token.")

    try:
        user = complete_setup(
            db,
            settings,
            admin_username=payload.admin_username,
            admin_email=str(payload.admin_email),
            admin_password=payload.admin_password,
            public_registry_origin=payload.public_registry_origin,
        )
    except SetupError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    rate_limiter.reset(rate_limit_key)
    public_origin = saved_public_registry_origin(db) or payload.public_registry_origin.rstrip("/")
    request.app.state.public_registry_origin = public_origin
    record_audit_event(
        db,
        actor=user,
        action="first_boot_setup_completed",
        target_type="app_setting",
        metadata_json={"public_registry_origin": public_origin},
    )
    return _setup_response(setup_complete=True, registry_restart_required=True)


@router.post("/session/login")
def login(
    request: Request,
    payload: LoginPayload,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    require_setup_complete(db, settings)
    client_host = request.client.host if request.client and request.client.host else "unknown"
    rate_limit_key = f"{client_host}:{payload.username.casefold()}"
    rate_limiter = request.app.state.login_rate_limiter
    retry_after = rate_limiter.retry_after(rate_limit_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not user.is_active or user.deleted_at is not None or not verify_password(payload.password, user.password_hash):
        rate_limiter.add_failure(rate_limit_key)
        increment_metric("registry_ui_login_failures_total")
        record_audit_event(
            db,
            action="ui_login_failed",
            actor_type="user",
            metadata_json={"username": payload.username},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password.")

    rate_limiter.reset(rate_limit_key)
    issued = create_session(db, user=user, settings=settings)
    increment_metric("registry_ui_logins_total")
    record_audit_event(
        db,
        actor=user,
        action="ui_login_succeeded",
        target_type="session",
        metadata_json={"username": user.username},
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issued.raw_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_lifetime_seconds,
        path="/",
    )
    response.set_cookie(
        key="rcr_csrf",
        value=issued.csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_lifetime_seconds,
        path="/",
    )
    return {"user": _serialize_user(user)}


@router.post("/session/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_csrf_token),
    settings: Settings = Depends(get_settings),
):
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        revoke_session(db, raw_token)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie("rcr_csrf", path="/")
    return {"ok": True, "user_id": user.id}


@router.get("/session/me")
def current_user(user: User = Depends(require_authenticated_user)):
    return {"user": _serialize_user(user)}


@router.get("/admin/users")
def list_users(
    page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    safe_page = max(page, 1)
    page_size = effective_default_page_size(db)
    base_query = select(User).where(User.deleted_at.is_(None)).order_by(User.username.asc())
    total_users = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    users = db.scalars(base_query.offset((safe_page - 1) * page_size).limit(page_size)).all()
    return {
        "users": [_serialize_user(user) for user in users],
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": total_users,
            "has_prev": safe_page > 1,
            "has_next": safe_page * page_size < total_users,
        },
    }


@router.get("/admin/users/{user_id}")
def get_user_detail(
    user_id: int,
    activity_page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    tokens = db.scalars(
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user.id)
        .order_by(PersonalAccessToken.created_at.desc())
    ).all()
    permissions = db.scalars(
        select(RepositoryPermission)
        .where(
            RepositoryPermission.subject_type == "user",
            RepositoryPermission.subject_id == user.id,
        )
        .order_by(RepositoryPermission.repository_pattern.asc())
    ).all()
    safe_activity_page = max(activity_page, 1)
    activity_page_size = effective_default_page_size(db)
    activity_query = select(AuditEvent).where(
        ((AuditEvent.actor_type == "user") & (AuditEvent.actor_id == user.id))
        | ((AuditEvent.target_type == "user") & (AuditEvent.target_id == user.id))
    ).order_by(AuditEvent.created_at.desc())
    total_activities = db.scalar(select(func.count()).select_from(activity_query.subquery())) or 0
    events = db.scalars(
        activity_query.offset((safe_activity_page - 1) * activity_page_size).limit(activity_page_size)
    ).all()

    actor_ids = sorted({event.actor_id for event in events if event.actor_type == "user" and event.actor_id is not None})
    actor_names: dict[int, str] = {}
    if actor_ids:
        actors = db.scalars(select(User).where(User.id.in_(actor_ids))).all()
        actor_names = {actor.id: _user_audit_label(actor) for actor in actors}

    return {
        "user": _serialize_user(user),
        "tokens": [_serialize_token(token) for token in tokens],
        "permissions": [_serialize_permission(permission, subject_name=user.username) for permission in permissions],
        "recent_activity": _serialize_entity_activity(events, actor_names),
        "activity_pagination": {
            "page": safe_activity_page,
            "page_size": activity_page_size,
            "total": total_activities,
            "has_prev": safe_activity_page > 1,
            "has_next": safe_activity_page * activity_page_size < total_activities,
        },
    }


@router.post("/admin/users")
def create_user(
    payload: CreateUserPayload,
    _csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = User(
        username=payload.username,
        email=str(payload.email),
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that username or email already exists.",
        ) from exc
    db.refresh(user)
    return {"user": _serialize_user(user)}


@router.post("/admin/users/{user_id}/disable")
def disable_user(
    user_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == csrf_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot disable your own account.",
        )
    user.is_active = False
    db.commit()
    return {"user": _serialize_user(user)}


@router.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == csrf_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account.",
        )
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Disable the user before deleting it.",
        )

    deleted_at = datetime.now(timezone.utc)
    original_username = user.username
    original_email = user.email
    tombstone_username, tombstone_email = _deleted_user_identity(db, user)

    sessions = db.scalars(
        select(WebSession).where(
            WebSession.user_id == user.id,
            WebSession.revoked_at.is_(None),
        )
    ).all()
    for web_session in sessions:
        web_session.revoked_at = deleted_at

    tokens = db.scalars(
        select(PersonalAccessToken).where(
            PersonalAccessToken.user_id == user.id,
            PersonalAccessToken.revoked_at.is_(None),
        )
    ).all()
    for token in tokens:
        token.revoked_at = deleted_at

    permissions = db.scalars(
        select(RepositoryPermission).where(
            RepositoryPermission.subject_type == "user",
            RepositoryPermission.subject_id == user.id,
        )
    ).all()
    for permission in permissions:
        db.delete(permission)

    user.is_active = False
    user.deleted_at = deleted_at
    user.deleted_by = csrf_user.id
    user.deleted_username = original_username
    user.username = tombstone_username
    user.email = tombstone_email

    record_audit_event(
        db,
        actor=csrf_user,
        action="user_deleted",
        target_type="user",
        target_id=user.id,
        metadata_json={
            "username": original_username,
            "email": original_email,
            "revoked_sessions": len(sessions),
            "revoked_tokens": len(tokens),
            "deleted_permissions": len(permissions),
        },
    )
    return {
        "deleted": True,
        "user_id": user_id,
        "revoked_sessions": len(sessions),
        "revoked_tokens": len(tokens),
        "deleted_permissions": len(permissions),
    }


@router.post("/admin/users/{user_id}/enable")
def enable_user(
    user_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = True
    db.commit()
    record_audit_event(
        db,
        actor=csrf_user,
        action="user_enabled",
        target_type="user",
        target_id=user.id,
        metadata_json={"username": user.username},
    )
    return {"user": _serialize_user(user)}


@router.post("/admin/users/{user_id}/password")
def reset_user_password(
    user_id: int,
    payload: ResetUserPasswordPayload,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == csrf_user.id:
        if payload.current_password is None or not verify_password(payload.current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")
    user.password_hash = hash_password(payload.password)
    db.commit()
    revoked_sessions = revoke_user_sessions(db, user_id=user.id)
    record_audit_event(
        db,
        actor=csrf_user,
        action="user_password_reset",
        target_type="user",
        target_id=user.id,
        metadata_json={"username": user.username, "revoked_sessions": revoked_sessions},
    )
    return {"user": _serialize_user(user), "revoked_sessions": revoked_sessions}


@router.get("/admin/sessions")
def list_web_sessions(
    request: Request,
    page: int = 1,
    page_size: Optional[int] = None,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    safe_page = max(page, 1)
    requested_page_size = effective_default_page_size(db) if page_size is None else page_size
    safe_page_size = min(max(requested_page_size, 1), 100)
    current_session, _current_user = _get_authenticated_user(request, db)
    current_session_id = current_session.id if current_session else None
    total_sessions = db.scalar(select(func.count()).select_from(WebSession)) or 0
    sessions = db.scalars(
        select(WebSession)
        .order_by(WebSession.revoked_at.is_(None).desc(), WebSession.last_seen_at.desc())
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    ).all()
    user_ids = {web_session.user_id for web_session in sessions}
    users = db.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    users_by_id = {user.id: user for user in users}
    now = datetime.now(timezone.utc)
    active_sessions = db.scalar(
        select(func.count())
        .select_from(WebSession)
        .where(
            WebSession.revoked_at.is_(None),
            WebSession.expires_at > now,
        )
    ) or 0
    expired_sessions = db.scalar(
        select(func.count())
        .select_from(WebSession)
        .where(
            WebSession.revoked_at.is_(None),
            WebSession.expires_at <= now,
        )
    ) or 0
    revoked_sessions = db.scalar(
        select(func.count()).select_from(WebSession).where(WebSession.revoked_at.is_not(None))
    ) or 0

    return {
        "sessions": [
            _serialize_web_session(web_session, user=users_by_id[web_session.user_id], current_session_id=current_session_id)
            for web_session in sessions
            if web_session.user_id in users_by_id
        ],
        "summary": {
            "active_sessions": active_sessions,
            "expired_sessions": expired_sessions,
            "revoked_sessions": revoked_sessions,
            "total_sessions": total_sessions,
        },
        "pagination": {
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total_sessions,
            "has_prev": safe_page > 1,
            "has_next": safe_page * safe_page_size < total_sessions,
        },
    }


@router.post("/admin/sessions/{session_id}/revoke")
def revoke_web_session(
    session_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    web_session = db.get(WebSession, session_id)
    if web_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    if web_session.revoked_at is None:
        web_session.revoked_at = datetime.utcnow()
        db.commit()
    record_audit_event(
        db,
        actor=csrf_user,
        action="web_session_revoked",
        target_type="web_session",
        target_id=web_session.id,
        metadata_json={"user_id": web_session.user_id},
    )
    return {"session_id": web_session.id, "revoked": True}


@router.post("/admin/users/{user_id}/sessions/revoke")
def revoke_user_web_sessions(
    user_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    revoked_sessions = revoke_user_sessions(db, user_id=user.id)
    record_audit_event(
        db,
        actor=csrf_user,
        action="user_sessions_revoked",
        target_type="user",
        target_id=user.id,
        metadata_json={"username": user.username, "revoked_sessions": revoked_sessions},
    )
    return {"user": _serialize_user(user), "revoked_sessions": revoked_sessions}


@router.get("/admin/tokens")
def list_tokens(
    page: int = 1,
    user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    safe_page = max(page, 1)
    page_size = effective_default_page_size(db)
    query = (
        select(PersonalAccessToken)
        .where(PersonalAccessToken.user_id == user.id)
        .order_by(PersonalAccessToken.created_at.desc())
    )
    total_tokens = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    tokens = db.scalars(
        query.offset((safe_page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "tokens": [_serialize_token(token) for token in tokens],
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": total_tokens,
            "has_prev": safe_page > 1,
            "has_next": safe_page * page_size < total_tokens,
        },
    }


@router.post("/admin/tokens")
def create_pat(
    payload: CreatePatPayload,
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    issued = issue_personal_access_token(db, user_id=user.id, name=payload.name, expires_at=payload.expires_at)
    db.commit()
    token = db.scalar(select(PersonalAccessToken).where(PersonalAccessToken.token_prefix == issued.token_prefix))
    if token is not None:
        record_audit_event(
            db,
            actor=user,
            action="pat_created",
            target_type="personal_access_token",
            target_id=token.id,
            metadata_json={"name": token.name, "token_prefix": token.token_prefix},
        )
    return {
        "token": _serialize_token(token),
        "raw_token": issued.raw_token,
    }


def _repository_storage_path(settings: Settings, repository_name: str) -> Path:
    root = Path(settings.registry_storage_root).resolve()
    segments = repository_name.split("/")
    if not segments or any(segment in {"", ".", ".."} for segment in segments):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid repository name.")
    repo_path = root.joinpath(*segments).resolve()
    try:
        repo_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid repository name.") from exc
    return repo_path


@router.post("/admin/tokens/{token_id}/revoke")
def revoke_pat(
    token_id: int,
    _csrf_user: User = Depends(require_csrf),
    user: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    token = db.get(PersonalAccessToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found.")
    token.revoked_at = datetime.utcnow()
    db.commit()
    record_audit_event(
        db,
        actor=user,
        action="pat_revoked",
        target_type="personal_access_token",
        target_id=token.id,
        metadata_json={"name": token.name, "token_prefix": token.token_prefix},
    )
    return {"token": _serialize_token(token)}


@router.get("/admin/robots")
def list_robots(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    robots = db.scalars(select(RobotAccount).order_by(RobotAccount.name.asc())).all()
    return {"robots": [_serialize_robot(robot) for robot in robots]}


@router.get("/admin/robots/{robot_id}")
def get_robot_detail(
    robot_id: int,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    robot = db.get(RobotAccount, robot_id)
    if robot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot account not found.")

    permissions = db.scalars(
        select(RepositoryPermission)
        .where(
            RepositoryPermission.subject_type == "robot",
            RepositoryPermission.subject_id == robot.id,
        )
        .order_by(RepositoryPermission.repository_pattern.asc())
    ).all()
    events = db.scalars(
        select(AuditEvent)
        .where(
            (AuditEvent.target_type == "robot_account") & (AuditEvent.target_id == robot.id)
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(10)
    ).all()

    actor_ids = sorted({event.actor_id for event in events if event.actor_type == "user" and event.actor_id is not None})
    actor_names: dict[int, str] = {}
    if actor_ids:
        actors = db.scalars(select(User).where(User.id.in_(actor_ids))).all()
        actor_names = {actor.id: _user_audit_label(actor) for actor in actors}

    return {
        "robot": _serialize_robot(robot),
        "permissions": [_serialize_permission(permission, subject_name=robot.name) for permission in permissions],
        "recent_activity": _serialize_entity_activity(events, actor_names),
    }


@router.get("/admin/permissions")
def list_permissions(
    page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.username.asc())).all()
    robots = db.scalars(select(RobotAccount).order_by(RobotAccount.name.asc())).all()
    safe_page = max(page, 1)
    page_size = effective_default_page_size(db)
    query = select(RepositoryPermission).order_by(
        RepositoryPermission.subject_type.asc(),
        RepositoryPermission.subject_id.asc(),
        RepositoryPermission.repository_pattern.asc(),
    )
    total_permissions = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    permissions = db.scalars(
        query.offset((safe_page - 1) * page_size).limit(page_size)
    ).all()
    user_names = {user.id: _user_audit_label(user) for user in users}
    robot_names = {robot.id: robot.name for robot in robots}
    return {
        "users": [_serialize_user(user) for user in users],
        "robots": [_serialize_robot(robot) for robot in robots],
        "permissions": [
            _serialize_permission(
                permission,
                subject_name=user_names.get(permission.subject_id)
                if permission.subject_type == "user"
                else robot_names.get(permission.subject_id),
            )
            for permission in permissions
        ],
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": total_permissions,
            "has_prev": safe_page > 1,
            "has_next": safe_page * page_size < total_permissions,
        },
    }


@router.post("/admin/permissions")
def upsert_permission(
    payload: UpsertPermissionPayload,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    if payload.subject_type not in {"user", "robot"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported subject type.")
    if not any([payload.can_pull, payload.can_push, payload.can_delete]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one permission.")

    subject_name: Optional[str]
    if payload.subject_type == "user":
        subject = db.get(User, payload.subject_id)
        if subject is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        subject_name = subject.username
    else:
        subject = db.get(RobotAccount, payload.subject_id)
        if subject is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot account not found.")
        subject_name = subject.name

    try:
        repository_pattern = validate_repository_pattern(payload.repository_pattern)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    permission = db.scalar(
        select(RepositoryPermission).where(
            RepositoryPermission.subject_type == payload.subject_type,
            RepositoryPermission.subject_id == payload.subject_id,
            RepositoryPermission.repository_pattern == repository_pattern,
        )
    )
    created = permission is None
    if permission is None:
        permission = RepositoryPermission(
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            repository_pattern=repository_pattern,
        )
        db.add(permission)

    permission.can_pull = payload.can_pull
    permission.can_push = payload.can_push
    permission.can_delete = payload.can_delete
    db.commit()
    db.refresh(permission)
    record_audit_event(
        db,
        actor=csrf_user,
        action="repository_permission_created" if created else "repository_permission_updated",
        target_type="repository_permission",
        target_id=permission.id,
        metadata_json={
            "subject_type": permission.subject_type,
            "subject_id": permission.subject_id,
            "subject_name": subject_name,
            "repository_pattern": permission.repository_pattern,
            "can_pull": permission.can_pull,
            "can_push": permission.can_push,
            "can_delete": permission.can_delete,
        },
    )
    return {"permission": _serialize_permission(permission, subject_name=subject_name)}


@router.post("/admin/permissions/{permission_id}/delete")
def delete_permission(
    permission_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    permission = db.get(RepositoryPermission, permission_id)
    if permission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found.")

    record_audit_event(
        db,
        actor=csrf_user,
        action="repository_permission_deleted",
        target_type="repository_permission",
        target_id=permission.id,
        metadata_json={
            "subject_type": permission.subject_type,
            "subject_id": permission.subject_id,
            "repository_pattern": permission.repository_pattern,
            "can_pull": permission.can_pull,
            "can_push": permission.can_push,
            "can_delete": permission.can_delete,
        },
    )
    db.delete(permission)
    db.commit()
    return {"ok": True, "permission_id": permission_id}


@router.post("/admin/repositories/visibility")
def upsert_repository_visibility(
    payload: UpsertRepositoryVisibilityPayload,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    try:
        repository_name = validate_repository_name(payload.repository_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    visibility = payload.visibility.strip().lower()
    if visibility not in {"private", "public"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Visibility must be 'private' or 'public'.")

    repository = db.scalar(select(Repository).where(Repository.name == repository_name))
    created = repository is None
    if repository is None:
        repository = Repository(name=repository_name, visibility=visibility)
        db.add(repository)
    else:
        repository.visibility = visibility

    db.commit()
    db.refresh(repository)
    record_audit_event(
        db,
        actor=csrf_user,
        action="repository_visibility_created" if created else "repository_visibility_updated",
        target_type="repository",
        target_id=repository.id,
        metadata_json={
            "repository_name": repository.name,
            "visibility": repository.visibility,
        },
    )
    return {"repository": _serialize_repository(repository)}


@router.post("/admin/robots")
def create_robot(
    payload: CreateRobotPayload,
    _csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    robot = RobotAccount(name=payload.name, description=payload.description, is_active=True)
    db.add(robot)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A robot with that name already exists.",
        ) from exc
    db.refresh(robot)
    record_audit_event(
        db,
        actor=_admin,
        action="robot_created",
        target_type="robot_account",
        target_id=robot.id,
        metadata_json={"robot": robot.name},
    )
    return {"robot": _serialize_robot(robot)}


@router.post("/admin/robots/{robot_id}/tokens")
def create_robot_token(
    robot_id: int,
    payload: CreateRobotTokenPayload,
    _csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    robot = db.get(RobotAccount, robot_id)
    if robot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot account not found.")
    issued = issue_robot_token(db, robot_id=robot.id, name=payload.name, expires_at=payload.expires_at)
    db.commit()
    db.refresh(robot)
    created_token = next((token for token in robot.robot_tokens if token.token_prefix == issued.token_prefix), None)
    record_audit_event(
        db,
        actor=_admin,
        action="robot_token_created",
        target_type="robot_token",
        target_id=created_token.id if created_token else None,
        metadata_json={"robot": robot.name, "name": payload.name, "token_prefix": issued.token_prefix},
    )
    return {"robot": _serialize_robot(robot), "raw_token": issued.raw_token}


@router.post("/admin/robots/{robot_id}/disable")
def disable_robot(
    robot_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    robot = db.get(RobotAccount, robot_id)
    if robot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot account not found.")
    robot.is_active = False
    db.commit()
    record_audit_event(
        db,
        actor=csrf_user,
        action="robot_disabled",
        target_type="robot_account",
        target_id=robot.id,
        metadata_json={"robot": robot.name},
    )
    return {"robot": _serialize_robot(robot)}


@router.post("/admin/robots/{robot_id}/enable")
def enable_robot(
    robot_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    robot = db.get(RobotAccount, robot_id)
    if robot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot account not found.")
    robot.is_active = True
    db.commit()
    record_audit_event(
        db,
        actor=csrf_user,
        action="robot_enabled",
        target_type="robot_account",
        target_id=robot.id,
        metadata_json={"robot": robot.name},
    )
    return {"robot": _serialize_robot(robot)}


@router.post("/admin/robots/{robot_id}/tokens/{token_id}/revoke")
def revoke_robot_token(
    robot_id: int,
    token_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    token = db.get(RobotToken, token_id)
    if token is None or token.robot_id != robot_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot token not found.")
    token.revoked_at = datetime.utcnow()
    db.commit()
    record_audit_event(
        db,
        actor=csrf_user,
        action="robot_token_revoked",
        target_type="robot_token",
        target_id=token.id,
        metadata_json={"robot_id": robot_id, "name": token.name, "token_prefix": token.token_prefix},
    )
    return {"token": {"id": token.id, "revoked_at": token.revoked_at.isoformat()}}


@router.post("/admin/robots/{robot_id}/delete")
def delete_robot(
    robot_id: int,
    payload: DeleteRobotPayload,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    robot = db.get(RobotAccount, robot_id)
    if robot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Robot account not found.")
    if payload.confirmation != robot.name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation text mismatch.")

    record_audit_event(
        db,
        actor=csrf_user,
        action="robot_deleted",
        target_type="robot_account",
        target_id=robot.id,
        metadata_json={"robot": robot.name},
    )
    for token in list(robot.robot_tokens):
        db.delete(token)
    db.delete(robot)
    db.commit()
    return {"ok": True, "robot_id": robot_id}


@router.get("/admin/dashboard")
def admin_dashboard(
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())).all()
    pats = db.scalars(select(PersonalAccessToken).order_by(PersonalAccessToken.created_at.desc())).all()
    robots = db.scalars(select(RobotAccount).order_by(RobotAccount.created_at.desc())).all()
    robot_tokens = db.scalars(select(RobotToken).order_by(RobotToken.created_at.desc())).all()

    total_repositories = db.scalar(
        select(func.count(func.distinct(Repository.id)))
        .join(RepositoryTag)
        .where(
            Repository.deleted_at.is_(None),
            RepositoryTag.deleted_at.is_(None),
        )
    ) or 0
    total_tags = db.scalar(
        select(func.count(RepositoryTag.id))
        .join(Repository)
        .where(
            Repository.deleted_at.is_(None),
            RepositoryTag.deleted_at.is_(None),
        )
    ) or 0
    repo_rows = [
        {"name": name, "tag_count": int(tag_count)}
        for name, tag_count in db.execute(
            select(Repository.name, func.count(RepositoryTag.id).label("tag_count"))
            .join(RepositoryTag)
            .where(
                Repository.deleted_at.is_(None),
                RepositoryTag.deleted_at.is_(None),
            )
            .group_by(Repository.id, Repository.name)
            .order_by(func.count(RepositoryTag.id).desc(), Repository.name.asc())
            .limit(settings.dashboard_max_repositories)
        ).all()
    ]
    repo_truncation = {
        "truncated": total_repositories > settings.dashboard_max_repositories,
        "pages_fetched": 0,
        "returned": len(repo_rows),
    }

    return {
        "stats": {
            "users_total": len(users),
            "users_active": sum(1 for user in users if user.is_active),
            "pats_active": _count_active_tokens(pats),
            "robots_active": sum(1 for robot in robots if robot.is_active),
            "registry_repositories": int(total_repositories),
            "registry_tags": int(total_tags),
            "pull_tokens_issued": len(_pull_token_events(db)),
        },
        "repo_distribution": repo_rows[:6],
        "repo_distribution_truncation": repo_truncation,
        "provisioning_trend": {
            "users": _bucket_counts([user.created_at for user in users]),
            "tokens": _bucket_counts([token.created_at for token in pats + robot_tokens]),
            "robots": _bucket_counts([robot.created_at for robot in robots]),
        },
        "registry_activity_trend": _registry_activity_trend(db),
        "recent_activity": _dashboard_activity(users, pats, robots, robot_tokens),
    }


@router.get("/admin/settings")
def admin_settings(
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return {
        "build": {
            "version": settings.app_version,
            "revision": settings.app_revision,
            "built_at": settings.app_build_time,
            "image_tag": settings.app_image_tag,
        },
        "public_registry_origin": effective_public_registry_origin(db, settings),
        "ui_timezone": effective_ui_timezone(db),
        "repository_tags_page_size": effective_default_page_size(db),
        "audit_log_retention_days": effective_audit_log_retention_days(db, fallback_days=settings.log_retention_days),
        "automatic_registry_state_rebuild": automatic_registry_state_rebuild_enabled(db),
        "storage_usage_refresh_interval_seconds": effective_storage_usage_refresh_interval_seconds(db),
        "default_audit_log_retention_days": DEFAULT_AUDIT_LOG_RETENTION_DAYS,
        "default_repository_tags_page_size": DEFAULT_REPOSITORY_TAGS_PAGE_SIZE,
        "default_storage_usage_refresh_interval_seconds": DEFAULT_STORAGE_USAGE_REFRESH_INTERVAL_SECONDS,
        "default_ui_timezone": DEFAULT_UI_TIMEZONE,
        "restart_command": RESTART_COMMAND,
    }


@router.get("/ui-settings")
def ui_settings(db: Session = Depends(get_db)):
    return {
        "ui_timezone": effective_ui_timezone(db),
        "default_ui_timezone": DEFAULT_UI_TIMEZONE,
    }


@router.post("/admin/settings")
def update_admin_settings(
    payload: UpdateSettingsPayload,
    request: Request,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        public_origin = validate_public_registry_origin(payload.public_registry_origin, app_env=settings.app_env)
        ui_timezone = validate_ui_timezone(payload.ui_timezone)
        repository_tags_page_size = validate_default_page_size(payload.repository_tags_page_size)
        audit_log_retention_days = validate_audit_log_retention_days(payload.audit_log_retention_days)
        automatic_rebuild = bool(payload.automatic_registry_state_rebuild)
        storage_interval = validate_storage_usage_refresh_interval_seconds(
            payload.storage_usage_refresh_interval_seconds
        )
        previous_public_origin = effective_public_registry_origin(db, settings)
        set_app_setting(db, PUBLIC_REGISTRY_ORIGIN_KEY, public_origin)
        set_app_setting(db, UI_TIMEZONE_KEY, ui_timezone)
        set_app_setting(db, REPOSITORY_TAGS_PAGE_SIZE_KEY, str(repository_tags_page_size))
        set_app_setting(db, AUDIT_LOG_RETENTION_DAYS_KEY, str(audit_log_retention_days))
        set_app_setting(db, AUTOMATIC_REGISTRY_STATE_REBUILD_KEY, "true" if automatic_rebuild else "false")
        set_app_setting(db, STORAGE_USAGE_REFRESH_INTERVAL_SECONDS_KEY, str(storage_interval))
        db.commit()
        registry_restart_required = public_origin != previous_public_origin
        if registry_restart_required:
            render_registry_config_to_path(settings, public_registry_origin=public_origin)
    except SetupError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    request.app.state.public_registry_origin = public_origin
    record_audit_event(
        db,
        actor=csrf_user,
        action="app_settings_updated",
        target_type="app_setting",
        metadata_json={
            "public_registry_origin": public_origin,
            "ui_timezone": ui_timezone,
            "repository_tags_page_size": repository_tags_page_size,
            "audit_log_retention_days": audit_log_retention_days,
            "automatic_registry_state_rebuild": automatic_rebuild,
            "storage_usage_refresh_interval_seconds": storage_interval,
        },
    )
    return {
        "settings": {
            "public_registry_origin": public_origin,
            "ui_timezone": ui_timezone,
            "repository_tags_page_size": repository_tags_page_size,
            "audit_log_retention_days": audit_log_retention_days,
            "automatic_registry_state_rebuild": automatic_rebuild,
            "storage_usage_refresh_interval_seconds": storage_interval,
        },
        "registry_restart_required": registry_restart_required,
        "restart_command": RESTART_COMMAND if registry_restart_required else None,
    }


@router.get("/admin/maintenance")
def maintenance_summary(
    page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
):
    summary = maintenance.maintenance_summary(db, page=page, page_size=effective_default_page_size(db))
    cache_stats = _cached_manifest_summary_stats(db)
    state_stats = registry_state_stats(db)
    rebuild_jobs = db.scalars(
        select(RegistryStateRebuildJob)
        .order_by(RegistryStateRebuildJob.created_at.desc())
        .limit(5)
    ).all()
    return {
        "registry_status": summary["registry_status"],
        "registry_gate_enabled": summary["registry_status"] == "maintenance",
        "storage_usage_bytes": summary["storage_usage_bytes"],
        "storage_usage_measured_at": _serialize_optional_datetime(summary["storage_usage_measured_at"]),
        "storage_usage_stale": summary["storage_usage_stale"],
        "cache": cache_stats,
        "registry_state": {
            "active_repositories": state_stats["active_repositories"],
            "active_tags": state_stats["active_tags"],
            "inbox_queued": state_stats["inbox_queued"],
            "inbox_failed": state_stats["inbox_failed"],
            "last_rebuild": _serialize_registry_state_rebuild_job(
                state_stats["last_rebuild"],
                include_log_output=False,
            ) if state_stats["last_rebuild"] else None,
        },
        "log_retention_days": summary["log_retention_days"],
        "active_job": _serialize_gc_job(summary["active_job"], include_log_output=False) if summary["active_job"] else None,
        "last_job": _serialize_gc_job(summary["last_job"], include_log_output=False) if summary["last_job"] else None,
        "jobs": [_serialize_gc_job(job, include_log_output=False) for job in summary["jobs"]],
        "rebuild_jobs": [
            _serialize_registry_state_rebuild_job(job, include_log_output=False)
            for job in rebuild_jobs
        ],
        "pagination": summary["pagination"],
    }


@router.get("/internal/registry-maintenance")
def internal_registry_maintenance_gate(
    db: Session = Depends(get_db),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
):
    if maintenance.registry_gate_enabled(db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registry maintenance in progress.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/internal/registry-events", status_code=status.HTTP_202_ACCEPTED)
def ingest_registry_events(
    payload: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    _require_registry_notification_auth(request)
    events = _normalize_registry_notification_events(payload)
    if events:
        rows = create_registry_event_rows(db, events)
        mark_storage_usage_snapshot_stale(db)
        db.commit()
        for row in rows:
            background_tasks.add_task(
                process_registry_event_inbox_entry,
                request.app.state.session_factory,
                request.app.state.registry_client_factory,
                request.app.state.settings,
                row.id,
            )
    else:
        rows = []
    return {"accepted": len(rows)}


@router.post("/admin/maintenance/cache/rebuild")
def create_registry_state_rebuild(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    try:
        job = create_rebuild_job(
            db,
            actor=user,
            retention_days=effective_audit_log_retention_days(
                db,
                fallback_days=request.app.state.settings.log_retention_days,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if request.app.state.maintenance_auto_run:
        background_tasks.add_task(
            run_registry_state_rebuild_job,
            request.app.state.session_factory,
            request.app.state.registry_client_factory,
            request.app.state.settings,
            job.id,
        )

    return {"job": _serialize_registry_state_rebuild_job(job)}


@router.get("/admin/maintenance/cache/rebuild/{job_id}/log")
def registry_state_rebuild_job_log(
    job_id: int,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    job = db.get(RegistryStateRebuildJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registry state rebuild job not found.")
    return {"job": _serialize_registry_state_rebuild_job(job)}


@router.get("/admin/maintenance/inbox")
def registry_event_inbox(
    status_filter: Optional[str] = None,
    page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    valid_statuses = {"pending", "processing", "processed", "failed", "reconciled"}
    normalized_status_filter = None if status_filter in {None, "", "all"} else status_filter
    if normalized_status_filter and normalized_status_filter not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported inbox status filter.")

    page_size = effective_default_page_size(db)
    safe_page = max(page, 1)
    query = select(RegistryEventInbox)
    if normalized_status_filter:
        query = query.where(RegistryEventInbox.status == normalized_status_filter)
    query = query.order_by(RegistryEventInbox.received_at.desc(), RegistryEventInbox.id.desc())
    total_rows = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((safe_page - 1) * page_size).limit(page_size)).all()

    status_counts = dict(
        db.execute(
            select(RegistryEventInbox.status, func.count(RegistryEventInbox.id))
            .group_by(RegistryEventInbox.status)
        ).all()
    )
    return {
        "entries": [_serialize_registry_event_inbox_entry(row) for row in rows],
        "status_counts": {entry_status: int(status_counts.get(entry_status, 0)) for entry_status in sorted(valid_statuses)},
        "status_filter": normalized_status_filter,
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": total_rows,
            "has_previous": safe_page > 1,
            "has_next": safe_page * page_size < total_rows,
        },
    }


@router.post("/admin/maintenance/inbox/{event_id}/retry")
def retry_registry_event_inbox_entry(
    event_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    row = db.get(RegistryEventInbox, event_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Registry inbox entry not found.")
    if row.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed inbox entries can be retried.")

    row.status = "pending"
    row.error = None
    row.processed_at = None
    db.commit()
    record_audit_event(
        db,
        actor=user,
        action="registry_event_inbox_retry_requested",
        target_type="registry_event_inbox",
        target_id=row.id,
        metadata_json={
            "repo": row.repository_name,
            "action": row.action,
            "tag": row.tag,
            "digest": row.digest,
        },
        retention_days=effective_audit_log_retention_days(
            db,
            fallback_days=request.app.state.settings.log_retention_days,
        ),
    )
    background_tasks.add_task(
        process_registry_event_inbox_entry,
        request.app.state.session_factory,
        request.app.state.registry_client_factory,
        request.app.state.settings,
        row.id,
    )
    return {"entry": _serialize_registry_event_inbox_entry(row)}


@router.get("/admin/audit")
def audit_log(
    actor: Optional[str] = None,
    repo: Optional[str] = None,
    page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    safe_page = max(page, 1)
    page_size = effective_default_page_size(db)
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc())

    if actor:
        actor_user_ids = db.scalars(
            select(User.id).where(or_(User.username == actor, User.deleted_username == actor))
        ).all()
        if not actor_user_ids:
            return {
                "events": [],
                "pagination": {
                    "page": safe_page,
                    "page_size": page_size,
                    "total": 0,
                    "has_prev": safe_page > 1,
                    "has_next": False,
                },
            }
        query = query.where(
            AuditEvent.actor_type == "user",
            AuditEvent.actor_id.in_(actor_user_ids),
        )
    if repo:
        repo_pattern = f'%"{repo}"%'
        query = query.where(
            AuditEvent.metadata_json.is_not(None),
            AuditEvent.metadata_json.cast(String).like(repo_pattern),
        )

    total_events = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    events = db.scalars(query.offset((safe_page - 1) * page_size).limit(page_size)).all()

    actor_names: dict[int, str] = {}
    actor_ids = sorted({event.actor_id for event in events if event.actor_type == "user" and event.actor_id is not None})
    if actor_ids:
        users = db.scalars(select(User).where(User.id.in_(actor_ids))).all()
        actor_names = {user.id: _user_audit_label(user) for user in users}

    return {
        "events": [
            _serialize_audit_event(
                event,
                actor_names.get(event.actor_id) if event.actor_type == "user" and event.actor_id is not None else event.actor_type,
            )
            for event in events
        ],
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": total_events,
            "has_prev": safe_page > 1,
            "has_next": safe_page * page_size < total_events,
        },
    }


@router.post("/admin/maintenance/jobs")
def create_maintenance_job(
    payload: CreateGcJobPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
):
    try:
        job = maintenance.create_job(
            db,
            actor=user,
            dry_run=payload.dry_run,
            delete_untagged=payload.delete_untagged,
            prune_empty_dirs=payload.prune_empty_dirs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    if request.app.state.maintenance_auto_run:
        background_tasks.add_task(maintenance.run_job, job.id)

    return {"job": _serialize_gc_job(job)}


@router.get("/admin/maintenance/jobs/{job_id}/log")
def maintenance_job_log(
    job_id: int,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    job = db.get(GcJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance job not found.")
    return {"job": _serialize_gc_job(job)}


@router.post("/admin/maintenance/logs/prune")
def prune_maintenance_logs(
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
):
    counts = maintenance.prune_logs(db, actor=user)
    return {
        "retention_days": maintenance.log_retention_days(db),
        "pruned": counts,
    }


@router.get("/repos")
def list_repositories(
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    page: int = 1,
):
    safe_page = max(page, 1)
    page_size = effective_default_page_size(db)
    visible_condition = _visible_repository_condition(user)
    visible_repositories_query = (
        select(Repository)
        .join(RepositoryTag)
        .where(
            Repository.deleted_at.is_(None),
            RepositoryTag.deleted_at.is_(None),
        )
        .distinct()
    )
    if visible_condition is not None:
        visible_repositories_query = visible_repositories_query.where(visible_condition)
    total_visible = db.scalar(
        select(func.count()).select_from(visible_repositories_query.subquery())
    ) or 0
    page_start = (safe_page - 1) * page_size
    page_end = page_start + page_size
    repository_rows = db.scalars(
        visible_repositories_query.order_by(Repository.name.asc()).offset(page_start).limit(page_size)
    ).all()
    payload = {
        "repos": [
            {"name": repository.name, "visibility": repository.visibility}
            for repository in repository_rows
        ],
        "truncation": {"truncated": False, "pages_fetched": 0, "returned": len(repository_rows)},
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": total_visible,
            "has_prev": safe_page > 1,
            "has_next": page_end < total_visible,
        },
        "user": _serialize_user(user),
    }
    return payload


@router.get("/repos/{repo_name:path}/tags")
def list_repository_tags(
    repo_name: str,
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    page: int = 1,
    sort: str = "created",
    direction: str = "desc",
):
    safe_page = max(page, 1)
    safe_sort = sort.lower()
    safe_direction = direction.lower()
    if safe_sort not in {"created", "tag"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported tag sort.")
    if safe_direction not in {"asc", "desc"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported tag sort direction.")

    page_size = effective_default_page_size(db)
    repository = _get_active_repository(db, repository_name=repo_name)
    if not can_access_repository(db, repository_name=repo_name, action="pull", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pull access required.")

    can_delete_tag = can_access_repository(db, repository_name=repo_name, action="delete", **_subject_for_user(user))
    can_prune_repository = user.is_admin
    total_tags = db.scalar(
        select(func.count(RepositoryTag.id)).where(
            RepositoryTag.repository_id == repository.id,
            RepositoryTag.deleted_at.is_(None),
        )
    ) or 0
    page_start = (safe_page - 1) * page_size
    page_end = page_start + page_size
    if safe_sort == "tag":
        sort_order = (
            RepositoryTag.name.asc() if safe_direction == "asc" else RepositoryTag.name.desc(),
            RepositoryTag.pushed_at.is_(None),
            RepositoryTag.pushed_at.desc(),
        )
    else:
        sort_order = (
            CachedManifestSummary.created_at.is_(None),
            CachedManifestSummary.created_at.asc() if safe_direction == "asc" else CachedManifestSummary.created_at.desc(),
            RepositoryTag.pushed_at.is_(None),
            RepositoryTag.pushed_at.asc() if safe_direction == "asc" else RepositoryTag.pushed_at.desc(),
            RepositoryTag.name.asc(),
        )
    tag_rows = db.scalars(
        select(RepositoryTag)
        .outerjoin(
            CachedManifestSummary,
            and_(
                CachedManifestSummary.repository_name == repo_name,
                CachedManifestSummary.manifest_digest == RepositoryTag.manifest_digest,
            ),
        )
        .where(
            RepositoryTag.repository_id == repository.id,
            RepositoryTag.deleted_at.is_(None),
        )
        .order_by(*sort_order)
        .offset(page_start)
        .limit(page_size)
    ).all()

    digests = sorted({tag.manifest_digest for tag in tag_rows if tag.manifest_digest})
    cache_rows_by_digest: dict[str, CachedManifestSummary] = {}
    if digests:
        cached_rows = db.scalars(
            select(CachedManifestSummary).where(
                CachedManifestSummary.repository_name == repo_name,
                CachedManifestSummary.manifest_digest.in_(digests),
            )
        ).all()
        cache_rows_by_digest = {row.manifest_digest: row for row in cached_rows}
    shared_manifest_metadata = _shared_manifest_tag_metadata_by_digest(
        db,
        repository_id=repository.id,
        manifest_digests=digests,
    )

    tags: list[TagSummary] = []
    for tag_row in tag_rows:
        cached_row = cache_rows_by_digest.get(tag_row.manifest_digest)
        if cached_row is not None:
            tags.append(_build_tag_summary_from_cache(cached_row, tag=tag_row.name))
            continue
        tags.append(
            TagSummary(
                tag=tag_row.name,
                digest=tag_row.manifest_digest,
                media_type=tag_row.media_type,
                total_size=0,
                architectures=[],
                created_at=None,
                history_count=None,
                children_truncated=False,
                history_truncated=False,
            )
        )

    truncation = {
        "truncated": total_tags > page_size,
        "returned": len(tags),
        "available": int(total_tags),
    }

    return {
        "repo": repo_name,
        "visibility": repository.visibility,
        "public_registry_origin": effective_public_registry_origin(db, settings),
        "can_manage_visibility": user.is_admin,
        "can_delete_tag": can_delete_tag,
        "can_prune_repository": can_prune_repository,
        "tags": [
            _serialize_tag_summary(
                tag,
                shared_manifest_metadata=shared_manifest_metadata.get(tag.digest),
            )
            for tag in tags
        ],
        "truncation": truncation,
        "sorting": {
            "sort": safe_sort,
            "direction": safe_direction,
        },
        "pagination": {
            "page": safe_page,
            "page_size": page_size,
            "total": int(total_tags),
            "has_prev": safe_page > 1,
            "has_next": page_end < total_tags,
        },
    }


@router.get("/repos/{repo_name:path}/tags/{tag}")
def get_repository_tag_details(
    repo_name: str,
    tag: str,
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    repository = _get_active_repository(db, repository_name=repo_name)
    if not can_access_repository(db, repository_name=repo_name, action="pull", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pull access required.")
    _get_active_repository_tag(db, repository=repository, tag_name=tag)

    can_delete_tag = can_access_repository(db, repository_name=repo_name, action="delete", **_subject_for_user(user))

    try:
        manifest = registry.get_manifest_details(
            repo_name,
            tag,
            max_manifest_children=settings.manifest_children_max_items,
            max_history_entries=settings.history_entries_max_items,
        )
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository tag not found.") from exc
    finally:
        registry.close()

    return {
        "manifest": _serialize_manifest(
            manifest,
            shared_manifest_metadata=_shared_manifest_tag_metadata(
                db,
                repository_id=repository.id,
                manifest_digest=manifest.digest,
            ),
        ),
        "public_registry_origin": effective_public_registry_origin(db, settings),
        "can_delete_tag": can_delete_tag,
    }


@router.get("/repos/{repo_name:path}/tags/{tag}/history")
def get_repository_tag_history(
    repo_name: str,
    tag: str,
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    repository = _get_active_repository(db, repository_name=repo_name)
    if not can_access_repository(db, repository_name=repo_name, action="pull", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pull access required.")
    _get_active_repository_tag(db, repository=repository, tag_name=tag)

    try:
        variants, truncation = registry.get_tag_history_bounded(
            repo_name,
            tag,
            max_manifest_children=settings.manifest_children_max_items,
            max_history_entries=settings.history_entries_max_items,
        )
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository tag history not found.") from exc
    finally:
        registry.close()

    return {
        "repo": repo_name,
        "tag": tag,
        "variants": [_serialize_history_variant(variant) for variant in variants],
        "truncation": truncation,
    }


@router.post("/repos/{repo_name:path}/tags/delete")
def delete_repository_tags(
    repo_name: str,
    payload: DeleteTagsPayload,
    request: Request,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    repository = _get_active_repository(db, repository_name=repo_name)

    if not can_access_repository(db, repository_name=repo_name, action="delete", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Delete access required.")

    active_tags = db.scalars(
        select(RepositoryTag.name).where(
            RepositoryTag.repository_id == repository.id,
            RepositoryTag.name.in_(payload.tags),
            RepositoryTag.deleted_at.is_(None),
        )
    ).all()
    active_tag_set = set(active_tags)
    missing_tags = [tag for tag in payload.tags if tag not in active_tag_set]
    if missing_tags:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository tag not found.")

    manifests_by_tag: dict[str, ManifestDetails] = {}
    try:
        for tag in payload.tags:
            manifest = registry.get_manifest_details(repo_name, tag)
            if not manifest.digest:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Manifest digest unavailable.")
            manifests_by_tag[tag] = manifest

        deleted_digests: set[str] = set()
        for manifest in manifests_by_tag.values():
            if manifest.digest in deleted_digests:
                continue
            registry.delete_manifest(repo_name, manifest.digest)
            deleted_digests.add(manifest.digest)
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository tag not found.") from exc
    finally:
        registry.close()

    deleted_tags = []
    for tag, manifest in manifests_by_tag.items():
        record_audit_event(
            db,
            actor=user,
            action="repository_tag_deleted",
            target_type="repository_tag",
            metadata_json={"repo": repo_name, "tag": tag, "digest": manifest.digest},
        )
        mark_repository_tag_deleted(
            db,
            repository_name=repo_name,
            tag_name=tag,
            manifest_digest=manifest.digest,
        )
        deleted_tags.append({"tag": tag, "digest": manifest.digest})
    mark_storage_usage_snapshot_stale(db)
    db.commit()
    return {"ok": True, "repo": repo_name, "deleted": deleted_tags, "count": len(deleted_tags)}


@router.post("/repos/{repo_name:path}/tags/{tag}/delete")
def delete_repository_tag(
    repo_name: str,
    tag: str,
    payload: DeleteTagPayload,
    request: Request,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    expected = f"{repo_name}:{tag}"
    if payload.confirmation != expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation text mismatch.")
    repository = _get_active_repository(db, repository_name=repo_name)
    if not can_access_repository(db, repository_name=repo_name, action="delete", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Delete access required.")
    _get_active_repository_tag(db, repository=repository, tag_name=tag)

    try:
        manifest = registry.get_manifest_details(repo_name, tag)
        if not manifest.digest:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Manifest digest unavailable.")
        registry.delete_manifest(repo_name, manifest.digest)
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository tag not found.") from exc
    finally:
        registry.close()

    record_audit_event(
        db,
        actor=user,
        action="repository_tag_deleted",
        target_type="repository_tag",
        metadata_json={"repo": repo_name, "tag": tag, "digest": manifest.digest},
    )
    mark_repository_tag_deleted(
        db,
        repository_name=repo_name,
        tag_name=tag,
        manifest_digest=manifest.digest,
    )
    mark_storage_usage_snapshot_stale(db)
    db.commit()
    return {"ok": True, "repo": repo_name, "tag": tag, "digest": manifest.digest}


@router.post("/repos/{repo_name:path}/delete")
def delete_empty_repository(
    repo_name: str,
    payload: DeleteRepositoryPayload,
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if payload.confirmation != repo_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation text mismatch.")
    repo_path = _repository_storage_path(settings, repo_name)
    repository = db.scalar(
        select(Repository).where(
            Repository.name == repo_name,
            Repository.deleted_at.is_(None),
        )
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    active_tags = db.scalar(
        select(func.count(RepositoryTag.id)).where(
            RepositoryTag.repository_id == repository.id,
            RepositoryTag.deleted_at.is_(None),
        )
    ) or 0
    if active_tags:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository must be empty before deletion.")

    removed = False
    if repo_path.exists():
        shutil.rmtree(repo_path)
        removed = True

    record_audit_event(
        db,
        actor=user,
        action="repository_storage_pruned",
        target_type="repository",
        metadata_json={"repo": repo_name, "removed": removed},
    )
    mark_repository_deleted(db, repository_name=repo_name)
    mark_storage_usage_snapshot_stale(db)
    db.commit()
    return {"ok": True, "repo": repo_name, "removed": removed}
