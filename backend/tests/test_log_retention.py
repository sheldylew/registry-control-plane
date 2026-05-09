from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.audit import record_audit_event
from backend.config import Settings
from backend.log_retention import utcnow
from backend.main import create_app
from backend.models import AuditEvent, GcJob, PersonalAccessToken, RobotAccount, RobotToken, User, WebSession


def test_startup_prunes_old_audit_events_and_completed_gc_jobs(settings) -> None:
    app = create_app(settings)
    stale_time = utcnow() - timedelta(days=settings.log_retention_days + 1)

    with TestClient(app):
        with app.state.session_factory() as session:
            session.add(
                AuditEvent(
                    actor_type="system",
                    action="old_event",
                    created_at=stale_time,
                )
            )
            session.add(
                GcJob(
                    status="succeeded",
                    requested_by=1,
                    finished_at=stale_time,
                    created_at=stale_time,
                    updated_at=stale_time,
                )
            )
            session.commit()

        app_with_existing_data = create_app(settings)
        with TestClient(app_with_existing_data):
            with app_with_existing_data.state.session_factory() as session:
                assert session.scalars(select(AuditEvent)).all() == []
                assert session.scalars(select(GcJob)).all() == []


def test_startup_prunes_stale_sessions_and_token_records(settings) -> None:
    app = create_app(settings)
    stale_session_time = utcnow() - timedelta(days=settings.web_session_retention_days + 1)
    stale_token_time = utcnow() - timedelta(days=settings.token_record_retention_days + 1)

    with TestClient(app):
        with app.state.session_factory() as session:
            user = session.scalars(select(User).order_by(User.id.asc())).first()
            robot = RobotAccount(name="stale-bot", description="stale token owner")
            session.add(robot)
            session.flush()
            session.add(
                WebSession(
                    user_id=user.id,
                    session_hash="stale-session-hash",
                    csrf_token="stale-csrf-token",
                    expires_at=stale_session_time,
                    last_seen_at=stale_session_time,
                    created_at=stale_session_time,
                )
            )
            session.add(
                PersonalAccessToken(
                    user_id=user.id,
                    name="stale-pat",
                    token_hash="stale-pat-hash",
                    token_prefix="stale-pat",
                    expires_at=stale_token_time,
                    created_at=stale_token_time,
                )
            )
            session.add(
                RobotToken(
                    robot_id=robot.id,
                    name="stale-robot-token",
                    token_hash="stale-robot-token-hash",
                    token_prefix="stale-robot",
                    revoked_at=stale_token_time,
                    created_at=stale_token_time,
                )
            )
            session.commit()

        app_with_existing_data = create_app(settings)
        with TestClient(app_with_existing_data):
            with app_with_existing_data.state.session_factory() as session:
                assert session.scalars(select(WebSession).where(WebSession.session_hash == "stale-session-hash")).all() == []
                assert session.scalars(select(PersonalAccessToken).where(PersonalAccessToken.name == "stale-pat")).all() == []
                assert session.scalars(select(RobotToken).where(RobotToken.name == "stale-robot-token")).all() == []


def test_new_audit_write_prunes_old_logs(settings) -> None:
    app = create_app(settings)
    stale_time = utcnow() - timedelta(days=settings.log_retention_days + 1)

    with TestClient(app):
        with app.state.session_factory() as session:
            session.add(
                AuditEvent(
                    actor_type="system",
                    action="old_event",
                    created_at=stale_time,
                )
            )
            session.add(
                GcJob(
                    status="failed",
                    requested_by=1,
                    finished_at=stale_time,
                    created_at=stale_time,
                    updated_at=stale_time,
                )
            )
            session.commit()

            record_audit_event(
                session,
                action="fresh_event",
                actor_type="system",
                retention_days=settings.log_retention_days,
            )

        with app.state.session_factory() as session:
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()
            jobs = session.scalars(select(GcJob)).all()

    assert [event.action for event in events] == ["fresh_event"]
    assert jobs == []


def test_settings_reject_non_positive_log_retention(settings) -> None:
    try:
        Settings(
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
            log_retention_days=0,
        )
    except ValueError as exc:
        assert "LOG_RETENTION_DAYS" in str(exc)
    else:
        raise AssertionError("Expected settings validation to reject non-positive log retention.")
