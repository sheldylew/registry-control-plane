from pathlib import Path
import shutil
from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import String, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.audit import record_audit_event
from backend.auth.passwords import hash_password, verify_password
from backend.auth.pats import authenticate_personal_access_token, issue_personal_access_token, issue_robot_token
from backend.auth.permissions import (
    can_access_repository,
    filter_visible_repositories,
    validate_repository_name,
    validate_repository_pattern,
)
from backend.auth.sessions import create_session, revoke_session, revoke_user_sessions
from backend.config import Settings
from backend.maintenance import MaintenanceService
from backend.metrics import increment as increment_metric
from backend.metrics import snapshot as metrics_snapshot
from backend.models import AuditEvent, GcJob, PersonalAccessToken, Repository, RepositoryPermission, RobotAccount, RobotToken, User
from backend.registry_client import HistoryVariant, ManifestDetails, RegistryClient, RegistryNotFoundError, TagSummary
from backend.setup import (
    RESTART_COMMAND,
    SetupError,
    complete_setup,
    effective_public_registry_origin,
    render_registry_config_to_path,
    saved_public_registry_origin,
    set_app_setting,
    setup_required,
    setup_status,
    validate_public_registry_origin,
    verify_setup_token,
    PUBLIC_REGISTRY_ORIGIN_KEY,
)


router = APIRouter(prefix="/api")

MAX_SHORT_TEXT_LENGTH = 255
MAX_EMAIL_LENGTH = 320
MAX_PASSWORD_LENGTH = 512
MAX_DESCRIPTION_LENGTH = 2000


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


def _serialize_manifest(details: ManifestDetails) -> dict:
    return {
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


def _serialize_tag_summary(summary: TagSummary) -> dict:
    return {
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


def _serialize_gc_job(job: GcJob) -> dict:
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
        "log_output": job.log_output,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
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
    if settings.app_env == "development":
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


def require_csrf(request: Request, user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)) -> User:
    submitted = request.headers.get("X-CSRF-Token")
    if not submitted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF token.")
    _validate_same_origin_request(request)
    web_session, _current_user = _get_authenticated_user(request, db)
    if web_session is None or web_session.csrf_token != submitted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
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

    @field_validator("public_registry_origin")
    @classmethod
    def validate_public_origin_text(cls, value: str) -> str:
        return _normalize_required_text(value, field_name="Public registry origin")


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
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
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
    user: User = Depends(require_csrf),
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
    page_size = 10
    base_query = select(User).order_by(User.username.asc())
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
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == csrf_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot disable your own account.",
        )
    user.is_active = False
    db.commit()
    return {"user": _serialize_user(user)}


@router.post("/admin/users/{user_id}/enable")
def enable_user(
    user_id: int,
    csrf_user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
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
    if user is None:
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


@router.get("/admin/tokens")
def list_tokens(user: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    tokens = db.scalars(
        select(PersonalAccessToken).where(PersonalAccessToken.user_id == user.id).order_by(PersonalAccessToken.created_at.desc())
    ).all()
    return {"tokens": [_serialize_token(token) for token in tokens]}


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


@router.get("/admin/permissions")
def list_permissions(_admin: User = Depends(require_admin_user), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.username.asc())).all()
    robots = db.scalars(select(RobotAccount).order_by(RobotAccount.name.asc())).all()
    permissions = db.scalars(
        select(RepositoryPermission).order_by(
            RepositoryPermission.subject_type.asc(),
            RepositoryPermission.subject_id.asc(),
            RepositoryPermission.repository_pattern.asc(),
        )
    ).all()
    user_names = {user.id: user.username for user in users}
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
    registry: RegistryClient = Depends(get_registry_client),
    settings: Settings = Depends(get_settings),
):
    metrics = metrics_snapshot()
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    pats = db.scalars(select(PersonalAccessToken).order_by(PersonalAccessToken.created_at.desc())).all()
    robots = db.scalars(select(RobotAccount).order_by(RobotAccount.created_at.desc())).all()
    robot_tokens = db.scalars(select(RobotToken).order_by(RobotToken.created_at.desc())).all()

    repo_rows: list[dict] = []
    total_tags = 0
    repo_truncation = {"truncated": False, "pages_fetched": 0, "returned": 0}
    try:
        repositories, repo_truncation = registry.list_repositories_bounded(
            max_pages=settings.registry_catalog_max_pages
        )
        for repository_name in repositories[: settings.dashboard_max_repositories]:
            try:
                tags = registry.list_tags(repository_name)
            except RegistryNotFoundError:
                continue
            total_tags += len(tags)
            repo_rows.append({"name": repository_name, "tag_count": len(tags)})
        repo_truncation["truncated"] = repo_truncation["truncated"] or len(repositories) > settings.dashboard_max_repositories
        repo_truncation["returned"] = len(repo_rows)
    except Exception:
        # Handle registry connectivity issues gracefully
        print("Warning: Registry summary unavailable.")
        # Return empty repo data instead of failing completely
        repo_rows = []
        total_tags = 0
        repo_truncation = {"truncated": False, "pages_fetched": 0, "returned": 0}
    finally:
        registry.close()

    repo_rows.sort(key=lambda item: (-item["tag_count"], item["name"]))

    return {
        "stats": {
            "users_total": len(users),
            "users_active": sum(1 for user in users if user.is_active),
            "pats_active": _count_active_tokens(pats),
            "robots_active": sum(1 for robot in robots if robot.is_active),
            "registry_repositories": len(repo_rows),
            "registry_tags": total_tags,
            "public_pull_tokens_issued": metrics["registry_public_pull_tokens_issued_total"],
        },
        "repo_distribution": repo_rows[:6],
        "repo_distribution_truncation": repo_truncation,
        "provisioning_trend": {
            "users": _bucket_counts([user.created_at for user in users]),
            "tokens": _bucket_counts([token.created_at for token in pats + robot_tokens]),
            "robots": _bucket_counts([robot.created_at for robot in robots]),
        },
        "recent_activity": _dashboard_activity(users, pats, robots, robot_tokens),
    }


@router.get("/admin/settings")
def admin_settings(
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return {
        "public_registry_origin": effective_public_registry_origin(db, settings),
        "restart_command": RESTART_COMMAND,
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
        set_app_setting(db, PUBLIC_REGISTRY_ORIGIN_KEY, public_origin)
        db.commit()
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
        metadata_json={"public_registry_origin": public_origin},
    )
    return {
        "settings": {"public_registry_origin": public_origin},
        "registry_restart_required": True,
        "restart_command": RESTART_COMMAND,
    }


@router.get("/admin/maintenance")
def maintenance_summary(
    page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
):
    summary = maintenance.maintenance_summary(db, page=page)
    return {
        "registry_status": summary["registry_status"],
        "registry_gate_enabled": summary["registry_status"] == "maintenance",
        "storage_usage_bytes": summary["storage_usage_bytes"],
        "log_retention_days": summary["log_retention_days"],
        "active_job": _serialize_gc_job(summary["active_job"]) if summary["active_job"] else None,
        "last_job": _serialize_gc_job(summary["last_job"]) if summary["last_job"] else None,
        "jobs": [_serialize_gc_job(job) for job in summary["jobs"]],
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


@router.get("/admin/audit")
def audit_log(
    actor: Optional[str] = None,
    repo: Optional[str] = None,
    page: int = 1,
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
):
    safe_page = max(page, 1)
    page_size = 10
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc())

    if actor:
        actor_user = db.scalar(select(User).where(User.username == actor))
        if actor_user is None:
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
            AuditEvent.actor_id == actor_user.id,
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
        actor_names = {user.id: user.username for user in users}

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


@router.post("/admin/maintenance/logs/prune")
def prune_maintenance_logs(
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    maintenance: MaintenanceService = Depends(get_maintenance_service),
):
    counts = maintenance.prune_logs(db, actor=user)
    return {
        "retention_days": maintenance.log_retention_days(),
        "pruned": counts,
    }


@router.get("/repos")
def list_repositories(
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    try:
        all_repositories, truncation = registry.list_repositories_bounded(
            max_pages=settings.registry_catalog_max_pages
        )
        visible_repositories = filter_visible_repositories(
            db,
            repository_names=all_repositories,
            **_subject_for_user(user),
        )
        resolvable_repositories: list[str] = []
        for repository_name in visible_repositories:
            try:
                registry.list_tags(repository_name)
            except RegistryNotFoundError:
                continue
            resolvable_repositories.append(repository_name)
        repository_rows = db.scalars(
            select(Repository).where(Repository.name.in_(resolvable_repositories))
        ).all()
        repository_visibility = {
            repository.name: repository.visibility for repository in repository_rows
        }
    finally:
        registry.close()

    return {
        "repos": [
            {
                "name": repository_name,
                "visibility": repository_visibility.get(repository_name, "private"),
            }
            for repository_name in resolvable_repositories
        ],
        "truncation": truncation,
        "user": _serialize_user(user),
    }


@router.get("/repos/{repo_name:path}/tags")
def list_repository_tags(
    repo_name: str,
    user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    if not can_access_repository(db, repository_name=repo_name, action="pull", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pull access required.")

    can_delete_tag = can_access_repository(db, repository_name=repo_name, action="delete", **_subject_for_user(user))
    can_prune_repository = user.is_admin
    repository = db.scalar(select(Repository).where(Repository.name == repo_name))
    visibility = repository.visibility if repository is not None else "private"

    try:
        tags, truncation = registry.list_tag_summaries_bounded(
            repo_name,
            max_tags=settings.repository_tags_max_items,
            max_manifest_children=settings.manifest_children_max_items,
            max_history_entries=settings.history_entries_max_items,
        )
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.") from exc
    finally:
        registry.close()

    return {
        "repo": repo_name,
        "visibility": visibility,
        "public_registry_origin": effective_public_registry_origin(db, settings),
        "can_manage_visibility": user.is_admin,
        "can_delete_tag": can_delete_tag,
        "can_prune_repository": can_prune_repository,
        "tags": [_serialize_tag_summary(tag) for tag in tags],
        "truncation": truncation,
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
    if not can_access_repository(db, repository_name=repo_name, action="pull", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pull access required.")

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
        "manifest": _serialize_manifest(manifest),
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
    if not can_access_repository(db, repository_name=repo_name, action="pull", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pull access required.")

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


@router.post("/repos/{repo_name:path}/tags/{tag}/delete")
def delete_repository_tag(
    repo_name: str,
    tag: str,
    payload: DeleteTagPayload,
    user: User = Depends(require_csrf),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    expected = f"{repo_name}:{tag}"
    if payload.confirmation != expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation text mismatch.")
    if not can_access_repository(db, repository_name=repo_name, action="delete", **_subject_for_user(user)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Delete access required.")

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
    return {"ok": True, "repo": repo_name, "tag": tag, "digest": manifest.digest}


@router.post("/repos/{repo_name:path}/delete")
def delete_empty_repository(
    repo_name: str,
    payload: DeleteRepositoryPayload,
    user: User = Depends(require_csrf),
    _admin: User = Depends(require_admin_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    registry: RegistryClient = Depends(get_registry_client),
):
    if payload.confirmation != repo_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation text mismatch.")
    try:
        tags = registry.list_tags(repo_name)
    except RegistryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.") from exc
    finally:
        registry.close()

    if tags:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository must be empty before deletion.")

    repo_path = _repository_storage_path(settings, repo_name)
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
    return {"ok": True, "repo": repo_name, "removed": removed}
