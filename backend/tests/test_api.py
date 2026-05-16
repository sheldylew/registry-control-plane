import stat
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.auth.pats import issue_personal_access_token
from backend.auth.registry_tokens import bootstrap_signing_material
from backend.auth.passwords import hash_password
from backend.config import Settings
from backend.main import create_app
from backend.metrics import snapshot as metrics_snapshot
from backend.models import (
    AppSetting,
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
from backend.rate_limit import FixedWindowRateLimiter
from backend.registry_client import HistoryVariant, ManifestDetails, RegistryNotFoundError, ResolvedManifestDescriptor, TagSummary
from backend.runtime_secrets import ensure_registry_notifications_token
from backend.setup import (
    AUDIT_LOG_RETENTION_DAYS_KEY,
    AUTOMATIC_REGISTRY_STATE_REBUILD_KEY,
    DEFAULT_AUDIT_LOG_RETENTION_DAYS,
    DEFAULT_REPOSITORY_TAGS_PAGE_SIZE,
    REGISTRY_STORAGE_USAGE_BYTES_KEY,
    REGISTRY_STORAGE_USAGE_MEASURED_AT_KEY,
    REGISTRY_STORAGE_USAGE_STALE_KEY,
    REPOSITORY_TAGS_PAGE_SIZE_KEY,
    STORAGE_USAGE_REFRESH_INTERVAL_SECONDS_KEY,
    PUBLIC_REGISTRY_ORIGIN_KEY,
    ensure_setup_token,
    set_app_setting,
)


def test_healthz_returns_ok(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_healthz_returns_ok(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_auth_token_requires_basic_auth(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:demo/app:pull"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Basic authentication is required."


def test_setup_required_when_no_admin_or_saved_origin(settings) -> None:
    setup_settings = replace(
        settings,
        admin_username=None,
        admin_password=None,
        admin_email=None,
        public_registry_origin="",
    )
    app = create_app(setup_settings)

    with TestClient(app) as client:
        status_response = client.get("/api/setup/status")
        login_response = client.post("/api/session/login", json={"username": "admin", "password": "password"})
        token_response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:demo/app:pull"},
        )

    assert status_response.status_code == 200
    assert status_response.json()["setup_required"] is True
    assert login_response.status_code == 503
    assert token_response.status_code == 503


def test_setup_complete_creates_admin_saves_origin_and_invalidates_token(settings) -> None:
    setup_settings = replace(
        settings,
        admin_username=None,
        admin_password=None,
        admin_email=None,
        public_registry_origin="",
    )
    raw_token = ensure_setup_token(setup_settings, setup_is_required=True)
    app = create_app(setup_settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/setup/complete",
            json={
                "setup_token": raw_token,
                "admin_username": "first-admin",
                "admin_email": "first-admin@example.com",
                "admin_password": "first-admin-pass",
                "public_registry_origin": "http://localhost:8080",
            },
        )
        replay = client.post(
            "/api/setup/complete",
            json={
                "setup_token": raw_token,
                "admin_username": "second-admin",
                "admin_email": "second-admin@example.com",
                "admin_password": "second-admin-pass",
                "public_registry_origin": "http://localhost:8080",
            },
        )
        login = client.post(
            "/api/session/login",
            json={"username": "first-admin", "password": "first-admin-pass"},
        )

        with app.state.session_factory() as session:
            admins = session.scalars(select(User).where(User.is_admin.is_(True))).all()
            origin = session.get(AppSetting, PUBLIC_REGISTRY_ORIGIN_KEY)

    assert response.status_code == 200
    assert response.json()["setup_complete"] is True
    assert response.json()["registry_restart_required"] is True
    assert response.json()["restart_command"] == "docker compose restart registry"
    assert replay.status_code == 409
    assert login.status_code == 200
    assert len(admins) == 1
    assert admins[0].username == "first-admin"
    assert origin is not None
    assert origin.value == "http://localhost:8080"
    assert Path(setup_settings.setup_token_path).exists() is False
    assert "realm: http://localhost:8080/auth/token" in Path(setup_settings.registry_rendered_config_path).read_text(encoding="utf-8")


def test_setup_token_rate_limits_repeated_invalid_attempts(settings) -> None:
    setup_settings = replace(
        settings,
        admin_username=None,
        admin_password=None,
        admin_email=None,
        public_registry_origin="",
    )
    app = create_app(setup_settings)
    app.state.setup_rate_limiter = FixedWindowRateLimiter(max_attempts=1, window_seconds=3600)

    payload = {
        "setup_token": "wrong-token",
        "admin_username": "first-admin",
        "admin_email": "first-admin@example.com",
        "admin_password": "first-admin-pass",
        "public_registry_origin": "http://localhost:8080",
    }
    with TestClient(app) as client:
        first = client.post("/api/setup/complete", json=payload)
        second = client.post("/api/setup/complete", json=payload)

    assert first.status_code == 403
    assert second.status_code == 429


def test_env_bootstrap_saves_origin_and_skips_setup(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        setup_response = client.get("/api/setup/status")
        login_response = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        with app.state.session_factory() as session:
            origin = session.get(AppSetting, PUBLIC_REGISTRY_ORIGIN_KEY)

    assert setup_response.status_code == 200
    assert setup_response.json()["setup_required"] is False
    assert login_response.status_code == 200
    assert origin is not None
    assert origin.value == settings.public_registry_origin


def test_partial_env_bootstrap_stays_in_setup_mode(settings) -> None:
    setup_settings = replace(
        settings,
        admin_username=settings.admin_username,
        admin_password=None,
        admin_email=settings.admin_email,
        public_registry_origin=settings.public_registry_origin,
    )
    app = create_app(setup_settings)

    with TestClient(app) as client:
        response = client.get("/api/setup/status")
        with app.state.session_factory() as session:
            admins = session.scalars(select(User).where(User.is_admin.is_(True))).all()

    assert response.status_code == 200
    assert response.json()["setup_required"] is True
    assert response.json()["env_bootstrap_partial"] is True
    assert admins == []


def test_setup_complete_rejects_non_https_origin_in_production(settings) -> None:
    production_settings = replace(
        settings,
        app_env="production",
        session_cookie_secure=True,
        admin_username=None,
        admin_password=None,
        admin_email=None,
        public_registry_origin="",
    )
    raw_token = ensure_setup_token(production_settings, setup_is_required=True)
    app = create_app(production_settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/setup/complete",
            json={
                "setup_token": raw_token,
                "admin_username": "first-admin",
                "admin_email": "first-admin@example.com",
                "admin_password": "first-admin-pass",
                "public_registry_origin": "http://localhost:8080",
            },
        )

    assert response.status_code == 400
    assert "https" in response.json()["detail"]


def test_admin_bootstrap_runs_on_startup(settings) -> None:
    bootstrap_signing_material(settings)
    app = create_app(settings)

    with TestClient(app):
        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))

    assert admin is not None
    assert admin.is_admin is True
    assert admin.email == settings.admin_email


def test_clean_bootstrap_generates_signing_material_and_marker(settings) -> None:
    bootstrap_signing_material(settings)

    assert settings.auth_bootstrap_marker_path
    with open(settings.auth_private_key_path, "rb") as private_key_file:
        assert private_key_file.read().startswith(b"-----BEGIN PRIVATE KEY-----")
    with open(settings.auth_public_cert_path, "rb") as cert_file:
        assert cert_file.read().startswith(b"-----BEGIN CERTIFICATE-----")
    with open(settings.auth_bootstrap_marker_path, "r", encoding="utf-8") as marker_file:
        assert marker_file.read() == "initialized\n"
    assert stat.S_IMODE(Path(settings.auth_private_key_path).stat().st_mode) == 0o600
    assert stat.S_IMODE(Path(settings.auth_public_cert_path).stat().st_mode) == 0o644
    assert stat.S_IMODE(Path(settings.auth_private_key_path).parent.stat().st_mode) == 0o700


def test_api_startup_rejects_group_readable_private_key(settings) -> None:
    bootstrap_signing_material(settings)
    Path(settings.auth_private_key_path).chmod(0o644)

    app = create_app(settings)
    with pytest.raises(RuntimeError, match="expected 0600"):
        with TestClient(app):
            pass


def test_api_startup_fails_when_marker_exists_but_auth_volume_is_missing(settings) -> None:
    bootstrap_signing_material(settings)

    Path(settings.auth_private_key_path).unlink()
    Path(settings.auth_public_cert_path).unlink()

    app = create_app(settings)
    with pytest.raises(RuntimeError, match="Signing material is missing"):
        with TestClient(app):
            pass


def test_login_succeeds_with_valid_password(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )

        with app.state.session_factory() as session:
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert response.json()["user"]["username"] == settings.admin_username
    assert "rcr_session" in response.cookies
    assert "rcr_csrf" in response.cookies
    assert events[-1].action == "ui_login_succeeded"
    assert metrics_snapshot()["registry_ui_logins_total"] == 1


def test_login_sets_secure_cookies_in_production(settings) -> None:
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
    app = create_app(production_settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/session/login",
            json={"username": production_settings.admin_username, "password": production_settings.admin_password},
        )

    set_cookie_headers = response.headers.get_list("set-cookie")

    assert response.status_code == 200
    assert all("Secure" in header for header in set_cookie_headers)


def test_logout_requires_csrf_token_but_not_trusted_origin(settings) -> None:
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
    app = create_app(production_settings)
    with TestClient(app, base_url="https://registry.example.com") as client:
        login = client.post(
            "/api/session/login",
            json={"username": production_settings.admin_username, "password": production_settings.admin_password},
        )
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/session/logout",
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "http://localhost:8080",
            },
        )
        current_user = client.get("/api/session/me")

    assert response.status_code == 200
    assert current_user.status_code == 401


def test_admin_can_list_and_revoke_web_sessions(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")

        sessions = client.get("/api/admin/sessions")
        assert sessions.status_code == 200
        body = sessions.json()
        current = next(session for session in body["sessions"] if session["is_current"])

        revoke = client.post(
            f"/api/admin/sessions/{current['id']}/revoke",
            headers={"X-CSRF-Token": csrf},
        )
        current_user = client.get("/api/session/me")

    assert body["summary"]["active_sessions"] >= 1
    assert body["summary"]["expired_sessions"] == 0
    assert body["summary"]["revoked_sessions"] == 0
    assert body["pagination"]["page_size"] == 10
    assert current["user"]["username"] == settings.admin_username
    assert revoke.status_code == 200
    assert current_user.status_code == 401


def test_admin_can_revoke_all_sessions_for_user(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        first_login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert first_login.status_code == 200
        user_id = first_login.json()["user"]["id"]
        csrf = first_login.cookies.get("rcr_csrf")

        response = client.post(
            f"/api/admin/users/{user_id}/sessions/revoke",
            headers={"X-CSRF-Token": csrf},
        )
        current_user = client.get("/api/session/me")

    assert response.status_code == 200
    assert response.json()["revoked_sessions"] >= 1
    assert current_user.status_code == 401


def test_login_fails_with_invalid_password(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": "bad-password"},
        )

        with app.state.session_factory() as session:
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 401
    assert events[-1].action == "ui_login_failed"
    assert metrics_snapshot()["registry_ui_login_failures_total"] == 1


def test_login_rate_limits_repeated_failures(settings) -> None:
    app = create_app(settings)
    app.state.login_rate_limiter = FixedWindowRateLimiter(max_attempts=2, window_seconds=3600)

    with TestClient(app) as client:
        first = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": "bad-password"},
        )
        second = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": "bad-password"},
        )
        third = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": "bad-password"},
        )

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert 3590 <= int(third.headers["retry-after"]) <= 3600


def test_production_settings_require_secure_cookies(settings) -> None:
    try:
        Settings(
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
            session_cookie_secure=False,
            session_lifetime_seconds=settings.session_lifetime_seconds,
        )
        raise AssertionError("Expected production settings validation to fail.")
    except ValueError as exc:
        assert "SESSION_COOKIE_SECURE" in str(exc)


def test_production_settings_require_https_public_origin(settings) -> None:
    with pytest.raises(ValueError, match="PUBLIC_REGISTRY_ORIGIN"):
        Settings(
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
            public_registry_origin="http://localhost:8080",
            auth_private_key_path=settings.auth_private_key_path,
            auth_public_cert_path=settings.auth_public_cert_path,
            internal_api_base_url=settings.internal_api_base_url,
            admin_username=settings.admin_username,
            admin_password=settings.admin_password,
            admin_email=settings.admin_email,
            session_cookie_secure=True,
            session_lifetime_seconds=settings.session_lifetime_seconds,
        )


def test_admin_routes_reject_unauthenticated_user(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/admin/users")

    assert response.status_code == 401


def test_admin_routes_reject_non_admin_user(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="plain-user",
                email="plain-user@example.com",
                password_hash=hash_password("plain-user-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()

        login = client.post(
            "/api/session/login",
            json={"username": "plain-user", "password": "plain-user-pass"},
        )
        assert login.status_code == 200
        response = client.get("/api/admin/users")

    assert response.status_code == 403


def test_admin_users_list_supports_pagination(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            users = []
            for index in range(1, 13):
                users.append(
                    User(
                        username=f"user-{index:02d}",
                        email=f"user-{index:02d}@example.com",
                        password_hash=hash_password(f"password-{index:02d}"),
                        is_admin=False,
                        is_active=True,
                    )
                )
            session.add_all(users)
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        first = client.get("/api/admin/users")
        second = client.get("/api/admin/users?page=2")

    body_first = first.json()
    body_second = second.json()

    assert first.status_code == 200
    assert second.status_code == 200
    assert body_first["pagination"]["page"] == 1
    assert body_first["pagination"]["page_size"] == 10
    assert body_first["pagination"]["total"] == 13
    assert body_first["pagination"]["has_prev"] is False
    assert body_first["pagination"]["has_next"] is True
    assert len(body_first["users"]) == 10
    assert body_second["pagination"]["page"] == 2
    assert body_second["pagination"]["total"] == 13
    assert body_second["pagination"]["has_prev"] is True
    assert body_second["pagination"]["has_next"] is False
    assert len(body_second["users"]) == 3


def test_admin_can_load_user_detail_profile_payload(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="detail-user",
                email="detail-user@example.com",
                password_hash=hash_password("detail-user-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id
            session.add(
                PersonalAccessToken(
                    user_id=user_id,
                    name="cli-token",
                    token_hash="a" * 64,
                    token_prefix="pref1234",
                )
            )
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user_id,
                    repository_pattern="detail/*",
                    can_pull=True,
                    can_push=True,
                    can_delete=False,
                )
            )
            session.add(
                AuditEvent(
                    actor_type="user",
                    actor_id=user_id,
                    action="user_password_reset",
                    target_type="user",
                    target_id=user_id,
                )
            )
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get(f"/api/admin/users/{user_id}")

    body = response.json()
    assert response.status_code == 200
    assert body["user"]["username"] == "detail-user"
    assert body["tokens"][0]["name"] == "cli-token"
    assert body["permissions"][0]["repository_pattern"] == "detail/*"
    assert body["recent_activity"][0]["action"] == "user_password_reset"


def test_admin_can_load_robot_detail_profile_payload(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            robot = RobotAccount(name="detail-bot", description="profile bot", is_active=True)
            session.add(robot)
            session.commit()
            session.refresh(robot)
            robot_id = robot.id
            session.add(
                RobotToken(
                    robot_id=robot_id,
                    name="default",
                    token_hash="b" * 64,
                    token_prefix="rbt12345",
                )
            )
            session.add(
                RepositoryPermission(
                    subject_type="robot",
                    subject_id=robot_id,
                    repository_pattern="robot/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=False,
                )
            )
            session.add(
                AuditEvent(
                    actor_type="user",
                    actor_id=1,
                    action="robot_created",
                    target_type="robot_account",
                    target_id=robot_id,
                )
            )
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get(f"/api/admin/robots/{robot_id}")

    body = response.json()
    assert response.status_code == 200
    assert body["robot"]["name"] == "detail-bot"
    assert body["robot"]["tokens"][0]["name"] == "default"
    assert body["permissions"][0]["repository_pattern"] == "robot/*"
    assert body["recent_activity"][0]["action"] == "robot_created"


def test_admin_cannot_disable_own_account(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")

        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))
            assert admin is not None
            admin_id = admin.id

        response = client.post(
            f"/api/admin/users/{admin_id}/disable",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.id == admin_id))

    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot disable your own account."
    assert admin is not None
    assert admin.is_active is True


def test_admin_can_enable_disabled_user(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="disabled-user",
                email="disabled-user@example.com",
                password_hash=hash_password("disabled-user-pass"),
                is_admin=False,
                is_active=False,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

        login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            f"/api/admin/users/{user_id}/enable",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            user = session.get(User, user_id)
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert response.json()["user"]["is_active"] is True
    assert user is not None
    assert user.is_active is True
    assert events[-1].action == "user_enabled"


def test_admin_write_requires_same_origin_csrf_request(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/admin/users",
            json={
                "username": "csrf-blocked",
                "email": "csrf-blocked@example.com",
                "password": "password-123",
                "is_admin": False,
            },
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "https://evil.example",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid request origin."


def test_admin_write_allows_same_origin_csrf_request(settings) -> None:
    custom_settings = Settings(
        app_env=settings.app_env,
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
        session_cookie_secure=settings.session_cookie_secure,
        session_lifetime_seconds=settings.session_lifetime_seconds,
    )
    app = create_app(custom_settings)
    with TestClient(app, base_url="http://testserver") as client:
        login = client.post(
            "/api/session/login",
            json={"username": custom_settings.admin_username, "password": custom_settings.admin_password},
        )
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/admin/users",
            json={
                "username": "csrf-allowed",
                "email": "csrf-allowed@example.com",
                "password": "password-123",
                "is_admin": False,
            },
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "https://registry.example.com",
            },
        )

    assert response.status_code == 200


def test_admin_permissions_endpoint_lists_users_robots_and_rules(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="perm-user",
                email="perm-user@example.com",
                password_hash=hash_password("perm-user-pass"),
                is_admin=False,
                is_active=True,
            )
            robot = RobotAccount(name="perm-bot", description="permission bot", is_active=True)
            session.add_all([user, robot])
            session.commit()
            session.refresh(user)
            session.refresh(robot)
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user.id,
                    repository_pattern="sheldylew/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=False,
                )
            )
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/admin/permissions")

    body = response.json()
    assert response.status_code == 200
    assert any(entry["username"] == "perm-user" for entry in body["users"])
    assert any(entry["name"] == "perm-bot" for entry in body["robots"])
    assert body["permissions"][0]["subject_name"] == "perm-user"
    assert body["permissions"][0]["repository_pattern"] == "sheldylew/*"


def test_create_user_returns_conflict_for_duplicate_username(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/admin/users",
            json={
                "username": settings.admin_username,
                "email": "another@example.com",
                "password": "password-123",
                "is_admin": False,
            },
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "http://testserver",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "A user with that username or email already exists."


def test_create_user_returns_conflict_for_duplicate_email(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/admin/users",
            json={
                "username": "another-admin-name",
                "email": settings.admin_email,
                "password": "password-123",
                "is_admin": False,
            },
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "http://testserver",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "A user with that username or email already exists."


def test_create_user_rejects_whitespace_only_username(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/admin/users",
            json={
                "username": "   ",
                "email": "trim-check@example.com",
                "password": "password-123",
                "is_admin": False,
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, Username is required."


def test_create_user_trims_username_and_email_before_persisting(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/admin/users",
            json={
                "username": "  trimmed-user  ",
                "email": "  trimmed-user@example.com  ",
                "password": "password-123",
                "is_admin": False,
            },
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            user = session.scalar(select(User).where(User.username == "trimmed-user"))

    assert response.status_code == 200
    assert user is not None
    assert user.username == "trimmed-user"
    assert user.email == "trimmed-user@example.com"


def test_admin_can_reset_user_password_and_revoke_sessions(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as admin_client, TestClient(app) as user_client:
        with app.state.session_factory() as session:
            user = User(
                username="reset-user",
                email="reset-user@example.com",
                password_hash=hash_password("old-password-123"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

        user_login = _login(user_client, "reset-user", "old-password-123")
        assert user_login.status_code == 200
        admin_login = _login(admin_client, settings.admin_username, settings.admin_password)
        assert admin_login.status_code == 200
        csrf = admin_login.cookies.get("rcr_csrf")

        response = admin_client.post(
            f"/api/admin/users/{user_id}/password",
            json={"password": "new-password-123"},
            headers={"X-CSRF-Token": csrf},
        )

        revoked_session_response = user_client.get("/api/session/me")
        old_password_login = _login(user_client, "reset-user", "old-password-123")
        new_password_login = _login(user_client, "reset-user", "new-password-123")

        with app.state.session_factory() as session:
            user = session.get(User, user_id)
            active_sessions = session.scalars(
                select(WebSession).where(
                    WebSession.user_id == user_id,
                    WebSession.revoked_at.is_(None),
                )
            ).all()
            revoked_sessions = session.scalars(
                select(WebSession).where(
                    WebSession.user_id == user_id,
                    WebSession.revoked_at.is_not(None),
                )
            ).all()
            audit_event = session.scalar(
                select(AuditEvent).where(
                    AuditEvent.action == "user_password_reset",
                    AuditEvent.target_type == "user",
                    AuditEvent.target_id == user_id,
                )
            )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "reset-user"
    assert response.json()["revoked_sessions"] == 1
    assert revoked_session_response.status_code == 401
    assert old_password_login.status_code == 401
    assert new_password_login.status_code == 200
    assert user is not None
    assert len(active_sessions) == 1
    assert len(revoked_sessions) == 1
    assert audit_event is not None
    assert audit_event.metadata_json == {"username": "reset-user", "revoked_sessions": 1}


def test_admin_reset_user_password_rejects_invalid_password(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="short-reset-user",
                email="short-reset-user@example.com",
                password_hash=hash_password("old-password-123"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            f"/api/admin/users/{user_id}/password",
            json={"password": "short"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 422


def test_admin_reset_own_password_requires_current_password(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")

        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))
            assert admin is not None
            admin_id = admin.id

        missing_current = client.post(
            f"/api/admin/users/{admin_id}/password",
            json={"password": "new-admin-password-123"},
            headers={"X-CSRF-Token": csrf},
        )
        wrong_current = client.post(
            f"/api/admin/users/{admin_id}/password",
            json={"password": "new-admin-password-123", "current_password": "wrong-password"},
            headers={"X-CSRF-Token": csrf},
        )
        valid_current = client.post(
            f"/api/admin/users/{admin_id}/password",
            json={"password": "new-admin-password-123", "current_password": settings.admin_password},
            headers={"X-CSRF-Token": csrf},
        )

        revoked_session_response = client.get("/api/session/me")
        old_password_login = _login(client, settings.admin_username, settings.admin_password)
        new_password_login = _login(client, settings.admin_username, "new-admin-password-123")

    assert missing_current.status_code == 401
    assert missing_current.json()["detail"] == "Current password is incorrect."
    assert wrong_current.status_code == 401
    assert wrong_current.json()["detail"] == "Current password is incorrect."
    assert valid_current.status_code == 200
    assert valid_current.json()["revoked_sessions"] == 1
    assert revoked_session_response.status_code == 401
    assert old_password_login.status_code == 401
    assert new_password_login.status_code == 200


def test_admin_can_create_or_update_repository_permission(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="perm-editor",
                email="perm-editor@example.com",
                password_hash=hash_password("perm-editor-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/permissions",
            json={
                "subject_type": "user",
                "subject_id": user_id,
                "repository_pattern": "sheldylew/*",
                "can_pull": True,
                "can_push": True,
                "can_delete": False,
            },
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            permission = session.scalar(
                select(RepositoryPermission).where(
                    RepositoryPermission.subject_type == "user",
                    RepositoryPermission.subject_id == user_id,
                    RepositoryPermission.repository_pattern == "sheldylew/*",
                )
            )
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert permission is not None
    assert permission.can_pull is True
    assert permission.can_push is True
    assert permission.can_delete is False
    assert events[-1].action == "repository_permission_created"


def test_admin_permission_rejects_whitespace_only_repository_pattern(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/permissions",
            json={
                "subject_type": "user",
                "subject_id": 1,
                "repository_pattern": "   ",
                "can_pull": True,
                "can_push": False,
                "can_delete": False,
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, Repository pattern is required."


def test_admin_permission_rejects_global_wildcard_pattern(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/permissions",
            json={
                "subject_type": "user",
                "subject_id": 1,
                "repository_pattern": "*",
                "can_pull": True,
                "can_push": False,
                "can_delete": False,
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Global '*' repository permissions are not allowed."


def test_admin_can_delete_repository_permission(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="perm-delete",
                email="perm-delete@example.com",
                password_hash=hash_password("perm-delete-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            permission = RepositoryPermission(
                subject_type="user",
                subject_id=user.id,
                repository_pattern="sheldylew/*",
                can_pull=True,
                can_push=False,
                can_delete=False,
            )
            session.add(permission)
            session.commit()
            session.refresh(permission)
            permission_id = permission.id

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            f"/api/admin/permissions/{permission_id}/delete",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            deleted = session.get(RepositoryPermission, permission_id)
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert deleted is None
    assert events[-1].action == "repository_permission_deleted"


def test_admin_can_create_or_update_repository_visibility(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/repositories/visibility",
            json={
                "repository_name": "public/app",
                "visibility": "public",
            },
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            repository = session.scalar(select(Repository).where(Repository.name == "public/app"))
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert repository is not None
    assert repository.visibility == "public"
    assert events[-1].action == "repository_visibility_created"


def test_admin_repository_visibility_rejects_wildcards(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/repositories/visibility",
            json={
                "repository_name": "public/*",
                "visibility": "public",
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Repository visibility must target an exact repository name."


def test_public_repository_is_visible_without_explicit_permission(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="public-browser",
                email="public-browser@example.com",
                password_hash=hash_password("public-browser-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            _seed_repository_state(session, "public/app", visibility="public")
            session.commit()

        login = client.post(
            "/api/session/login",
            json={"username": "public-browser", "password": "public-browser-pass"},
        )
        assert login.status_code == 200
        response = client.get("/api/repos")

    assert response.status_code == 200
    assert response.json()["repos"] == [{"name": "public/app", "visibility": "public"}]


def test_admin_can_disable_robot(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            robot = RobotAccount(name="ops-bot", description="ops", is_active=True)
            session.add(robot)
            session.commit()
            session.refresh(robot)
            robot_id = robot.id

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            f"/api/admin/robots/{robot_id}/disable",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            robot = session.get(RobotAccount, robot_id)
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert robot is not None
    assert robot.is_active is False
    assert events[-1].action == "robot_disabled"


def test_admin_can_create_robot_with_trimmed_fields(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")

        response = client.post(
            "/api/admin/robots",
            json={
                "name": "  deploy-bot  ",
                "description": "  automation account  ",
            },
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            robot = session.scalar(select(RobotAccount).where(RobotAccount.name == "deploy-bot"))

    assert response.status_code == 200
    assert robot is not None
    assert robot.name == "deploy-bot"
    assert robot.description == "automation account"


def test_admin_create_robot_rejects_duplicate_name(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(RobotAccount(name="duplicate-bot", description="existing", is_active=True))
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/robots",
            json={"name": " duplicate-bot ", "description": "another"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "A robot with that name already exists."


def test_admin_can_enable_robot(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            robot = RobotAccount(name="ops-bot-disabled", description="ops", is_active=False)
            session.add(robot)
            session.commit()
            session.refresh(robot)
            robot_id = robot.id

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            f"/api/admin/robots/{robot_id}/enable",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            robot = session.get(RobotAccount, robot_id)
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert robot is not None
    assert robot.is_active is True
    assert events[-1].action == "robot_enabled"


def test_admin_can_revoke_robot_token(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            robot = RobotAccount(name="token-bot", description="token", is_active=True)
            session.add(robot)
            session.commit()
            session.refresh(robot)
            token = RobotToken(robot_id=robot.id, name="default", token_hash="hash-r1", token_prefix="rbt001")
            session.add(token)
            session.commit()
            session.refresh(token)
            robot_id = robot.id
            token_id = token.id

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            f"/api/admin/robots/{robot_id}/tokens/{token_id}/revoke",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            token = session.get(RobotToken, token_id)
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert token is not None
    assert token.revoked_at is not None
    assert events[-1].action == "robot_token_revoked"


def test_admin_create_pat_rejects_whitespace_only_name(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/tokens",
            json={"name": "   "},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, Token name is required."


def test_admin_can_delete_robot_and_tokens(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            robot = RobotAccount(name="delete-bot", description="delete", is_active=True)
            session.add(robot)
            session.commit()
            session.refresh(robot)
            token = RobotToken(robot_id=robot.id, name="default", token_hash="hash-r2", token_prefix="rbt002")
            session.add(token)
            session.commit()
            session.refresh(token)
            robot_id = robot.id
            token_id = token.id

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            f"/api/admin/robots/{robot_id}/delete",
            json={"confirmation": "delete-bot"},
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            deleted_robot = session.get(RobotAccount, robot_id)
            deleted_token = session.get(RobotToken, token_id)
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    assert deleted_robot is None
    assert deleted_token is None
    assert events[-1].action == "robot_deleted"


class FakeRegistryClient:
    def __init__(
        self,
        repositories=None,
        tags=None,
        manifests=None,
        descriptors=None,
        descriptor_sequences=None,
        histories=None,
        missing_repos=None,
        repo_pages_truncated=False,
    ):
        self.repositories = repositories or []
        self.tags = tags or {}
        self.manifests = manifests or {}
        self.descriptors = descriptors or {}
        self.descriptor_sequences = {
            key: list(values) for key, values in (descriptor_sequences or {}).items()
        }
        self.histories = histories or {}
        self.missing_repos = missing_repos or set()
        self.repo_pages_truncated = repo_pages_truncated
        self.deleted_manifests = []
        self.list_tags_calls = []
        self.resolve_manifest_descriptor_calls = []
        self.list_tag_summaries_for_tags_calls = []
        self.get_manifest_details_calls = []
        self.get_tag_history_bounded_calls = []
        self.list_repositories_bounded_calls = 0
        self.list_tag_summaries_bounded_calls = 0

    def close(self) -> None:
        return None

    def list_repositories(self) -> list[str]:
        return self.repositories

    def list_tags(self, repository_name: str) -> list[str]:
        self.list_tags_calls.append(repository_name)
        if repository_name in self.missing_repos:
            raise RegistryNotFoundError(repository_name)
        return self.tags.get(repository_name, [])

    def list_tag_summaries(self, repository_name: str) -> list[TagSummary]:
        summaries, _meta = self.list_tag_summaries_bounded(repository_name)
        return summaries

    def resolve_manifest_descriptor(self, repository_name: str, reference: str) -> ResolvedManifestDescriptor:
        self.resolve_manifest_descriptor_calls.append((repository_name, reference))
        if repository_name in self.missing_repos:
            raise RegistryNotFoundError(repository_name)
        key = (repository_name, reference)
        if key in self.descriptor_sequences:
            sequence = self.descriptor_sequences[key]
            if not sequence:
                raise RegistryNotFoundError(reference)
            digest, media_type = sequence[0]
            if len(sequence) > 1:
                self.descriptor_sequences[key] = sequence[1:]
            return ResolvedManifestDescriptor(digest=digest, media_type=media_type)
        if key in self.descriptors:
            digest, media_type = self.descriptors[key]
            return ResolvedManifestDescriptor(digest=digest, media_type=media_type)
        payload = self.manifests.get(key)
        if payload is None:
            raise RegistryNotFoundError(reference)
        return ResolvedManifestDescriptor(
            digest=payload.get("digest"),
            media_type=payload.get("media_type"),
        )

    def list_tag_summaries_for_tags(
        self,
        repository_name: str,
        tags: list[str],
        *,
        max_manifest_children=None,
        max_history_entries=None,
    ) -> list[TagSummary]:
        self.list_tag_summaries_for_tags_calls.append((repository_name, list(tags)))
        summaries = []
        for tag in tags:
            details = self.get_manifest_details(
                repository_name,
                tag,
                max_manifest_children=max_manifest_children,
                max_history_entries=max_history_entries,
            )
            summaries.append(
                TagSummary(
                    tag=tag,
                    digest=details.digest,
                    media_type=details.media_type,
                    total_size=details.total_size,
                    architectures=details.architectures,
                    created_at=details.created_at,
                    history_count=details.history_count,
                    children_truncated=details.children_truncated,
                    history_truncated=details.history_truncated,
                )
            )
        return summaries

    def list_tag_summaries_bounded(
        self,
        repository_name: str,
        *,
        max_tags=None,
        max_manifest_children=None,
        max_history_entries=None,
    ) -> tuple[list[TagSummary], dict]:
        self.list_tag_summaries_bounded_calls += 1
        if repository_name in self.missing_repos:
            raise RegistryNotFoundError(repository_name)
        tags = self.tags.get(repository_name, [])
        limited = tags[:max_tags] if max_tags is not None else tags
        summaries = self.list_tag_summaries_for_tags(
            repository_name,
            limited,
            max_manifest_children=max_manifest_children,
            max_history_entries=max_history_entries,
        )
        return summaries, {
            "truncated": max_tags is not None and len(tags) > max_tags,
            "returned": len(summaries),
            "available": len(tags),
        }

    def get_manifest_details(
        self,
        repository_name: str,
        tag: str,
        *,
        max_manifest_children=None,
        max_history_entries=None,
    ) -> ManifestDetails:
        self.get_manifest_details_calls.append((repository_name, tag))
        if repository_name in self.missing_repos:
            raise RegistryNotFoundError(repository_name)
        payload = self.manifests.get((repository_name, tag))
        if payload is None:
            for (candidate_repo, _candidate_tag), candidate_payload in self.manifests.items():
                if candidate_repo == repository_name and candidate_payload.get("digest") == tag:
                    payload = candidate_payload
                    break
        if payload is None:
            raise RegistryNotFoundError(tag)
        return ManifestDetails(**payload)

    def get_tag_history(self, repository_name: str, tag: str) -> list[HistoryVariant]:
        variants, _meta = self.get_tag_history_bounded(repository_name, tag)
        return variants

    def get_tag_history_bounded(
        self,
        repository_name: str,
        tag: str,
        *,
        max_manifest_children=None,
        max_history_entries=None,
    ) -> tuple[list[HistoryVariant], dict]:
        self.get_tag_history_bounded_calls.append((repository_name, tag))
        if repository_name in self.missing_repos:
            raise RegistryNotFoundError(repository_name)
        variants = self.histories[(repository_name, tag)]
        limited = variants[:max_manifest_children] if max_manifest_children is not None else variants
        return limited, {
            "truncated": max_manifest_children is not None and len(variants) > max_manifest_children,
            "returned": len(limited),
            "available": len(variants),
        }

    def list_repositories_bounded(self, *, max_pages=None) -> tuple[list[str], dict]:
        self.list_repositories_bounded_calls += 1
        return self.repositories, {
            "truncated": self.repo_pages_truncated,
            "pages_fetched": 1,
        }

    def delete_manifest(self, repository_name: str, digest: str) -> None:
        self.deleted_manifests.append((repository_name, digest))


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/session/login", json={"username": username, "password": password})


def _registry_event_headers(app) -> dict[str, str]:
    return {"Authorization": f"Bearer {ensure_registry_notifications_token(app.state.settings)}"}


def _seed_repository_state(
    session,
    repository_name: str,
    *,
    tags: tuple[str, ...] = ("latest",),
    visibility: str = "private",
    deleted: bool = False,
) -> Repository:
    now = datetime.now(timezone.utc)
    repository = Repository(
        name=repository_name,
        visibility=visibility,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
        deleted_at=now if deleted else None,
    )
    session.add(repository)
    session.flush()
    for tag in tags:
        session.add(
            RepositoryTag(
                repository_id=repository.id,
                name=tag,
                manifest_digest=f"sha256:{repository_name.replace('/', '-')}-{tag}",
                media_type="application/vnd.oci.image.manifest.v1+json",
                pushed_at=now,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
    return repository


def _grant_reader(session, *, username: str, password: str = "reader-pass", pattern: str = "sheldylew/*") -> User:
    user = User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password(password),
        is_admin=False,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(
        RepositoryPermission(
            subject_type="user",
            subject_id=user.id,
            repository_pattern=pattern,
            can_pull=True,
            can_push=False,
            can_delete=False,
        )
    )
    session.commit()
    return user


def _seed_manifest_summary(
    session,
    *,
    repository_name: str,
    manifest_digest: str,
    tag_created_at: str = "2026-05-04T10:20:30Z",
    total_size: int = 1048576,
    architectures: list[str] | None = None,
) -> CachedManifestSummary:
    now = datetime.now(timezone.utc)
    row = CachedManifestSummary(
        repository_name=repository_name,
        manifest_digest=manifest_digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
        config_digest=f"{manifest_digest}-cfg",
        total_size=total_size,
        created_at=datetime.fromisoformat(tag_created_at.replace("Z", "+00:00")),
        architectures=architectures or ["linux/amd64", "linux/arm64"],
        history_count=5,
        children_truncated=False,
        history_truncated=False,
        cached_at=now,
        last_seen_at=now,
    )
    session.add(row)
    return row


def test_admin_can_update_public_registry_origin(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/settings",
            json={
                "public_registry_origin": "https://registry.example.com",
                "ui_timezone": "America/New_York",
                "repository_tags_page_size": 25,
                "audit_log_retention_days": 60,
                "automatic_registry_state_rebuild": True,
                "storage_usage_refresh_interval_seconds": 120,
            },
            headers={"X-CSRF-Token": csrf},
        )
        settings_response = client.get("/api/admin/settings")
        with app.state.session_factory() as session:
            origin = session.get(AppSetting, PUBLIC_REGISTRY_ORIGIN_KEY)
            ui_timezone = session.get(AppSetting, "ui_timezone")
            repository_tags_page_size = session.get(AppSetting, REPOSITORY_TAGS_PAGE_SIZE_KEY)
            audit_log_retention_days = session.get(AppSetting, AUDIT_LOG_RETENTION_DAYS_KEY)
            automatic_rebuild = session.get(AppSetting, AUTOMATIC_REGISTRY_STATE_REBUILD_KEY)
            storage_interval = session.get(AppSetting, STORAGE_USAGE_REFRESH_INTERVAL_SECONDS_KEY)

    assert response.status_code == 200
    assert response.json()["registry_restart_required"] is True
    assert response.json()["restart_command"] == "docker compose restart registry"
    assert settings_response.status_code == 200
    assert settings_response.json()["build"]["version"] == settings.app_version
    assert settings_response.json()["build"]["revision"] == settings.app_revision
    assert settings_response.json()["build"]["built_at"] == settings.app_build_time
    assert settings_response.json()["build"]["image_tag"] == settings.app_image_tag
    assert settings_response.json()["public_registry_origin"] == "https://registry.example.com"
    assert settings_response.json()["ui_timezone"] == "America/New_York"
    assert settings_response.json()["repository_tags_page_size"] == 25
    assert settings_response.json()["audit_log_retention_days"] == 60
    assert settings_response.json()["automatic_registry_state_rebuild"] is True
    assert settings_response.json()["storage_usage_refresh_interval_seconds"] == 120
    assert origin is not None
    assert origin.value == "https://registry.example.com"
    assert ui_timezone is not None
    assert ui_timezone.value == "America/New_York"
    assert repository_tags_page_size is not None
    assert repository_tags_page_size.value == "25"
    assert audit_log_retention_days is not None
    assert audit_log_retention_days.value == "60"
    assert automatic_rebuild is not None
    assert automatic_rebuild.value == "true"
    assert storage_interval is not None
    assert storage_interval.value == "120"


def test_automatic_registry_rebuild_setting_queues_startup_job(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/settings",
            json={
                "public_registry_origin": settings.public_registry_origin,
                "ui_timezone": "America/Los_Angeles",
                "automatic_registry_state_rebuild": True,
            },
            headers={"X-CSRF-Token": csrf},
        )

    restarted_app = create_app(settings)
    restarted_app.state.maintenance_auto_run = False
    with TestClient(restarted_app):
        with restarted_app.state.session_factory() as session:
            job = session.scalar(select(RegistryStateRebuildJob).order_by(RegistryStateRebuildJob.id.desc()))
            audit = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.action == "registry_state_rebuild_requested")
                .order_by(AuditEvent.id.desc())
            )

    assert response.status_code == 200
    assert job is not None
    assert job.status == "queued"
    assert audit is not None
    assert audit.metadata_json["reason"] == "automatic_startup"


def test_maintenance_summary_uses_cached_storage_usage(settings, monkeypatch) -> None:
    app = create_app(settings)
    measured_at = datetime(2026, 5, 11, 12, 30, tzinfo=timezone.utc)

    with TestClient(app) as client:
        _login(client, settings.admin_username, settings.admin_password)
        with app.state.session_factory() as session:
            set_app_setting(session, REGISTRY_STORAGE_USAGE_BYTES_KEY, "12345")
            set_app_setting(session, REGISTRY_STORAGE_USAGE_MEASURED_AT_KEY, measured_at.isoformat())
            set_app_setting(session, REGISTRY_STORAGE_USAGE_STALE_KEY, "true")
            set_app_setting(session, STORAGE_USAGE_REFRESH_INTERVAL_SECONDS_KEY, "0")
            session.commit()

        def fail_storage_walk(_storage_root):
            raise AssertionError("maintenance summary should not walk registry storage")

        monkeypatch.setattr("backend.maintenance.compute_storage_usage_bytes", fail_storage_walk)
        response = client.get("/api/admin/maintenance")

    assert response.status_code == 200
    assert response.json()["storage_usage_bytes"] == 12345
    assert response.json()["storage_usage_measured_at"] == measured_at.isoformat()
    assert response.json()["storage_usage_stale"] is True


def test_admin_can_update_public_registry_origin_after_external_domain_changes(settings) -> None:
    production_settings = replace(
        settings,
        app_env="production",
        public_registry_origin="https://registry-old.sheldylew.com",
        session_cookie_secure=True,
    )
    app = create_app(production_settings)

    with TestClient(app, base_url="https://registry-test.sheldylew.com") as client:
        login = _login(client, production_settings.admin_username, production_settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/settings",
            json={
                "public_registry_origin": "https://registry-test.sheldylew.com",
                "ui_timezone": "America/Los_Angeles",
            },
            headers={
                "X-CSRF-Token": csrf,
                "Origin": "https://registry-test.sheldylew.com",
            },
        )

    assert response.status_code == 200
    assert response.json()["settings"]["public_registry_origin"] == "https://registry-test.sheldylew.com"
    assert response.json()["registry_restart_required"] is True


def test_ui_settings_defaults_to_los_angeles_timezone(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/api/ui-settings")

    assert response.status_code == 200
    assert response.json()["ui_timezone"] == "America/Los_Angeles"


def test_admin_settings_default_repository_tags_page_size_is_ten(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        _login(client, settings.admin_username, settings.admin_password)
        response = client.get("/api/admin/settings")

    assert response.status_code == 200
    assert response.json()["repository_tags_page_size"] == DEFAULT_REPOSITORY_TAGS_PAGE_SIZE
    assert response.json()["default_repository_tags_page_size"] == DEFAULT_REPOSITORY_TAGS_PAGE_SIZE
    assert response.json()["audit_log_retention_days"] == DEFAULT_AUDIT_LOG_RETENTION_DAYS
    assert response.json()["default_audit_log_retention_days"] == DEFAULT_AUDIT_LOG_RETENTION_DAYS


def test_admin_can_update_repository_tags_page_size_without_restart(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/settings",
            json={
                "public_registry_origin": settings.public_registry_origin,
                "ui_timezone": "America/Los_Angeles",
                "repository_tags_page_size": 7,
                "automatic_registry_state_rebuild": False,
                "storage_usage_refresh_interval_seconds": 3600,
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 200
    assert response.json()["settings"]["repository_tags_page_size"] == 7
    assert response.json()["registry_restart_required"] is False
    assert response.json()["restart_command"] is None


def test_admin_can_update_audit_log_retention_without_restart(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/settings",
            json={
                "public_registry_origin": settings.public_registry_origin,
                "ui_timezone": "America/Los_Angeles",
                "repository_tags_page_size": 10,
                "audit_log_retention_days": 15,
                "automatic_registry_state_rebuild": False,
                "storage_usage_refresh_interval_seconds": 3600,
            },
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            audit_log_retention_days = session.get(AppSetting, AUDIT_LOG_RETENTION_DAYS_KEY)

    assert response.status_code == 200
    assert response.json()["settings"]["audit_log_retention_days"] == 15
    assert response.json()["registry_restart_required"] is False
    assert response.json()["restart_command"] is None
    assert audit_log_retention_days is not None
    assert audit_log_retention_days.value == "15"


def test_default_page_size_setting_applies_to_paginated_lists(settings) -> None:
    app = create_app(settings)
    default_page_size = 7

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))
            assert admin is not None
            set_app_setting(session, REPOSITORY_TAGS_PAGE_SIZE_KEY, str(default_page_size))

            activity_user = User(
                username="activity-user",
                email="activity-user@example.com",
                password_hash=hash_password("activity-user-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(activity_user)
            session.flush()

            for index in range(12):
                user = User(
                    username=f"page-user-{index:02d}",
                    email=f"page-user-{index:02d}@example.com",
                    password_hash=hash_password(f"page-user-pass-{index:02d}"),
                    is_admin=False,
                    is_active=True,
                )
                session.add(user)
                session.flush()
                session.add(
                    RepositoryPermission(
                        subject_type="user",
                        subject_id=user.id,
                        repository_pattern=f"page-seed/{index:02d}/*",
                        can_pull=True,
                        can_push=False,
                        can_delete=False,
                    )
                )

            for index in range(12):
                issue_personal_access_token(session, user_id=admin.id, name=f"page-token-{index:02d}")

            now = datetime.now(timezone.utc)
            for index in range(12):
                session.add(
                    WebSession(
                        user_id=admin.id,
                        session_hash=f"{index + 1:064x}",
                        csrf_token=f"page-csrf-{index:02d}",
                        expires_at=now + timedelta(days=7),
                        last_seen_at=now + timedelta(minutes=index),
                        created_at=now + timedelta(minutes=index),
                    )
                )
                session.add(
                    AuditEvent(
                        actor_type="user",
                        actor_id=admin.id,
                        action=f"page-audit-{index:02d}",
                        target_type="user",
                        target_id=activity_user.id,
                        metadata_json={"repo": f"sheldylew/page-seed-{index:02d}"},
                        created_at=now + timedelta(seconds=index),
                    )
                )
                session.add(
                    GcJob(
                        status="succeeded",
                        requested_by=admin.id,
                        dry_run=False,
                        delete_untagged=False,
                        prune_empty_dirs=False,
                        started_at=now + timedelta(minutes=index),
                        finished_at=now + timedelta(minutes=index, seconds=5),
                        log_output=f"page-seed-job-{index:02d}",
                        created_at=now + timedelta(minutes=index),
                        updated_at=now + timedelta(minutes=index),
                    )
                )

            for index in range(12):
                _seed_repository_state(session, f"sheldylew/page-seed-{index:02d}", tags=("latest",))
            _seed_repository_state(
                session,
                "sheldylew/page-seed-tags",
                tags=tuple(f"v{index:02d}" for index in range(12)),
            )
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200

        users_response = client.get("/api/admin/users")
        activity_response = client.get(f"/api/admin/users/{activity_user.id}")
        sessions_response = client.get("/api/admin/sessions")
        sessions_override_response = client.get("/api/admin/sessions?page_size=3")
        tokens_response = client.get("/api/admin/tokens")
        permissions_response = client.get("/api/admin/permissions")
        audit_response = client.get("/api/admin/audit")
        maintenance_response = client.get("/api/admin/maintenance")
        repos_response = client.get("/api/repos")
        tags_response = client.get("/api/repos/sheldylew/page-seed-tags/tags")

    assert users_response.status_code == 200
    assert users_response.json()["pagination"]["page_size"] == default_page_size
    assert len(users_response.json()["users"]) == default_page_size
    assert users_response.json()["pagination"]["has_next"] is True

    assert activity_response.status_code == 200
    assert activity_response.json()["activity_pagination"]["page_size"] == default_page_size
    assert len(activity_response.json()["recent_activity"]) == default_page_size
    assert activity_response.json()["activity_pagination"]["has_next"] is True

    assert sessions_response.status_code == 200
    assert sessions_response.json()["pagination"]["page_size"] == default_page_size
    assert len(sessions_response.json()["sessions"]) == default_page_size
    assert sessions_response.json()["pagination"]["has_next"] is True

    assert sessions_override_response.status_code == 200
    assert sessions_override_response.json()["pagination"]["page_size"] == 3
    assert len(sessions_override_response.json()["sessions"]) == 3
    assert sessions_override_response.json()["pagination"]["has_next"] is True

    assert tokens_response.status_code == 200
    assert tokens_response.json()["pagination"]["page_size"] == default_page_size
    assert len(tokens_response.json()["tokens"]) == default_page_size
    assert tokens_response.json()["pagination"]["has_next"] is True

    assert permissions_response.status_code == 200
    assert permissions_response.json()["pagination"]["page_size"] == default_page_size
    assert len(permissions_response.json()["permissions"]) == default_page_size
    assert permissions_response.json()["pagination"]["has_next"] is True

    assert audit_response.status_code == 200
    assert audit_response.json()["pagination"]["page_size"] == default_page_size
    assert len(audit_response.json()["events"]) == default_page_size
    assert audit_response.json()["pagination"]["has_next"] is True

    assert maintenance_response.status_code == 200
    assert maintenance_response.json()["pagination"]["page_size"] == default_page_size
    assert len(maintenance_response.json()["jobs"]) == default_page_size
    assert maintenance_response.json()["pagination"]["has_next"] is True

    assert repos_response.status_code == 200
    assert repos_response.json()["pagination"]["page_size"] == default_page_size
    assert len(repos_response.json()["repos"]) == default_page_size
    assert repos_response.json()["pagination"]["has_next"] is True

    assert tags_response.status_code == 200
    assert tags_response.json()["pagination"]["page_size"] == default_page_size
    assert len(tags_response.json()["tags"]) == default_page_size
    assert tags_response.json()["pagination"]["has_next"] is True


def test_repo_list_only_shows_visible_repositories(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "otherns/private")
            _seed_repository_state(session, "sheldylew/app")
            _seed_repository_state(session, "sheldylew/worker")
            user = User(
                username="repo-reader",
                email="repo-reader@example.com",
                password_hash=hash_password("repo-reader-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user.id,
                    repository_pattern="sheldylew/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=False,
                )
            )
            session.commit()

        login = _login(client, "repo-reader", "repo-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos")

    assert response.status_code == 200
    assert response.json()["repos"] == [
        {"name": "sheldylew/app", "visibility": "private"},
        {"name": "sheldylew/worker", "visibility": "private"},
    ]


def test_admin_sees_all_repositories(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "otherns/private")
            _seed_repository_state(session, "sheldylew/app")
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/repos")

    assert response.status_code == 200
    assert response.json()["repos"] == [
        {"name": "otherns/private", "visibility": "private"},
        {"name": "sheldylew/app", "visibility": "private"},
    ]


def test_repo_list_supports_pagination(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            for n in range(1, 13):
                _seed_repository_state(session, f"repo/{n:02d}")
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        page_one = client.get("/api/repos?page=1")
        page_two = client.get("/api/repos?page=2")

    assert page_one.status_code == 200
    assert page_two.status_code == 200
    assert page_one.json()["repos"] == [
        {"name": f"repo/{n:02d}", "visibility": "private"} for n in range(1, 11)
    ]
    assert page_two.json()["repos"] == [
        {"name": f"repo/{n:02d}", "visibility": "private"} for n in range(11, 13)
    ]
    assert page_one.json()["pagination"]["page"] == 1
    assert page_one.json()["pagination"]["page_size"] == 10
    assert page_one.json()["pagination"]["total"] == 12
    assert page_one.json()["pagination"]["has_next"] is True
    assert page_one.json()["pagination"]["has_prev"] is False
    assert page_two.json()["pagination"]["page"] == 2
    assert page_two.json()["pagination"]["has_prev"] is True
    assert page_two.json()["pagination"]["has_next"] is False
    assert page_two.json()["pagination"]["total"] == 12


def test_repo_list_uses_db_state_without_registry_catalog_scan(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(repositories=[f"repo/{n:02d}" for n in range(1, 26)])
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            for n in range(1, 26):
                _seed_repository_state(session, f"repo/{n:02d}")
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/repos?page=1")

    assert response.status_code == 200
    assert fake_registry.list_repositories_bounded_calls == 0
    assert fake_registry.list_tags_calls == []


def test_repo_list_excludes_soft_deleted_repositories(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app")
            _seed_repository_state(session, "sheldylew/deleted", deleted=True)
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/repos?page=1")

    assert response.status_code == 200
    assert response.json()["repos"] == [{"name": "sheldylew/app", "visibility": "private"}]


def test_repo_list_excludes_repositories_without_active_tags(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app")
            _seed_repository_state(session, "sheldylew/empty", tags=())
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/repos?page=1")

    assert response.status_code == 200
    assert response.json()["repos"] == [{"name": "sheldylew/app", "visibility": "private"}]


def test_repository_visibility_update_is_reflected_in_db_backed_repo_list(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "public/app")
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        csrf = login.cookies.get("rcr_csrf")
        first = client.get("/api/repos")
        update = client.post(
            "/api/admin/repositories/visibility",
            json={"repository_name": "public/app", "visibility": "public"},
            headers={"X-CSRF-Token": csrf},
        )
        second = client.get("/api/repos")

    assert first.status_code == 200
    assert update.status_code == 200
    assert second.status_code == 200
    assert first.json()["repos"] == [{"name": "public/app", "visibility": "private"}]
    assert second.json()["repos"] == [{"name": "public/app", "visibility": "public"}]


def test_registry_delete_event_removes_tag_from_db_backed_repo_list(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app")
            _seed_repository_state(session, "sheldylew/gc-me", tags=("old",))
            gc_tag = session.scalar(select(RepositoryTag).join(Repository).where(Repository.name == "sheldylew/gc-me"))
            gc_tag.manifest_digest = "sha256:gone"
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        first = client.get("/api/repos")
        event = client.post(
            "/api/internal/registry-events",
            headers=_registry_event_headers(app),
            json={
                "events": [
                    {
                        "action": "delete",
                        "repository": "sheldylew/gc-me",
                        "target": {
                            "repository": "sheldylew/gc-me",
                            "digest": "sha256:gone",
                        },
                    }
                ]
            },
        )
        second = client.get("/api/repos")

    assert first.status_code == 200
    assert event.status_code == 202
    assert second.status_code == 200
    assert first.json()["repos"] == [
        {"name": "sheldylew/app", "visibility": "private"},
        {"name": "sheldylew/gc-me", "visibility": "private"},
    ]
    assert second.json()["repos"] == [{"name": "sheldylew/app", "visibility": "private"}]


def test_repo_tags_require_pull_permission(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app")
            user = User(
                username="blocked-reader",
                email="blocked-reader@example.com",
                password_hash=hash_password("blocked-reader-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()

        login = _login(client, "blocked-reader", "blocked-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags")

    assert response.status_code == 403


def test_missing_repo_returns_404(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(missing_repos={"sheldylew/missing"})
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="visible-reader",
                email="visible-reader@example.com",
                password_hash=hash_password("visible-reader-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user.id,
                    repository_pattern="sheldylew/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=False,
                )
            )
            session.commit()

        login = _login(client, "visible-reader", "visible-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/missing/tags")

    assert response.status_code == 404


def test_repo_tag_manifest_returns_details(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/app", "latest"): {
                "name": "sheldylew/app",
                "tag": "latest",
                "digest": "sha256:manifest",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [{"digest": "sha256:layer", "size": 42, "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"}],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            }
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("latest",))
            user = User(
                username="manifest-reader",
                email="manifest-reader@example.com",
                password_hash=hash_password("manifest-reader-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user.id,
                    repository_pattern="sheldylew/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=False,
                )
            )
            session.commit()

        login = _login(client, "manifest-reader", "manifest-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags/latest")

    assert response.status_code == 200
    assert response.json()["manifest"]["digest"] == "sha256:manifest"
    assert response.json()["public_registry_origin"] == settings.public_registry_origin


def test_repo_tag_manifest_rejects_soft_deleted_tag_before_registry_fetch(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/app", "gone"): {
                "name": "sheldylew/app",
                "tag": "gone",
                "digest": "sha256:gone",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            }
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("gone",))
            tag_row = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id))
            tag_row.deleted_at = datetime.now(timezone.utc)
            session.commit()
            _grant_reader(session, username="soft-delete-reader", password="soft-delete-reader-pass")

        login = _login(client, "soft-delete-reader", "soft-delete-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags/gone")

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository tag not found."
    assert fake_registry.get_manifest_details_calls == []


def test_repo_tag_history_rejects_soft_deleted_tag_before_registry_fetch(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        histories={
            ("sheldylew/app", "gone"): [
                HistoryVariant(
                    platform="linux/amd64",
                    manifest_digest="sha256:gone",
                    config_digest="sha256:config",
                    created_at=None,
                    entries=[{}],
                )
            ]
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("gone",))
            tag_row = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id))
            tag_row.deleted_at = datetime.now(timezone.utc)
            session.commit()
            _grant_reader(session, username="soft-history-reader", password="soft-history-reader-pass")

        login = _login(client, "soft-history-reader", "soft-history-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags/gone/history")

    assert response.status_code == 404
    assert response.json()["detail"] == "Repository tag not found."
    assert fake_registry.get_tag_history_bounded_calls == []


def test_repo_tags_return_paginated_summary_rows(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient()
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("release",))
            tag = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id))
            tag.manifest_digest = "sha256:abc"
            _seed_manifest_summary(session, repository_name="sheldylew/app", manifest_digest="sha256:abc")
            session.commit()
            _grant_reader(session, username="summary-reader", password="summary-reader-pass")

        login = _login(client, "summary-reader", "summary-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags")

    assert response.status_code == 200
    assert response.json()["sorting"] == {"sort": "created", "direction": "desc"}
    assert response.json()["visibility"] == "private"
    assert response.json()["public_registry_origin"] == settings.public_registry_origin
    assert response.json()["can_manage_visibility"] is False
    assert response.json()["tags"] == [
        {
            "tag": "release",
            "digest": "sha256:abc",
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "total_size": 1048576,
            "architectures": ["linux/amd64", "linux/arm64"],
            "created_at": "2026-05-04T10:20:30Z",
            "history_count": 5,
            "children_truncated": False,
            "history_truncated": False,
            "shared_manifest_tag_count": 1,
            "shared_manifest_tags": ["release"],
        }
    ]
    assert response.json()["pagination"] == {
        "page": 1,
        "page_size": DEFAULT_REPOSITORY_TAGS_PAGE_SIZE,
        "total": 1,
        "has_prev": False,
        "has_next": False,
    }
    assert fake_registry.list_tags_calls == []
    assert fake_registry.resolve_manifest_descriptor_calls == []
    assert fake_registry.get_manifest_details_calls == []


def test_admin_repo_tags_include_repository_visibility(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "public/app", visibility="public")
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/repos/public/app/tags")

    assert response.status_code == 200
    assert response.json()["visibility"] == "public"
    assert response.json()["can_manage_visibility"] is True


def test_repo_tags_return_truncation_metadata(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("one", "two"))
            tag_rows = session.scalars(
                select(RepositoryTag).where(RepositoryTag.repository_id == repository.id).order_by(RepositoryTag.name.asc())
            ).all()
            tag_rows[0].manifest_digest = "sha256:one"
            tag_rows[1].manifest_digest = "sha256:two"
            _seed_manifest_summary(
                session,
                repository_name="sheldylew/app",
                manifest_digest="sha256:one",
                total_size=11,
                architectures=["linux/amd64"],
            )
            _seed_manifest_summary(
                session,
                repository_name="sheldylew/app",
                manifest_digest="sha256:two",
                tag_created_at="2026-05-05T10:20:30Z",
                total_size=22,
                architectures=["linux/arm64"],
            )
            set_app_setting(session, REPOSITORY_TAGS_PAGE_SIZE_KEY, "1")
            session.commit()
            _grant_reader(session, username="trunc-reader", password="trunc-reader-pass")

        login = _login(client, "trunc-reader", "trunc-reader-pass")
        response = client.get("/api/repos/sheldylew/app/tags?page=2")

    assert response.status_code == 200
    assert len(response.json()["tags"]) == 1
    assert response.json()["tags"][0]["tag"] == "one"
    assert response.json()["tags"][0]["digest"] == "sha256:one"
    assert response.json()["truncation"] == {"truncated": True, "returned": 1, "available": 2}
    assert response.json()["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total": 2,
        "has_prev": True,
        "has_next": False,
    }


def test_repo_tags_summary_rows_skip_registry_fetch(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient()
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("release",))
            tag = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id))
            tag.manifest_digest = "sha256:cached"
            _seed_manifest_summary(
                session,
                repository_name="sheldylew/app",
                manifest_digest="sha256:cached",
                total_size=77,
                architectures=["linux/amd64"],
            )
            session.commit()
            _grant_reader(session, username="cache-reader", password="cache-reader-pass")

        login = _login(client, "cache-reader", "cache-reader-pass")
        assert login.status_code == 200
        first = client.get("/api/repos/sheldylew/app/tags")
        second = client.get("/api/repos/sheldylew/app/tags")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["tags"] == second.json()["tags"]
    assert fake_registry.list_tags_calls == []
    assert fake_registry.resolve_manifest_descriptor_calls == []
    assert fake_registry.get_manifest_details_calls == []


def test_repo_tags_shared_digest_uses_single_cached_summary(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("edge", "release"))
            for tag in session.scalars(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id)).all():
                tag.manifest_digest = "sha256:shared"
            _seed_manifest_summary(session, repository_name="sheldylew/app", manifest_digest="sha256:shared", total_size=44)
            session.commit()
            _grant_reader(session, username="shared-reader", password="shared-reader-pass")

        login = _login(client, "shared-reader", "shared-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags")

    assert response.status_code == 200
    tags = response.json()["tags"]
    assert [tag["tag"] for tag in tags] == ["edge", "release"]
    assert [tag["shared_manifest_tag_count"] for tag in tags] == [2, 2]
    assert [tag["shared_manifest_tags"] for tag in tags] == [["edge", "release"], ["edge", "release"]]


def test_repo_tag_manifest_includes_shared_digest_warning_metadata(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/app", "edge"): {
                "name": "sheldylew/app",
                "tag": "edge",
                "digest": "sha256:shared",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            }
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("edge", "release"))
            for tag in session.scalars(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id)).all():
                tag.manifest_digest = "sha256:shared"
            session.commit()
            _grant_reader(session, username="detail-shared-reader", password="detail-shared-reader-pass")

        login = _login(client, "detail-shared-reader", "detail-shared-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags/edge")

    assert response.status_code == 200
    manifest = response.json()["manifest"]
    assert manifest["digest"] == "sha256:shared"
    assert manifest["shared_manifest_tag_count"] == 2
    assert manifest["shared_manifest_tags"] == ["edge", "release"]


def test_repo_tags_are_sorted_by_most_recent_created_first(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("z-old", "a-new"))
            tag_rows = {
                tag.name: tag
                for tag in session.scalars(
                    select(RepositoryTag).where(RepositoryTag.repository_id == repository.id)
                ).all()
            }
            tag_rows["z-old"].pushed_at = datetime(2026, 5, 4, 10, 20, 30, tzinfo=timezone.utc)
            tag_rows["a-new"].pushed_at = datetime(2026, 5, 5, 10, 20, 30, tzinfo=timezone.utc)
            for tag_name, digest in {"z-old": "sha256:old", "a-new": "sha256:new"}.items():
                tag_rows[tag_name].manifest_digest = digest
            _seed_manifest_summary(
                session,
                repository_name="sheldylew/app",
                manifest_digest="sha256:old",
                tag_created_at="2026-05-05T10:20:30Z",
            )
            _seed_manifest_summary(
                session,
                repository_name="sheldylew/app",
                manifest_digest="sha256:new",
                tag_created_at="2026-05-04T10:20:30Z",
            )
            session.commit()
            _grant_reader(session, username="recent-reader", password="recent-reader-pass")

        login = _login(client, "recent-reader", "recent-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags")

    assert response.status_code == 200
    assert [tag["tag"] for tag in response.json()["tags"]] == ["z-old", "a-new"]
    assert response.json()["sorting"] == {"sort": "created", "direction": "desc"}


def test_repo_tags_support_created_and_tag_sorting(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("z-old", "a-new", "middle"))
            tag_rows = {
                tag.name: tag
                for tag in session.scalars(
                    select(RepositoryTag).where(RepositoryTag.repository_id == repository.id)
                ).all()
            }
            tag_rows["z-old"].pushed_at = datetime(2026, 5, 4, 10, 20, 30, tzinfo=timezone.utc)
            tag_rows["middle"].pushed_at = datetime(2026, 5, 5, 10, 20, 30, tzinfo=timezone.utc)
            tag_rows["a-new"].pushed_at = datetime(2026, 5, 6, 10, 20, 30, tzinfo=timezone.utc)
            summaries = {
                "z-old": ("sha256:old", "2026-05-04T10:20:30Z"),
                "middle": ("sha256:middle", "2026-05-05T10:20:30Z"),
                "a-new": ("sha256:new", "2026-05-06T10:20:30Z"),
            }
            for tag_name, (digest, created_at) in summaries.items():
                tag_rows[tag_name].manifest_digest = digest
                _seed_manifest_summary(
                    session,
                    repository_name="sheldylew/app",
                    manifest_digest=digest,
                    tag_created_at=created_at,
                )
            session.commit()
            _grant_reader(session, username="sort-reader", password="sort-reader-pass")

        login = _login(client, "sort-reader", "sort-reader-pass")
        assert login.status_code == 200
        created_asc = client.get("/api/repos/sheldylew/app/tags?sort=created&direction=asc")
        tag_asc = client.get("/api/repos/sheldylew/app/tags?sort=tag&direction=asc")
        tag_desc = client.get("/api/repos/sheldylew/app/tags?sort=tag&direction=desc")

    assert created_asc.status_code == 200
    assert [tag["tag"] for tag in created_asc.json()["tags"]] == ["z-old", "middle", "a-new"]
    assert created_asc.json()["sorting"] == {"sort": "created", "direction": "asc"}
    assert [tag["tag"] for tag in tag_asc.json()["tags"]] == ["a-new", "middle", "z-old"]
    assert tag_asc.json()["sorting"] == {"sort": "tag", "direction": "asc"}
    assert [tag["tag"] for tag in tag_desc.json()["tags"]] == ["z-old", "middle", "a-new"]
    assert tag_desc.json()["sorting"] == {"sort": "tag", "direction": "desc"}


def test_repo_tags_reject_unsupported_sorting(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("latest",))
            session.commit()
            _grant_reader(session, username="bad-sort-reader", password="bad-sort-reader-pass")

        login = _login(client, "bad-sort-reader", "bad-sort-reader-pass")
        assert login.status_code == 200
        bad_sort = client.get("/api/repos/sheldylew/app/tags?sort=size")
        bad_direction = client.get("/api/repos/sheldylew/app/tags?direction=sideways")

    assert bad_sort.status_code == 400
    assert bad_sort.json()["detail"] == "Unsupported tag sort."
    assert bad_direction.status_code == 400
    assert bad_direction.json()["detail"] == "Unsupported tag sort direction."


def test_repo_tags_exclude_soft_deleted_tags(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("gone", "latest"))
            tag_rows = session.scalars(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id)).all()
            for tag in tag_rows:
                if tag.name == "gone":
                    tag.deleted_at = datetime.now(timezone.utc)
                if tag.name == "latest":
                    tag.manifest_digest = "sha256:live"
            _seed_manifest_summary(
                session,
                repository_name="sheldylew/app",
                manifest_digest="sha256:live",
                total_size=55,
                architectures=["linux/amd64"],
            )
            session.commit()
            _grant_reader(session, username="stale-reader", password="stale-reader-pass")

        login = _login(client, "stale-reader", "stale-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags")

    assert response.status_code == 200
    assert response.json()["tags"] == [
        {
            "tag": "latest",
            "digest": "sha256:live",
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "total_size": 55,
            "architectures": ["linux/amd64"],
            "created_at": "2026-05-04T10:20:30Z",
            "history_count": 5,
            "children_truncated": False,
            "history_truncated": False,
            "shared_manifest_tag_count": 1,
            "shared_manifest_tags": ["latest"],
        }
    ]


def test_registry_events_require_internal_bearer_token(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post("/api/internal/registry-events", json={"events": []})

    assert response.status_code == 403
    assert response.json()["detail"] == "Registry event authentication failed."


def test_registry_push_event_warms_cache_using_live_tag_resolution(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        descriptors={
            ("sheldylew/app", "latest"): ("sha256:new", "application/vnd.oci.image.manifest.v1+json"),
        },
        manifests={
            ("sheldylew/app", "latest"): {
                "name": "sheldylew/app",
                "tag": "latest",
                "digest": "sha256:new",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:cfg-new",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 99,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-06T10:20:30Z",
                "history_count": 4,
            }
        },
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        response = client.post(
            "/api/internal/registry-events",
            headers=_registry_event_headers(app),
            json={
                "events": [
                    {
                        "action": "push",
                        "repository": "sheldylew/app",
                        "tag": "latest",
                        "target": {
                            "repository": "sheldylew/app",
                            "digest": "sha256:stale",
                            "mediaType": "application/vnd.oci.image.manifest.v1+json",
                        },
                    }
                ]
            },
        )
        with app.state.session_factory() as session:
            cached_rows = session.scalars(select(CachedManifestSummary)).all()
            inbox_rows = session.scalars(select(RegistryEventInbox)).all()
            repository = session.scalar(select(Repository).where(Repository.name == "sheldylew/app"))
            tag_row = session.scalar(select(RepositoryTag).where(RepositoryTag.name == "latest"))
            storage_usage_stale = session.get(AppSetting, REGISTRY_STORAGE_USAGE_STALE_KEY)

    assert response.status_code == 202
    assert response.json() == {"accepted": 1}
    assert fake_registry.resolve_manifest_descriptor_calls == [("sheldylew/app", "latest")]
    assert fake_registry.get_manifest_details_calls == [("sheldylew/app", "sha256:new")]
    assert len(cached_rows) == 1
    assert cached_rows[0].repository_name == "sheldylew/app"
    assert cached_rows[0].manifest_digest == "sha256:new"
    assert cached_rows[0].total_size == 99
    assert len(inbox_rows) == 1
    assert inbox_rows[0].status == "processed"
    assert repository.deleted_at is None
    assert tag_row.manifest_digest == "sha256:new"
    assert tag_row.deleted_at is None
    assert storage_usage_stale is not None
    assert storage_usage_stale.value == "true"


def test_registry_delete_event_removes_cached_manifest_summary(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("latest",))
            tag_row = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id))
            tag_row.manifest_digest = "sha256:gone"
            _seed_manifest_summary(
                session,
                repository_name="sheldylew/app",
                manifest_digest="sha256:gone",
                total_size=10,
                architectures=["linux/amd64"],
            )
            session.commit()

        response = client.post(
            "/api/internal/registry-events",
            headers=_registry_event_headers(app),
            json={
                "events": [
                    {
                        "action": "delete",
                        "repository": "sheldylew/app",
                        "target": {
                            "repository": "sheldylew/app",
                            "digest": "sha256:gone",
                        },
                    }
                ]
            },
        )
        with app.state.session_factory() as session:
            cached_rows = session.scalars(select(CachedManifestSummary)).all()
            tag_row = session.scalar(select(RepositoryTag).where(RepositoryTag.name == "latest"))
            inbox_rows = session.scalars(select(RegistryEventInbox)).all()
            storage_usage_stale = session.get(AppSetting, REGISTRY_STORAGE_USAGE_STALE_KEY)

    assert response.status_code == 202
    assert response.json() == {"accepted": 1}
    assert cached_rows == []
    assert tag_row.deleted_at is not None
    assert inbox_rows[0].status == "processed"
    assert storage_usage_stale is not None
    assert storage_usage_stale.value == "true"


def test_repo_tag_history_returns_variants(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        histories={
            ("sheldylew/app", "release"): [
                HistoryVariant(
                    platform="linux/amd64",
                    manifest_digest="sha256:amd64",
                    config_digest="sha256:cfg-amd64",
                    created_at="2026-05-04T18:20:30Z",
                    entries=[{"created_by": "amd64 step"}],
                ),
                HistoryVariant(
                    platform="linux/arm64",
                    manifest_digest="sha256:arm64",
                    config_digest="sha256:cfg-arm64",
                    created_at="2026-05-03T09:15:00Z",
                    entries=[{"created_by": "arm64 step 1"}, {"created_by": "arm64 step 2"}],
                ),
            ]
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("release",))
            user = User(
                username="history-reader",
                email="history-reader@example.com",
                password_hash=hash_password("history-reader-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user.id,
                    repository_pattern="sheldylew/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=False,
                )
            )
            session.commit()

        login = _login(client, "history-reader", "history-reader-pass")
        assert login.status_code == 200
        response = client.get("/api/repos/sheldylew/app/tags/release/history")

    assert response.status_code == 200
    assert len(response.json()["variants"]) == 2
    assert response.json()["variants"][0]["platform"] == "linux/amd64"
    assert response.json()["variants"][1]["entry_count"] == 2


def test_repo_tag_history_returns_truncation_metadata(settings) -> None:
    limited_settings = Settings(
        app_env=settings.app_env,
        database_url=settings.database_url,
        registry_internal_url=settings.registry_internal_url,
        registry_storage_root=settings.registry_storage_root,
        compose_project_dir=settings.compose_project_dir,
        registry_service_name=settings.registry_service_name,
        registry_gc_config_path=settings.registry_gc_config_path,
        token_issuer=settings.token_issuer,
        token_service=settings.token_service,
        token_ttl_seconds=settings.token_ttl_seconds,
        public_registry_origin=settings.public_registry_origin,
        auth_private_key_path=settings.auth_private_key_path,
        auth_public_cert_path=settings.auth_public_cert_path,
        internal_api_base_url=settings.internal_api_base_url,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
        admin_email=settings.admin_email,
        manifest_children_max_items=1,
        session_cookie_secure=settings.session_cookie_secure,
        session_lifetime_seconds=settings.session_lifetime_seconds,
    )
    app = create_app(limited_settings)
    fake_registry = FakeRegistryClient(
        histories={
            ("sheldylew/app", "release"): [
                HistoryVariant(platform="linux/amd64", manifest_digest="sha256:amd64", config_digest="sha256:cfg1", created_at=None, entries=[{}]),
                HistoryVariant(platform="linux/arm64", manifest_digest="sha256:arm64", config_digest="sha256:cfg2", created_at=None, entries=[{}]),
            ]
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("release",))
            user = User(
                username="history-trunc",
                email="history-trunc@example.com",
                password_hash=hash_password("history-trunc-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user.id,
                    repository_pattern="sheldylew/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=False,
                )
            )
            session.commit()

        login = _login(client, "history-trunc", "history-trunc-pass")
        response = client.get("/api/repos/sheldylew/app/tags/release/history")

    assert response.status_code == 200
    assert len(response.json()["variants"]) == 1
    assert response.json()["truncation"] == {"truncated": True, "returned": 1, "available": 2}


def test_admin_dashboard_returns_stats_and_activity(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("latest", "release"))
            _seed_repository_state(session, "sheldylew/worker", tags=("stable",))
            user = User(
                username="dashboard-user",
                email="dashboard-user@example.com",
                password_hash=hash_password("dashboard-user-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            session.add(PersonalAccessToken(user_id=user.id, name="cli", token_hash="hash1", token_prefix="pat001"))
            robot = RobotAccount(name="dashboard-bot", description="dashboard", is_active=True)
            session.add(robot)
            session.commit()
            session.refresh(robot)
            session.add(RobotToken(robot_id=robot.id, name="bot-cli", token_hash="hash2", token_prefix="rbt001"))
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/admin/dashboard")

    body = response.json()
    assert response.status_code == 200
    assert body["stats"]["users_total"] == 2
    assert body["stats"]["registry_repositories"] == 2
    assert body["stats"]["registry_tags"] == 3
    assert body["repo_distribution"][0]["name"] == "sheldylew/app"
    assert len(body["provisioning_trend"]["users"]) == 7
    assert body["recent_activity"][0]["title"]
    activity_details = " ".join(event["detail"] for event in body["recent_activity"])
    assert "dashboard-user@example.com" in activity_details
    assert "pat001" not in activity_details
    assert "rbt001" not in activity_details
    assert "Token hidden for non-admin account" in activity_details
    assert "Token hidden for automation account" in activity_details


def test_admin_maintenance_returns_cache_stats(settings) -> None:
    app = create_app(settings)
    now = datetime.now(timezone.utc)
    older_cached = now - timedelta(days=3)
    recent_cached = now - timedelta(hours=12)
    stale_seen = now - timedelta(days=2)
    newest_seen = now - timedelta(hours=1)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("latest", "release"))
            _seed_repository_state(session, "sheldylew/worker")
            session.add(
                RegistryEventInbox(
                    action="push",
                    repository_name="sheldylew/app",
                    tag="queued",
                    digest="sha256:queued",
                    raw_payload={},
                    dedupe_key="push|sheldylew/app|queued|sha256:queued",
                    status="pending",
                    received_at=now,
                )
            )
            session.add(
                RegistryEventInbox(
                    action="push",
                    repository_name="sheldylew/app",
                    tag="failed",
                    digest="sha256:failed",
                    raw_payload={},
                    dedupe_key="push|sheldylew/app|failed|sha256:failed",
                    status="failed",
                    attempts=1,
                    error="boom",
                    received_at=now,
                    processed_at=now,
                )
            )
            session.add(
                RegistryStateRebuildJob(
                    status="succeeded",
                    requested_by=1,
                    repositories_scanned=2,
                    tags_scanned=3,
                    created_at=now,
                    updated_at=now,
                    finished_at=now,
                )
            )
            session.add_all(
                [
                    CachedManifestSummary(
                        repository_name="sheldylew/app",
                        manifest_digest="sha256:one",
                        media_type="application/vnd.oci.image.manifest.v1+json",
                        config_digest="sha256:cfg-one",
                        total_size=10,
                        created_at=None,
                        architectures=["linux/amd64"],
                        history_count=1,
                        children_truncated=False,
                        history_truncated=False,
                        cached_at=older_cached,
                        last_seen_at=stale_seen,
                    ),
                    CachedManifestSummary(
                        repository_name="sheldylew/app",
                        manifest_digest="sha256:two",
                        media_type="application/vnd.oci.image.manifest.v1+json",
                        config_digest="sha256:cfg-two",
                        total_size=11,
                        created_at=None,
                        architectures=["linux/arm64"],
                        history_count=2,
                        children_truncated=False,
                        history_truncated=False,
                        cached_at=recent_cached,
                        last_seen_at=now - timedelta(hours=2),
                    ),
                    CachedManifestSummary(
                        repository_name="sheldylew/worker",
                        manifest_digest="sha256:three",
                        media_type="application/vnd.oci.image.index.v1+json",
                        config_digest="sha256:cfg-three",
                        total_size=12,
                        created_at=None,
                        architectures=["linux/amd64", "linux/arm64"],
                        history_count=3,
                        children_truncated=False,
                        history_truncated=False,
                        cached_at=now - timedelta(hours=6),
                        last_seen_at=newest_seen,
                    ),
                ]
            )
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/admin/maintenance")

    body = response.json()
    assert response.status_code == 200
    assert body["cache"]["summaries_total"] == 3
    assert body["cache"]["repositories_total"] == 2
    assert body["cache"]["seen_last_24h"] == 2
    assert body["cache"]["oldest_cached_at"] == older_cached.isoformat()
    assert body["cache"]["newest_cached_at"] == (now - timedelta(hours=6)).isoformat()
    assert body["cache"]["newest_last_seen_at"] == newest_seen.isoformat()
    assert body["registry_state"]["active_repositories"] == 2
    assert body["registry_state"]["active_tags"] == 3
    assert body["registry_state"]["inbox_queued"] == 1
    assert body["registry_state"]["inbox_failed"] == 1
    assert body["registry_state"]["last_rebuild"]["status"] == "succeeded"
    assert body["rebuild_jobs"][0]["repositories_scanned"] == 2


def test_registry_state_rebuild_requires_csrf(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.post("/api/admin/maintenance/cache/rebuild")

    assert response.status_code == 403


def test_registry_state_rebuild_walks_registry_and_repairs_db_state(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        repositories=["public/app", "sheldylew/worker"],
        tags={"public/app": ["latest"], "sheldylew/worker": ["stable"]},
        descriptors={
            ("public/app", "latest"): ("sha256:public-new", "application/vnd.oci.image.manifest.v1+json"),
            ("sheldylew/worker", "stable"): ("sha256:worker", "application/vnd.oci.image.manifest.v1+json"),
        },
        manifests={
            ("public/app", "latest"): {
                "name": "public/app",
                "tag": "latest",
                "digest": "sha256:public-new",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:public-cfg",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 101,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-07T10:20:30Z",
                "history_count": 1,
            },
            ("sheldylew/worker", "stable"): {
                "name": "sheldylew/worker",
                "tag": "stable",
                "digest": "sha256:worker",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:worker-cfg",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 202,
                "architectures": ["linux/arm64"],
                "created_at": "2026-05-08T10:20:30Z",
                "history_count": 2,
            },
        },
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            public_repo = _seed_repository_state(session, "public/app", tags=("old",), visibility="public")
            old_tag = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == public_repo.id))
            old_tag.manifest_digest = "sha256:old"
            _seed_repository_state(session, "stale/repo", tags=("gone",))
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/cache/rebuild",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            job = session.scalar(select(RegistryStateRebuildJob).order_by(RegistryStateRebuildJob.id.desc()))
            public_repo = session.scalar(select(Repository).where(Repository.name == "public/app"))
            worker_repo = session.scalar(select(Repository).where(Repository.name == "sheldylew/worker"))
            stale_repo = session.scalar(select(Repository).where(Repository.name == "stale/repo"))
            public_latest = session.scalar(
                select(RepositoryTag)
                .join(Repository)
                .where(Repository.name == "public/app", RepositoryTag.name == "latest")
            )
            public_old = session.scalar(
                select(RepositoryTag)
                .join(Repository)
                .where(Repository.name == "public/app", RepositoryTag.name == "old")
            )
            worker_tag = session.scalar(
                select(RepositoryTag)
                .join(Repository)
                .where(Repository.name == "sheldylew/worker", RepositoryTag.name == "stable")
            )
            summaries = session.scalars(
                select(CachedManifestSummary).order_by(CachedManifestSummary.manifest_digest.asc())
            ).all()

    assert response.status_code == 200
    assert response.json()["job"]["status"] == "queued"
    assert job.status == "succeeded"
    assert job.repositories_scanned == 2
    assert job.tags_scanned == 2
    assert job.tags_deleted == 2
    assert public_repo.visibility == "public"
    assert public_repo.deleted_at is None
    assert worker_repo.deleted_at is None
    assert stale_repo.deleted_at is not None
    assert public_latest.manifest_digest == "sha256:public-new"
    assert worker_tag.manifest_digest == "sha256:worker"
    assert public_old.deleted_at is not None
    assert [row.manifest_digest for row in summaries] == ["sha256:public-new", "sha256:worker"]


def test_registry_state_rebuild_reconciles_stale_inbox_rows(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        repositories=["sheldylew/app"],
        tags={"sheldylew/app": ["latest"]},
        descriptors={
            ("sheldylew/app", "latest"): ("sha256:latest", "application/vnd.oci.image.manifest.v1+json"),
        },
        manifests={
            ("sheldylew/app", "latest"): {
                "name": "sheldylew/app",
                "tag": "latest",
                "digest": "sha256:latest",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:latest-cfg",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 101,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-07T10:20:30Z",
                "history_count": 1,
            },
        },
    )
    app.state.registry_client_factory = lambda: fake_registry
    now = datetime.now(timezone.utc)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add_all(
                [
                    RegistryEventInbox(
                        action="push",
                        repository_name="sheldylew/app",
                        tag="old-pending",
                        digest="sha256:old-pending",
                        raw_payload={},
                        dedupe_key="push|sheldylew/app|old-pending|sha256:old-pending",
                        status="pending",
                        received_at=now - timedelta(hours=2),
                    ),
                    RegistryEventInbox(
                        action="delete",
                        repository_name="sheldylew/app",
                        tag="old-processing",
                        digest="sha256:old-processing",
                        raw_payload={},
                        dedupe_key="delete|sheldylew/app|old-processing|sha256:old-processing",
                        status="processing",
                        attempts=1,
                        received_at=now - timedelta(hours=1),
                    ),
                    RegistryEventInbox(
                        action="push",
                        repository_name="sheldylew/app",
                        tag="new-pending",
                        digest="sha256:new-pending",
                        raw_payload={},
                        dedupe_key="push|sheldylew/app|new-pending|sha256:new-pending",
                        status="pending",
                        received_at=now + timedelta(hours=1),
                    ),
                    RegistryEventInbox(
                        action="push",
                        repository_name="sheldylew/app",
                        tag="failed",
                        digest="sha256:failed",
                        raw_payload={},
                        dedupe_key="push|sheldylew/app|failed|sha256:failed",
                        status="failed",
                        attempts=1,
                        error="boom",
                        received_at=now - timedelta(hours=3),
                        processed_at=now - timedelta(hours=3),
                    ),
                ]
            )
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/cache/rebuild",
            headers={"X-CSRF-Token": csrf},
        )
        maintenance_response = client.get("/api/admin/maintenance")

        with app.state.session_factory() as session:
            rows = {
                row.tag: row
                for row in session.scalars(
                    select(RegistryEventInbox).where(RegistryEventInbox.repository_name == "sheldylew/app")
                )
            }
            job = session.scalar(select(RegistryStateRebuildJob).order_by(RegistryStateRebuildJob.id.desc()))
            succeeded_event = session.scalar(
                select(AuditEvent).where(AuditEvent.action == "registry_state_rebuild_succeeded")
            )

    assert response.status_code == 200
    assert job.status == "succeeded"
    assert "inbox reconciliation: 2 stale events reconciled" in job.log_output
    assert succeeded_event.metadata_json["inbox_reconciled"] == 2
    assert rows["old-pending"].status == "reconciled"
    assert rows["old-processing"].status == "reconciled"
    assert rows["old-pending"].processed_at is not None
    assert rows["old-processing"].processed_at is not None
    assert rows["new-pending"].status == "pending"
    assert rows["failed"].status == "failed"
    assert maintenance_response.status_code == 200
    assert maintenance_response.json()["registry_state"]["inbox_queued"] == 1
    assert maintenance_response.json()["registry_state"]["inbox_failed"] == 1


def test_registry_state_rebuild_rejects_active_maintenance_job(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))
            session.add(
                GcJob(
                    status="queued",
                    requested_by=admin.id,
                    dry_run=False,
                    delete_untagged=False,
                    prune_empty_dirs=False,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/maintenance/cache/rebuild",
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "A maintenance job is already queued or running."


def test_admin_dashboard_skips_soft_deleted_registry_state(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("latest", "release"))
            _seed_repository_state(session, "sheldylew/gc-me", deleted=True)
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/admin/dashboard")

    body = response.json()
    assert response.status_code == 200
    assert body["stats"]["registry_repositories"] == 1
    assert body["stats"]["registry_tags"] == 2
    assert body["stats"]["public_pull_tokens_issued"] == 0
    assert body["repo_distribution"] == [{"name": "sheldylew/app", "tag_count": 2}]


def test_admin_dashboard_caps_repository_fanout(settings) -> None:
    limited_settings = Settings(
        app_env=settings.app_env,
        database_url=settings.database_url,
        registry_internal_url=settings.registry_internal_url,
        registry_storage_root=settings.registry_storage_root,
        compose_project_dir=settings.compose_project_dir,
        registry_service_name=settings.registry_service_name,
        registry_gc_config_path=settings.registry_gc_config_path,
        token_issuer=settings.token_issuer,
        token_service=settings.token_service,
        token_ttl_seconds=settings.token_ttl_seconds,
        public_registry_origin=settings.public_registry_origin,
        auth_private_key_path=settings.auth_private_key_path,
        auth_public_cert_path=settings.auth_public_cert_path,
        internal_api_base_url=settings.internal_api_base_url,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
        admin_email=settings.admin_email,
        dashboard_max_repositories=1,
        session_cookie_secure=settings.session_cookie_secure,
        session_lifetime_seconds=settings.session_lifetime_seconds,
    )
    app = create_app(limited_settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app")
            _seed_repository_state(session, "sheldylew/worker")
            session.commit()

        login = _login(client, limited_settings.admin_username, limited_settings.admin_password)
        response = client.get("/api/admin/dashboard")

    body = response.json()
    assert response.status_code == 200
    assert body["repo_distribution_truncation"]["truncated"] is True
    assert body["repo_distribution_truncation"]["returned"] == 1


def test_admin_dashboard_includes_public_pull_counter(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "public/app", visibility="public")
            session.commit()

        public_pull = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull"},
        )
        assert public_pull.status_code == 200

        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200
        response = client.get("/api/admin/dashboard")

    body = response.json()
    assert response.status_code == 200
    assert body["stats"]["public_pull_tokens_issued"] == 1


def test_admin_audit_endpoint_filters_by_actor_and_repo(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        assert login.status_code == 200

        with app.state.session_factory() as session:
            admin = session.scalar(select(User).where(User.username == settings.admin_username))
            session.add(
                AuditEvent(
                    actor_type="user",
                    actor_id=admin.id,
                    action="repository_tag_deleted",
                    target_type="repository_tag",
                    metadata_json={"repo": "sheldylew/app", "tag": "latest"},
                )
            )
            session.add(
                AuditEvent(
                    actor_type="user",
                    actor_id=admin.id,
                    action="repository_storage_pruned",
                    target_type="repository",
                    metadata_json={"repo": "sheldylew/other"},
                )
            )
            session.commit()

        filtered = client.get("/api/admin/audit", params={"actor": settings.admin_username, "repo": "sheldylew/app"})

    assert filtered.status_code == 200
    assert len(filtered.json()["events"]) == 1
    assert filtered.json()["events"][0]["metadata_json"]["repo"] == "sheldylew/app"


def test_delete_tag_requires_delete_permission(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/app", "latest"): {
                "name": "sheldylew/app",
                "tag": "latest",
                "digest": "sha256:manifest",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            }
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("latest",))
            user = User(
                username="delete-blocked",
                email="delete-blocked@example.com",
                password_hash=hash_password("delete-blocked-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()

        login = _login(client, "delete-blocked", "delete-blocked-pass")
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/app/tags/latest/delete",
            json={"confirmation": "sheldylew/app:latest"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 403
    assert fake_registry.deleted_manifests == []


def test_delete_tag_deletes_manifest_and_records_audit(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/app", "latest"): {
                "name": "sheldylew/app",
                "tag": "latest",
                "digest": "sha256:manifest",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            }
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/app", tags=("latest",))
            tag = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id))
            tag.manifest_digest = "sha256:manifest"
            user = User(
                username="delete-allowed",
                email="delete-allowed@example.com",
                password_hash=hash_password("delete-allowed-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            session.add(
                RepositoryPermission(
                    subject_type="user",
                    subject_id=user.id,
                    repository_pattern="sheldylew/*",
                    can_pull=True,
                    can_push=False,
                    can_delete=True,
                )
            )
            session.commit()

        login = _login(client, "delete-allowed", "delete-allowed-pass")
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/app/tags/latest/delete",
            json={"confirmation": "sheldylew/app:latest"},
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            events = session.query(AuditEvent).all()
            tag = session.scalar(select(RepositoryTag).where(RepositoryTag.name == "latest"))
            storage_usage_stale = session.get(AppSetting, REGISTRY_STORAGE_USAGE_STALE_KEY)

    assert response.status_code == 200
    assert fake_registry.deleted_manifests == [("sheldylew/app", "sha256:manifest")]
    assert events[-1].action == "repository_tag_deleted"
    assert tag.deleted_at is not None
    assert storage_usage_stale is not None
    assert storage_usage_stale.value == "true"


def test_admin_can_delete_tag_without_explicit_repo_permission(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/admin-delete", "latest"): {
                "name": "sheldylew/admin-delete",
                "tag": "latest",
                "digest": "sha256:admin-manifest",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            }
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            repository = _seed_repository_state(session, "sheldylew/admin-delete", tags=("latest",))
            tag = session.scalar(select(RepositoryTag).where(RepositoryTag.repository_id == repository.id))
            tag.manifest_digest = "sha256:admin-manifest"
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/admin-delete/tags/latest/delete",
            json={"confirmation": "sheldylew/admin-delete:latest"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 200
    assert fake_registry.deleted_manifests == [("sheldylew/admin-delete", "sha256:admin-manifest")]
    with app.state.session_factory() as session:
        tag = session.scalar(select(RepositoryTag).where(RepositoryTag.name == "latest"))
    assert tag.deleted_at is not None


def test_bulk_delete_tags_deletes_manifests_and_records_audit(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/bulk-delete", "one"): {
                "name": "sheldylew/bulk-delete",
                "tag": "one",
                "digest": "sha256:sheldylew-bulk-delete-one",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config-one",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            },
            ("sheldylew/bulk-delete", "two"): {
                "name": "sheldylew/bulk-delete",
                "tag": "two",
                "digest": "sha256:sheldylew-bulk-delete-two",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config-two",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 64,
                "architectures": ["linux/arm64"],
                "created_at": "2026-05-04T10:25:30Z",
                "history_count": 1,
            },
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/bulk-delete", tags=("one", "two"))
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/bulk-delete/tags/delete",
            json={"tags": ["one", "two"]},
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            events = session.scalars(
                select(AuditEvent).where(AuditEvent.action == "repository_tag_deleted").order_by(AuditEvent.id.asc())
            ).all()
            tags = session.scalars(
                select(RepositoryTag).join(Repository).where(Repository.name == "sheldylew/bulk-delete")
            ).all()
            storage_usage_stale = session.get(AppSetting, REGISTRY_STORAGE_USAGE_STALE_KEY)

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert fake_registry.deleted_manifests == [
        ("sheldylew/bulk-delete", "sha256:sheldylew-bulk-delete-one"),
        ("sheldylew/bulk-delete", "sha256:sheldylew-bulk-delete-two"),
    ]
    assert [event.metadata_json["tag"] for event in events[-2:]] == ["one", "two"]
    assert all(tag.deleted_at is not None for tag in tags)
    assert storage_usage_stale is not None
    assert storage_usage_stale.value == "true"


def test_bulk_delete_tags_requires_delete_permission(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(
        manifests={
            ("sheldylew/bulk-blocked", "latest"): {
                "name": "sheldylew/bulk-blocked",
                "tag": "latest",
                "digest": "sha256:sheldylew-bulk-blocked-latest",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "config_digest": "sha256:config",
                "config_media_type": "application/vnd.oci.image.config.v1+json",
                "layers": [],
                "total_size": 42,
                "architectures": ["linux/amd64"],
                "created_at": "2026-05-04T10:20:30Z",
                "history_count": 1,
            }
        }
    )
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/bulk-blocked", tags=("latest",))
            _grant_reader(session, username="bulk-blocked", password="bulk-blocked-pass")

        login = _login(client, "bulk-blocked", "bulk-blocked-pass")
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/bulk-blocked/tags/delete",
            json={"tags": ["latest"]},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 403
    assert fake_registry.deleted_manifests == []


def test_delete_empty_repository_prunes_storage(settings, temp_workspace) -> None:
    repo_root = temp_workspace / "registry-data"
    repo_path = repo_root / "sheldylew" / "empty"
    repo_path.mkdir(parents=True)
    custom_settings = Settings(
        app_env=settings.app_env,
        database_url=settings.database_url,
        registry_internal_url=settings.registry_internal_url,
        registry_storage_root=str(repo_root),
        compose_project_dir=settings.compose_project_dir,
        registry_service_name=settings.registry_service_name,
        registry_gc_config_path=settings.registry_gc_config_path,
        token_issuer=settings.token_issuer,
        token_service=settings.token_service,
        token_ttl_seconds=settings.token_ttl_seconds,
        public_registry_origin=settings.public_registry_origin,
        auth_private_key_path=settings.auth_private_key_path,
        auth_public_cert_path=settings.auth_public_cert_path,
        internal_api_base_url=settings.internal_api_base_url,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
        admin_email=settings.admin_email,
        session_cookie_secure=settings.session_cookie_secure,
        session_lifetime_seconds=settings.session_lifetime_seconds,
    )
    app = create_app(custom_settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/empty", tags=())
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/empty/delete",
            json={"confirmation": "sheldylew/empty"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 200
    assert repo_path.exists() is False
    with app.state.session_factory() as session:
        repository = session.scalar(select(Repository).where(Repository.name == "sheldylew/empty"))
        storage_usage_stale = session.get(AppSetting, REGISTRY_STORAGE_USAGE_STALE_KEY)
    assert repository.deleted_at is not None
    assert storage_usage_stale is not None
    assert storage_usage_stale.value == "true"


def test_delete_empty_repository_rejects_non_empty_repo(settings) -> None:
    app = create_app(settings)

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            _seed_repository_state(session, "sheldylew/app", tags=("latest",))
            session.commit()

        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/app/delete",
            json={"confirmation": "sheldylew/app"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 409


def test_non_admin_cannot_prune_empty_repository(settings) -> None:
    app = create_app(settings)
    fake_registry = FakeRegistryClient(tags={"sheldylew/empty": []})
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="repo-prune-blocked",
                email="repo-prune-blocked@example.com",
                password_hash=hash_password("repo-prune-blocked-pass"),
                is_admin=False,
                is_active=True,
            )
            session.add(user)
            session.commit()

        login = _login(client, "repo-prune-blocked", "repo-prune-blocked-pass")
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/sheldylew/empty/delete",
            json={"confirmation": "sheldylew/empty"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 403


def test_delete_empty_repository_rejects_traversal_segments(settings, temp_workspace) -> None:
    repo_root = temp_workspace / "registry-data"
    outside_path = temp_workspace / "escape"
    outside_path.mkdir()
    custom_settings = Settings(
        app_env=settings.app_env,
        database_url=settings.database_url,
        registry_internal_url=settings.registry_internal_url,
        registry_storage_root=str(repo_root),
        compose_project_dir=settings.compose_project_dir,
        registry_service_name=settings.registry_service_name,
        registry_gc_config_path=settings.registry_gc_config_path,
        token_issuer=settings.token_issuer,
        token_service=settings.token_service,
        token_ttl_seconds=settings.token_ttl_seconds,
        public_registry_origin=settings.public_registry_origin,
        auth_private_key_path=settings.auth_private_key_path,
        auth_public_cert_path=settings.auth_public_cert_path,
        internal_api_base_url=settings.internal_api_base_url,
        admin_username=settings.admin_username,
        admin_password=settings.admin_password,
        admin_email=settings.admin_email,
        session_cookie_secure=settings.session_cookie_secure,
        session_lifetime_seconds=settings.session_lifetime_seconds,
    )
    app = create_app(custom_settings)
    fake_registry = FakeRegistryClient(tags={"../escape": []})
    app.state.registry_client_factory = lambda: fake_registry

    with TestClient(app) as client:
        login = _login(client, settings.admin_username, settings.admin_password)
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/repos/%2E%2E/escape/delete",
            json={"confirmation": "../escape"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 400
    assert outside_path.exists() is True
