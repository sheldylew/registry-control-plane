import base64
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.auth.signing_material import bootstrap_signing_material, require_signing_material
from backend.auth.pats import authenticate_named_robot_token, authenticate_user_pat
from backend.auth.passwords import verify_password
from backend.auth.permissions import resolve_allowed_access
from backend.auth.scopes import parse_scopes
from backend.config import Settings
from backend.models import RobotAccount, User
from backend.auth.permissions import AllowedAccess
from backend.auth.scopes import RequestedScope


@dataclass(frozen=True)
class AuthenticatedSubject:
    subject_type: str
    subject_id: Optional[int]
    subject_name: str
    is_admin: bool


@dataclass(frozen=True)
class RegistryTokenResult:
    payload: dict
    subject: AuthenticatedSubject
    requested_scopes: list[RequestedScope]
    granted_access: list[AllowedAccess]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _signing_paths(settings: Settings) -> tuple[Path, Path]:
    return Path(settings.auth_private_key_path), Path(settings.auth_public_cert_path)


def _load_private_key_pem(settings: Settings) -> bytes:
    return Path(settings.auth_private_key_path).read_bytes()


def _load_x5c_header(settings: Settings) -> list[str]:
    cert = x509.load_pem_x509_certificate(Path(settings.auth_public_cert_path).read_bytes())
    der_bytes = cert.public_bytes(serialization.Encoding.DER)
    return [base64.b64encode(der_bytes).decode("ascii")]


def encode_registry_token(
    settings: Settings,
    *,
    subject_name: str,
    service: str,
    access_entries: list[dict],
) -> tuple[str, datetime]:
    issued_at = _utcnow()
    expires_at = issued_at + timedelta(seconds=settings.token_ttl_seconds)
    token_payload = {
        "iss": settings.token_issuer,
        "sub": subject_name,
        "aud": service,
        "exp": int(expires_at.timestamp()),
        "nbf": int(issued_at.timestamp()),
        "iat": int(issued_at.timestamp()),
        "jti": str(uuid.uuid4()),
        "access": access_entries,
    }

    encoded = jwt.encode(
        token_payload,
        _load_private_key_pem(settings),
        algorithm="RS256",
        headers={"typ": "JWT", "x5c": _load_x5c_header(settings)},
    )
    return encoded, issued_at


def parse_basic_credentials(authorization: Optional[str]) -> tuple[str, str]:
    if not authorization or not authorization.startswith("Basic "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Basic authentication is required.",
        )

    try:
        decoded = base64.b64decode(authorization[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid basic authentication header.",
        ) from exc

    return username, password


def authenticate_basic_principal(
    session: Session,
    *,
    username: str,
    secret: str,
) -> AuthenticatedSubject:
    user = session.scalar(select(User).where(User.username == username))
    if user is not None and user.is_active:
        if verify_password(secret, user.password_hash):
            return AuthenticatedSubject(
                subject_type="user",
                subject_id=user.id,
                subject_name=user.username,
                is_admin=user.is_admin,
            )

        pat_match = authenticate_user_pat(session, username=username, raw_token=secret)
        if pat_match is not None:
            pat_user, _token = pat_match
            return AuthenticatedSubject(
                subject_type="user",
                subject_id=pat_user.id,
                subject_name=pat_user.username,
                is_admin=pat_user.is_admin,
            )

    robot_match = authenticate_named_robot_token(session, robot_name=username, raw_token=secret)
    if robot_match is not None:
        robot, _token = robot_match
        return AuthenticatedSubject(
            subject_type="robot",
            subject_id=robot.id,
            subject_name=robot.name,
            is_admin=False,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid registry credentials.",
    )


def build_registry_token_response(
    session: Session,
    *,
    settings: Settings,
    authorization: Optional[str],
    service: str,
    scope_values: list[str],
) -> RegistryTokenResult:
    if service != settings.token_service:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported token service.",
        )

    try:
        requested_scopes = parse_scopes(scope_values)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if authorization:
        username, secret = parse_basic_credentials(authorization)
        subject = authenticate_basic_principal(session, username=username, secret=secret)
    else:
        anonymous_requested_repo_pull_only = all(
            scope.resource_type == "repository" and set(scope.actions).issubset({"pull"})
            for scope in requested_scopes
        )
        if not anonymous_requested_repo_pull_only:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Basic authentication is required.",
            )
        subject = AuthenticatedSubject(
            subject_type="anonymous",
            subject_id=None,
            subject_name="anonymous",
            is_admin=False,
        )

    allowed_access = resolve_allowed_access(
        session,
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        is_admin=subject.is_admin,
        requested_scopes=requested_scopes,
    )
    if not authorization and any(set(access.actions) != set(scope.actions) for scope, access in zip(requested_scopes, allowed_access)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Basic authentication is required.",
        )

    encoded, issued_at = encode_registry_token(
        settings,
        subject_name=subject.subject_name,
        service=service,
        access_entries=[
            {
                "type": access.resource_type,
                "name": access.resource_name,
                "actions": list(access.actions),
            }
            for access in allowed_access
        ],
    )

    return RegistryTokenResult(
        payload={
            "token": encoded,
            "access_token": encoded,
            "expires_in": settings.token_ttl_seconds,
            "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        },
        subject=subject,
        requested_scopes=requested_scopes,
        granted_access=allowed_access,
    )
