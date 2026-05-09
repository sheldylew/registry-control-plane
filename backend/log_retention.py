from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from backend.models import AuditEvent, GcJob, PersonalAccessToken, RobotToken, WebSession


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def prune_expired_logs(
    session: Session,
    *,
    retention_days: int,
    now: datetime | None = None,
) -> dict[str, int]:
    cutoff = (now or utcnow()) - timedelta(days=retention_days)

    audit_events_deleted = session.execute(
        delete(AuditEvent).where(AuditEvent.created_at < cutoff),
        execution_options={"synchronize_session": False},
    ).rowcount or 0
    gc_jobs_deleted = session.execute(
        delete(GcJob).where(
            GcJob.status.in_(("succeeded", "failed")),
            or_(
                GcJob.finished_at < cutoff,
                GcJob.created_at < cutoff,
            ),
        )
        ,
        execution_options={"synchronize_session": False},
    ).rowcount or 0
    session.commit()
    return {
        "audit_events_deleted": audit_events_deleted,
        "gc_jobs_deleted": gc_jobs_deleted,
    }


def prune_expired_operational_records(
    session: Session,
    *,
    web_session_retention_days: int,
    token_record_retention_days: int,
    now: datetime | None = None,
) -> dict[str, int]:
    effective_now = now or utcnow()
    session_cutoff = effective_now - timedelta(days=web_session_retention_days)
    token_cutoff = effective_now - timedelta(days=token_record_retention_days)

    web_sessions_deleted = session.execute(
        delete(WebSession).where(
            or_(
                WebSession.revoked_at < session_cutoff,
                WebSession.expires_at < session_cutoff,
            ),
        ),
        execution_options={"synchronize_session": False},
    ).rowcount or 0
    personal_access_tokens_deleted = session.execute(
        delete(PersonalAccessToken).where(
            or_(
                PersonalAccessToken.revoked_at < token_cutoff,
                PersonalAccessToken.expires_at < token_cutoff,
            ),
        ),
        execution_options={"synchronize_session": False},
    ).rowcount or 0
    robot_tokens_deleted = session.execute(
        delete(RobotToken).where(
            or_(
                RobotToken.revoked_at < token_cutoff,
                RobotToken.expires_at < token_cutoff,
            ),
        ),
        execution_options={"synchronize_session": False},
    ).rowcount or 0
    session.commit()
    return {
        "web_sessions_deleted": web_sessions_deleted,
        "personal_access_tokens_deleted": personal_access_tokens_deleted,
        "robot_tokens_deleted": robot_tokens_deleted,
    }
