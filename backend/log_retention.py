from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from backend.models import AuditEvent, GcJob


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
