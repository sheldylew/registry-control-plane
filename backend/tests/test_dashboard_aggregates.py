from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api import routes as api_routes
from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.models import AuditEvent, PersonalAccessToken, RegistryEventInbox, RobotAccount, RobotToken, User


@pytest.fixture(autouse=True)
def dashboard_cache_state():
    api_routes._dashboard_cache.clear()
    yield
    api_routes._dashboard_cache.clear()


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/session/login", json={"username": username, "password": password})


def _dashboard(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        yield app, client


def _get_dashboard(client: TestClient, settings):
    login = _login(client, settings.admin_username, settings.admin_password)
    assert login.status_code == 200
    response = client.get("/api/admin/dashboard")
    assert response.status_code == 200
    return response.json()


def _user(
    username: str,
    *,
    is_admin: bool = False,
    is_active: bool = True,
    deleted_at=None,
    created_at=None,
) -> User:
    return User(
        username=username,
        email=f"{username}@example.com",
        password_hash=hash_password(f"{username}-pass"),
        is_admin=is_admin,
        is_active=is_active,
        deleted_at=deleted_at,
        created_at=created_at or datetime.now(timezone.utc),
    )


def test_dashboard_pat_active_counts_unrevoked_even_expired_or_soft_deleted_owner(settings) -> None:
    now = datetime.now(timezone.utc)

    for app, client in _dashboard(settings):
        with app.state.session_factory() as session:
            active_user = _user("dashboard-pat-active")
            deleted_user = _user("dashboard-pat-deleted", deleted_at=now)
            session.add_all([active_user, deleted_user])
            session.flush()
            session.add_all(
                [
                    PersonalAccessToken(
                        user_id=active_user.id,
                        name="active",
                        token_hash="dash-pat-active-hash",
                        token_prefix="dashpa1",
                        revoked_at=None,
                    ),
                    PersonalAccessToken(
                        user_id=active_user.id,
                        name="expired",
                        token_hash="dash-pat-expired-hash",
                        token_prefix="dashpa2",
                        expires_at=now - timedelta(days=1),
                        revoked_at=None,
                    ),
                    PersonalAccessToken(
                        user_id=deleted_user.id,
                        name="soft-deleted-owner",
                        token_hash="dash-pat-deleted-hash",
                        token_prefix="dashpa3",
                        revoked_at=None,
                    ),
                    PersonalAccessToken(
                        user_id=active_user.id,
                        name="revoked",
                        token_hash="dash-pat-revoked-hash",
                        token_prefix="dashpa4",
                        revoked_at=now,
                    ),
                ]
            )
            session.commit()

        body = _get_dashboard(client, settings)

    assert body["stats"]["pats_active"] == 3


def test_dashboard_provisioning_user_buckets_exclude_soft_deleted_users(settings) -> None:
    now = datetime.now(timezone.utc)

    for app, client in _dashboard(settings):
        with app.state.session_factory() as session:
            session.add_all(
                [
                    _user("dashboard-bucket-active", created_at=now),
                    _user("dashboard-bucket-deleted", deleted_at=now, created_at=now),
                ]
            )
            session.commit()

        body = _get_dashboard(client, settings)

    assert sum(bucket["count"] for bucket in body["provisioning_trend"]["users"]) == 2


def test_dashboard_pull_token_counting_requires_repository_pull_scope(settings) -> None:
    now = datetime.now(timezone.utc)

    def audit_event(key: str, metadata_json: dict | None) -> AuditEvent:
        return AuditEvent(
            actor_type="user",
            actor_id=None,
            action="registry_token_issued",
            target_type="registry_token",
            target_id=None,
            metadata_json=metadata_json,
            created_at=now + timedelta(seconds=len(key)),
        )

    for app, client in _dashboard(settings):
        with app.state.session_factory() as session:
            session.add_all(
                [
                    audit_event(
                        "pull",
                        {"granted_scope": [{"type": "repository", "name": "team/app", "actions": ["pull"]}]},
                    ),
                    audit_event(
                        "pull-push",
                        {"granted_scope": [{"type": "repository", "name": "team/app", "actions": ["pull", "push"]}]},
                    ),
                    audit_event(
                        "push-only",
                        {"granted_scope": [{"type": "repository", "name": "team/app", "actions": ["push"]}]},
                    ),
                    audit_event(
                        "registry",
                        {"granted_scope": [{"type": "registry", "name": "catalog", "actions": ["pull"]}]},
                    ),
                    audit_event("missing-scope", {}),
                ]
            )
            session.commit()

        body = _get_dashboard(client, settings)

    assert body["stats"]["pull_tokens_issued"] == 2
    assert sum(bucket["count"] for bucket in body["registry_activity_trend"]["pull_tokens"]) == 2


def test_dashboard_deletion_buckets_include_audited_deletes_without_double_counting_notifications(settings) -> None:
    now = datetime.now(timezone.utc)

    for app, client in _dashboard(settings):
        with app.state.session_factory() as session:
            session.add_all(
                [
                    AuditEvent(
                        actor_type="user",
                        actor_id=None,
                        action="repository_tag_deleted",
                        target_type="repository_tag",
                        metadata_json={"repo": "team/app", "tag": "latest", "digest": "sha256:deleted"},
                        created_at=now,
                    ),
                    RegistryEventInbox(
                        action="delete",
                        repository_name="team/app",
                        tag="latest",
                        digest="sha256:deleted",
                        raw_payload={},
                        dedupe_key="delete|team/app|latest|sha256:deleted",
                        status="processed",
                        received_at=now,
                        processed_at=now,
                    ),
                    AuditEvent(
                        actor_type="user",
                        actor_id=None,
                        action="repository_storage_pruned",
                        target_type="repository",
                        metadata_json={"repo": "team/empty", "removed": True},
                        created_at=now,
                    ),
                ]
            )
            session.commit()

        body = _get_dashboard(client, settings)

    assert sum(bucket["count"] for bucket in body["registry_activity_trend"]["deletions"]) == 2


def test_dashboard_recent_activity_is_capped_and_redacts_token_prefixes(settings) -> None:
    now = datetime.now(timezone.utc)
    pat_prefixes = [f"patsecret{index}" for index in range(6)]
    robot_prefixes = [f"rbtsecret{index}" for index in range(6)]

    for app, client in _dashboard(settings):
        with app.state.session_factory() as session:
            user = _user("dashboard-redacted-user", created_at=now - timedelta(minutes=30))
            robot = RobotAccount(
                name="dashboard-redacted-bot",
                description="redaction bot",
                is_active=True,
                created_at=now - timedelta(minutes=30),
            )
            session.add_all([user, robot])
            session.flush()
            for index, prefix in enumerate(pat_prefixes):
                session.add(
                    PersonalAccessToken(
                        user_id=user.id,
                        name=f"pat-{index}",
                        token_hash=f"dash-redacted-pat-hash-{index}",
                        token_prefix=prefix,
                        created_at=now + timedelta(seconds=index),
                    )
                )
            for index, prefix in enumerate(robot_prefixes):
                session.add(
                    RobotToken(
                        robot_id=robot.id,
                        name=f"robot-{index}",
                        token_hash=f"dash-redacted-robot-hash-{index}",
                        token_prefix=prefix,
                        created_at=now + timedelta(seconds=20 + index),
                    )
                )
            session.commit()

        body = _get_dashboard(client, settings)

    recent_activity = body["recent_activity"]
    serialized_activity = str(recent_activity)
    assert len(recent_activity) == 8
    for prefix in [*pat_prefixes, *robot_prefixes]:
        assert prefix not in serialized_activity
    assert "Token hidden for non-admin account" in serialized_activity
    assert "Token hidden for automation account" in serialized_activity


def test_dashboard_cache_reuses_payload_inside_five_minute_ttl(settings, monkeypatch) -> None:
    monkeypatch.setattr(api_routes.time, "monotonic", lambda: 1000.0)

    for app, client in _dashboard(settings):
        body = _get_dashboard(client, settings)
        assert body["stats"]["users_total"] == 1

        with app.state.session_factory() as session:
            session.add(_user("dashboard-cache-stale"))
            session.commit()

        monkeypatch.setattr(api_routes.time, "monotonic", lambda: 1299.0)
        cached_body = _get_dashboard(client, settings)

    assert cached_body["stats"]["users_total"] == 1


def test_dashboard_cache_refreshes_after_five_minute_ttl(settings, monkeypatch) -> None:
    monkeypatch.setattr(api_routes.time, "monotonic", lambda: 1000.0)

    for app, client in _dashboard(settings):
        body = _get_dashboard(client, settings)
        assert body["stats"]["users_total"] == 1

        with app.state.session_factory() as session:
            session.add(_user("dashboard-cache-refresh"))
            session.commit()

        monkeypatch.setattr(api_routes.time, "monotonic", lambda: 1301.0)
        refreshed_body = _get_dashboard(client, settings)

    assert refreshed_body["stats"]["users_total"] == 2
