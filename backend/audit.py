from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.log_retention import prune_expired_logs
from backend.models import AuditEvent, User
from backend.setup import effective_audit_log_retention_days


def record_audit_event(
    session: Session,
    *,
    action: str,
    actor: Optional[User] = None,
    actor_type: Optional[str] = None,
    actor_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    metadata_json: Optional[dict] = None,
    retention_days: Optional[int] = None,
) -> None:
    resolved_actor_type = actor_type
    resolved_actor_id = actor_id
    if actor is not None:
        resolved_actor_type = "user"
        resolved_actor_id = actor.id

    prune_expired_logs(
        session,
        retention_days=effective_audit_log_retention_days(session, fallback_days=retention_days or 30),
    )

    session.add(
        AuditEvent(
            actor_type=resolved_actor_type or "system",
            actor_id=resolved_actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_json=metadata_json,
        )
    )
    session.commit()
