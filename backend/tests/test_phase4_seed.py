import pytest
from sqlalchemy import select

from backend.config import Settings
from backend.phase4_seed import (
    DEVELOPER_PASSWORD,
    DEVELOPER_USERNAME,
    READER_PASSWORD,
    READER_USERNAME,
    REVOKED_ROBOT_TOKEN,
    ROBOT_NAME,
    ROBOT_TOKEN,
    ensure_phase4_seed_allowed,
    seed_phase4_subjects,
)
from backend.auth.pats import authenticate_named_robot_token
from backend.auth.passwords import verify_password
from backend.models import RepositoryPermission, RobotAccount, RobotToken, User


def test_seed_phase4_subjects_is_idempotent(session, settings) -> None:
    first = seed_phase4_subjects(session, settings)
    second = seed_phase4_subjects(session, settings)

    users = session.scalars(select(User).order_by(User.username.asc())).all()
    permissions = session.scalars(select(RepositoryPermission)).all()
    robots = session.scalars(select(RobotAccount)).all()
    robot_tokens = session.scalars(select(RobotToken)).all()

    assert first == second
    assert [user.username for user in users] == ["admin", "developer", "reader"]
    assert len(permissions) == 4
    assert len(robots) == 1
    assert len(robot_tokens) == 2


def test_seed_phase4_subjects_sets_expected_credentials(session, settings) -> None:
    seed_phase4_subjects(session, settings)

    developer = session.scalar(select(User).where(User.username == DEVELOPER_USERNAME))
    reader = session.scalar(select(User).where(User.username == READER_USERNAME))

    assert developer is not None
    assert reader is not None
    assert verify_password(DEVELOPER_PASSWORD, developer.password_hash) is True
    assert verify_password(READER_PASSWORD, reader.password_hash) is True


def test_seed_phase4_subjects_sets_expected_robot_tokens(session, settings) -> None:
    seed_phase4_subjects(session, settings)

    active_robot = authenticate_named_robot_token(session, robot_name=ROBOT_NAME, raw_token=ROBOT_TOKEN)
    revoked_robot = authenticate_named_robot_token(session, robot_name=ROBOT_NAME, raw_token=REVOKED_ROBOT_TOKEN)

    assert active_robot is not None
    assert revoked_robot is None


def test_phase4_seed_is_allowed_in_development(settings) -> None:
    ensure_phase4_seed_allowed(settings)


def test_phase4_seed_rejects_non_dev_without_override(settings, monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_PHASE4_SEED", raising=False)
    production_settings = Settings(
        app_env="production",
        database_url=settings.database_url,
        registry_internal_url=settings.registry_internal_url,
        registry_storage_root=settings.registry_storage_root,
        compose_project_dir=settings.compose_project_dir,
        registry_service_name=settings.registry_service_name,
        registry_gc_config_path=settings.registry_gc_config_path,
        token_issuer=settings.token_issuer,
        token_service=settings.token_service,
        token_ttl_seconds=settings.token_ttl_seconds,
        public_registry_origin="https://registry.example.com",
        auth_private_key_path=settings.auth_private_key_path,
        auth_public_cert_path=settings.auth_public_cert_path,
        internal_api_base_url=settings.internal_api_base_url,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
        admin_email=settings.admin_email,
        login_rate_limit_attempts=settings.login_rate_limit_attempts,
        login_rate_limit_window_seconds=settings.login_rate_limit_window_seconds,
        auth_token_rate_limit_attempts=settings.auth_token_rate_limit_attempts,
        auth_token_rate_limit_window_seconds=settings.auth_token_rate_limit_window_seconds,
        session_cookie_secure=True,
        session_lifetime_seconds=settings.session_lifetime_seconds,
    )

    with pytest.raises(RuntimeError, match="Phase 4 seed data is disabled outside development"):
        ensure_phase4_seed_allowed(production_settings)


def test_phase4_seed_allows_override_outside_dev(settings, monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_PHASE4_SEED", "1")
    production_settings = Settings(
        app_env="production",
        database_url=settings.database_url,
        registry_internal_url=settings.registry_internal_url,
        registry_storage_root=settings.registry_storage_root,
        compose_project_dir=settings.compose_project_dir,
        registry_service_name=settings.registry_service_name,
        registry_gc_config_path=settings.registry_gc_config_path,
        token_issuer=settings.token_issuer,
        token_service=settings.token_service,
        token_ttl_seconds=settings.token_ttl_seconds,
        public_registry_origin="https://registry.example.com",
        auth_private_key_path=settings.auth_private_key_path,
        auth_public_cert_path=settings.auth_public_cert_path,
        internal_api_base_url=settings.internal_api_base_url,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
        admin_email=settings.admin_email,
        login_rate_limit_attempts=settings.login_rate_limit_attempts,
        login_rate_limit_window_seconds=settings.login_rate_limit_window_seconds,
        auth_token_rate_limit_attempts=settings.auth_token_rate_limit_attempts,
        auth_token_rate_limit_window_seconds=settings.auth_token_rate_limit_window_seconds,
        session_cookie_secure=True,
        session_lifetime_seconds=settings.session_lifetime_seconds,
    )

    ensure_phase4_seed_allowed(production_settings)
