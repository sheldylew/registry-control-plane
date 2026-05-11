from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth.passwords import hash_password
from backend.config import Settings
from backend.models import AppSetting, User
from backend.registry_config import render_registry_config
from backend.runtime_secrets import ensure_registry_notifications_token


PUBLIC_REGISTRY_ORIGIN_KEY = "public_registry_origin"
UI_TIMEZONE_KEY = "ui_timezone"
AUTOMATIC_REGISTRY_STATE_REBUILD_KEY = "automatic_registry_state_rebuild"
STORAGE_USAGE_REFRESH_INTERVAL_SECONDS_KEY = "storage_usage_refresh_interval_seconds"
REGISTRY_STORAGE_USAGE_BYTES_KEY = "registry_storage_usage_bytes"
REGISTRY_STORAGE_USAGE_MEASURED_AT_KEY = "registry_storage_usage_measured_at"
REGISTRY_STORAGE_USAGE_STALE_KEY = "registry_storage_usage_stale"
DEFAULT_UI_TIMEZONE = "America/Los_Angeles"
DEFAULT_STORAGE_USAGE_REFRESH_INTERVAL_SECONDS = 3600
RESTART_COMMAND = "docker compose restart registry"
REGISTRY_EVENTS_PATH = "/api/internal/registry-events"


class SetupError(ValueError):
    pass


@dataclass(frozen=True)
class SetupStatus:
    setup_required: bool
    public_registry_origin: Optional[str]
    env_bootstrap_available: bool
    env_bootstrap_partial: bool
    registry_restart_required: bool = False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _token_file(path: str) -> Path:
    return Path(path)


def _setting(session: Session, key: str) -> Optional[AppSetting]:
    return session.get(AppSetting, key)


def get_app_setting(session: Session, key: str) -> Optional[str]:
    setting = _setting(session, key)
    return setting.value if setting is not None else None


def set_app_setting(session: Session, key: str, value: str) -> AppSetting:
    setting = _setting(session, key)
    if setting is None:
        setting = AppSetting(key=key, value=value, updated_at=utcnow())
        session.add(setting)
    else:
        setting.value = value
        setting.updated_at = utcnow()
    session.flush()
    return setting


def admin_exists(session: Session) -> bool:
    return session.scalar(select(User.id).where(User.is_admin.is_(True)).limit(1)) is not None


def saved_public_registry_origin(session: Session) -> Optional[str]:
    return get_app_setting(session, PUBLIC_REGISTRY_ORIGIN_KEY)


def effective_public_registry_origin(session: Session, settings: Settings) -> str:
    return saved_public_registry_origin(session) or settings.public_registry_origin


def saved_ui_timezone(session: Session) -> Optional[str]:
    return get_app_setting(session, UI_TIMEZONE_KEY)


def effective_ui_timezone(session: Session) -> str:
    return saved_ui_timezone(session) or DEFAULT_UI_TIMEZONE


def automatic_registry_state_rebuild_enabled(session: Session) -> bool:
    value = get_app_setting(session, AUTOMATIC_REGISTRY_STATE_REBUILD_KEY)
    return value is not None and value.strip().casefold() in {"1", "true", "yes", "on"}


def validate_storage_usage_refresh_interval_seconds(value: int) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError) as exc:
        raise SetupError("Storage usage refresh interval must be a whole number of seconds.") from exc
    if interval < 0 or interval > 86400:
        raise SetupError("Storage usage refresh interval must be between 0 and 86400 seconds.")
    return interval


def effective_storage_usage_refresh_interval_seconds(session: Session) -> int:
    value = get_app_setting(session, STORAGE_USAGE_REFRESH_INTERVAL_SECONDS_KEY)
    if value is None:
        return DEFAULT_STORAGE_USAGE_REFRESH_INTERVAL_SECONDS
    try:
        return validate_storage_usage_refresh_interval_seconds(int(value.strip()))
    except (SetupError, ValueError):
        return DEFAULT_STORAGE_USAGE_REFRESH_INTERVAL_SECONDS


def env_bootstrap_values(settings: Settings) -> dict[str, Optional[str]]:
    return {
        "admin_username": settings.admin_username,
        "admin_password": settings.admin_password,
        "admin_email": settings.admin_email,
        "public_registry_origin": settings.public_registry_origin,
    }


def env_bootstrap_available(settings: Settings) -> bool:
    values = env_bootstrap_values(settings).values()
    return all(value is not None and value.strip() for value in values)


def env_bootstrap_partial(settings: Settings) -> bool:
    values = [value is not None and value.strip() for value in env_bootstrap_values(settings).values()]
    return any(values) and not all(values)


def validate_public_registry_origin(origin: str, *, app_env: str) -> str:
    normalized = origin.strip().rstrip("/")
    if not normalized:
        raise SetupError("Public registry origin is required.")

    parts = urlsplit(normalized)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.path or parts.query or parts.fragment:
        raise SetupError("Public registry origin must be an origin like https://registry.example.com.")

    if app_env == "production" and parts.scheme != "https":
        raise SetupError("Public registry origin must use https:// in production.")

    if app_env != "production" and parts.scheme == "http":
        localhost_hosts = {"localhost", "127.0.0.1", "[::1]"}
        hostname = parts.hostname or ""
        if hostname not in localhost_hosts:
            raise SetupError("HTTP public registry origin is allowed only for localhost development.")

    return normalized


def validate_ui_timezone(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SetupError("UI timezone is required.")
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise SetupError("UI timezone must be a valid IANA timezone like America/Los_Angeles.") from exc
    return normalized


def setup_required(session: Session) -> bool:
    return not admin_exists(session) or not saved_public_registry_origin(session)


def setup_status(session: Session, settings: Settings) -> SetupStatus:
    origin = saved_public_registry_origin(session)
    return SetupStatus(
        setup_required=not admin_exists(session) or not origin,
        public_registry_origin=origin,
        env_bootstrap_available=env_bootstrap_available(settings),
        env_bootstrap_partial=env_bootstrap_partial(settings),
    )


def ensure_setup_token(settings: Settings, *, setup_is_required: bool) -> Optional[str]:
    token_path = _token_file(settings.setup_token_path)
    if not setup_is_required:
        if token_path.exists():
            token_path.unlink()
        return None

    if token_path.exists():
        return None

    raw_token = secrets.token_urlsafe(32)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(
        json.dumps({"token_hash": _hash_token(raw_token), "created_at": utcnow().isoformat()}) + "\n",
        encoding="utf-8",
    )
    os.chmod(token_path, 0o600)
    return raw_token


def verify_setup_token(settings: Settings, raw_token: str) -> bool:
    token_path = _token_file(settings.setup_token_path)
    if not token_path.exists():
        return False

    try:
        payload = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    token_hash = payload.get("token_hash")
    if not isinstance(token_hash, str):
        return False
    return hmac.compare_digest(token_hash, _hash_token(raw_token))


def invalidate_setup_token(settings: Settings) -> None:
    token_path = _token_file(settings.setup_token_path)
    if token_path.exists():
        token_path.unlink()


def write_setup_complete_marker(settings: Settings) -> None:
    marker = Path(settings.setup_complete_marker_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("complete\n", encoding="utf-8")
    os.chmod(marker, 0o644)


def render_registry_config_to_path(settings: Settings, *, public_registry_origin: str) -> None:
    template_path = Path(settings.registry_config_template_path)
    rendered_path = Path(settings.registry_rendered_config_path)
    template = template_path.read_text(encoding="utf-8")
    registry_notifications_token = ensure_registry_notifications_token(settings)
    rendered = render_registry_config(
        template,
        settings=settings,
        public_registry_origin=public_registry_origin,
        registry_notifications_token=registry_notifications_token,
    )
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(rendered, encoding="utf-8")
    os.chmod(rendered_path, 0o644)


def complete_setup(
    session: Session,
    settings: Settings,
    *,
    admin_username: str,
    admin_email: str,
    admin_password: str,
    public_registry_origin: str,
) -> User:
    if not setup_required(session):
        raise SetupError("Setup has already been completed.")

    origin = validate_public_registry_origin(public_registry_origin, app_env=settings.app_env)
    user = session.scalar(select(User).where(User.is_admin.is_(True)).order_by(User.id.asc()).limit(1))
    if user is None:
        user = User(
            username=admin_username,
            email=admin_email,
            password_hash=hash_password(admin_password),
            is_admin=True,
            is_active=True,
        )
        session.add(user)
    set_app_setting(session, PUBLIC_REGISTRY_ORIGIN_KEY, origin)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise SetupError("An admin user with that username or email already exists.") from exc
    session.refresh(user)
    render_registry_config_to_path(settings, public_registry_origin=origin)
    invalidate_setup_token(settings)
    write_setup_complete_marker(settings)
    return user


def complete_setup_from_environment(session: Session, settings: Settings) -> Optional[User]:
    if not setup_required(session):
        return None
    if env_bootstrap_partial(settings):
        return None
    if not env_bootstrap_available(settings):
        return None

    return complete_setup(
        session,
        settings,
        admin_username=settings.admin_username or "",
        admin_email=settings.admin_email or "",
        admin_password=settings.admin_password or "",
        public_registry_origin=settings.public_registry_origin,
    )
