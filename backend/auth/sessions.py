import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models import User, WebSession


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedSession:
    raw_token: str
    csrf_token: str
    expires_at: datetime


def create_session(session: Session, *, user: User, settings: Settings) -> IssuedSession:
    raw_token = secrets.token_hex(32)
    csrf_token = secrets.token_hex(32)
    expires_at = utcnow() + timedelta(seconds=settings.session_lifetime_seconds)
    web_session = WebSession(
        user_id=user.id,
        session_hash=_hash_session_token(raw_token),
        csrf_token=csrf_token,
        expires_at=expires_at,
        last_seen_at=utcnow(),
    )
    session.add(web_session)
    session.commit()
    return IssuedSession(raw_token=raw_token, csrf_token=csrf_token, expires_at=expires_at)


def authenticate_session(session: Session, raw_token: str) -> Optional[Tuple[WebSession, User]]:
    raw_hash = _hash_session_token(raw_token)
    candidate = session.scalar(
        select(WebSession).where(
            WebSession.session_hash == raw_hash,
            WebSession.revoked_at.is_(None),
        )
    )
    if candidate is None:
        return None
    if _as_utc(candidate.expires_at) <= utcnow():
        return None
    user = session.get(User, candidate.user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    candidate.last_seen_at = utcnow()
    session.commit()
    return candidate, user


def revoke_session(session: Session, raw_token: str) -> None:
    raw_hash = _hash_session_token(raw_token)
    candidate = session.scalar(
        select(WebSession).where(
            WebSession.session_hash == raw_hash,
            WebSession.revoked_at.is_(None),
        )
    )
    if candidate is not None:
        candidate.revoked_at = utcnow()
        session.commit()


def revoke_user_sessions(session: Session, *, user_id: int) -> int:
    sessions = session.scalars(
        select(WebSession).where(
            WebSession.user_id == user_id,
            WebSession.revoked_at.is_(None),
        )
    ).all()
    revoked_at = utcnow()
    for web_session in sessions:
        web_session.revoked_at = revoked_at
    session.commit()
    return len(sessions)
