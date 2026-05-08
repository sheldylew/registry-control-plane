import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy.orm import Session

from backend.models import PersonalAccessToken, RobotAccount, RobotToken, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _new_token_parts(marker: str) -> tuple[str, str, str]:
    prefix = secrets.token_hex(4)
    secret = secrets.token_hex(16)
    raw_token = f"{marker}_{prefix}.{secret}"
    return prefix, secret, raw_token


def _token_is_active(token: Union[PersonalAccessToken, RobotToken], now: Optional[datetime] = None) -> bool:
    effective_now = _as_utc(now) if now is not None else utcnow()
    if token.revoked_at is not None:
        return False
    if token.expires_at is not None and _as_utc(token.expires_at) <= effective_now:
        return False
    return True


def _extract_prefix(raw_token: str, marker: str) -> Optional[str]:
    expected_prefix = f"{marker}_"
    if not raw_token.startswith(expected_prefix):
        return None

    remainder = raw_token[len(expected_prefix) :]
    token_prefix, separator, _secret = remainder.partition(".")
    if separator != "." or not token_prefix:
        return None
    return token_prefix


@dataclass(frozen=True)
class IssuedToken:
    raw_token: str
    token_prefix: str


def issue_personal_access_token(
    session: Session,
    *,
    user_id: int,
    name: str,
    expires_at: Optional[datetime] = None,
) -> IssuedToken:
    token_prefix, _secret, raw_token = _new_token_parts("rcr_pat")
    token = PersonalAccessToken(
        user_id=user_id,
        name=name,
        token_hash=_hash_token(raw_token),
        token_prefix=token_prefix,
        expires_at=expires_at,
    )
    session.add(token)
    session.flush()
    return IssuedToken(raw_token=raw_token, token_prefix=token_prefix)


def issue_robot_token(
    session: Session,
    *,
    robot_id: int,
    name: str,
    expires_at: Optional[datetime] = None,
) -> IssuedToken:
    token_prefix, _secret, raw_token = _new_token_parts("rcr_robot")
    token = RobotToken(
        robot_id=robot_id,
        name=name,
        token_hash=_hash_token(raw_token),
        token_prefix=token_prefix,
        expires_at=expires_at,
    )
    session.add(token)
    session.flush()
    return IssuedToken(raw_token=raw_token, token_prefix=token_prefix)


def authenticate_personal_access_token(
    session: Session,
    raw_token: str,
    *,
    now: Optional[datetime] = None,
) -> Optional[PersonalAccessToken]:
    token_prefix = _extract_prefix(raw_token, "rcr_pat")
    if token_prefix is None:
        return None

    token = session.query(PersonalAccessToken).filter(PersonalAccessToken.token_prefix == token_prefix).one_or_none()
    if token is None:
        return None

    raw_hash = _hash_token(raw_token)
    if not hmac.compare_digest(token.token_hash, raw_hash):
        return None
    if not _token_is_active(token, now=now):
        return None
    return token


def authenticate_robot_token(
    session: Session,
    raw_token: str,
    *,
    now: Optional[datetime] = None,
) -> Optional[RobotToken]:
    token_prefix = _extract_prefix(raw_token, "rcr_robot")
    if token_prefix is None:
        return None

    token = session.query(RobotToken).filter(RobotToken.token_prefix == token_prefix).one_or_none()
    if token is None:
        return None

    raw_hash = _hash_token(raw_token)
    if not hmac.compare_digest(token.token_hash, raw_hash):
        return None
    if not _token_is_active(token, now=now):
        return None

    robot = session.get(RobotAccount, token.robot_id)
    if robot is None or not robot.is_active:
        return None
    return token


def authenticate_user_pat(
    session: Session,
    *,
    username: str,
    raw_token: str,
    now: Optional[datetime] = None,
) -> Optional[tuple[User, PersonalAccessToken]]:
    token = authenticate_personal_access_token(session, raw_token, now=now)
    if token is None:
        return None

    user = session.get(User, token.user_id)
    if user is None or not user.is_active or user.username != username:
        return None
    return user, token


def authenticate_named_robot_token(
    session: Session,
    *,
    robot_name: str,
    raw_token: str,
    now: Optional[datetime] = None,
) -> Optional[tuple[RobotAccount, RobotToken]]:
    token = authenticate_robot_token(session, raw_token, now=now)
    if token is None:
        return None

    robot = session.get(RobotAccount, token.robot_id)
    if robot is None or not robot.is_active or robot.name != robot_name:
        return None
    return robot, token
