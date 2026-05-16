import base64
from datetime import datetime, timezone

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.metrics import snapshot as metrics_snapshot
from backend.models import AuditEvent, Repository, RepositoryPermission, RobotAccount, User
from backend.rate_limit import FixedWindowRateLimiter


def _basic_auth(username: str, secret: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{secret}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _decode_token(app, token: str, audience: str) -> dict:
    cert = x509.load_pem_x509_certificate(
        app.state.settings and open(app.state.settings.auth_public_cert_path, "rb").read()
    )
    public_key = cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience=audience,
        issuer=app.state.settings.token_issuer,
    )


def test_auth_token_issues_jwt_for_admin_password(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:pull,push"},
            headers=_basic_auth(settings.admin_username, settings.admin_password),
        )

        with app.state.session_factory() as session:
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["sub"] == settings.admin_username
    assert payload["aud"] == settings.token_service
    assert payload["access"][0]["actions"] == ["pull", "push"]
    assert events[-1].action == "registry_token_issued"
    assert events[-1].metadata_json["granted_scope"][0]["actions"] == ["pull", "push"]
    assert metrics_snapshot()["registry_auth_token_requests_total"] == 1
    assert metrics_snapshot()["registry_auth_scope_grants_total"] == 2


def test_auth_token_intersects_requested_actions(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            user = User(
                username="repo-user",
                email="repo-user@example.com",
                password_hash=hash_password("repo-pass-123"),
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

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:pull,push"},
            headers=_basic_auth("repo-user", "repo-pass-123"),
        )

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["access"][0]["actions"] == ["pull"]


def test_auth_token_allows_anonymous_pull_for_public_repository(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(Repository(name="public/app", visibility="public"))
            session.commit()

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull"},
        )

        with app.state.session_factory() as session:
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["sub"] == "anonymous"
    assert payload["access"][0]["actions"] == ["pull"]
    assert events[-1].action == "registry_token_issued"
    assert events[-1].actor_type == "anonymous"
    assert events[-1].actor_id is None
    assert metrics_snapshot()["registry_public_pull_tokens_issued_total"] == 1


def test_auth_token_treats_empty_basic_public_pull_as_anonymous(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(Repository(name="public/app", visibility="public"))
            session.commit()

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull"},
            headers=_basic_auth("", ""),
        )

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["sub"] == "anonymous"
    assert payload["access"][0]["actions"] == ["pull"]


def test_auth_token_falls_back_to_anonymous_for_stale_basic_public_pull(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(Repository(name="public/app", visibility="public"))
            session.commit()

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull"},
            headers=_basic_auth("stale-user", "stale-secret"),
        )

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["sub"] == "anonymous"
    assert payload["access"][0]["actions"] == ["pull"]


def test_auth_token_denies_anonymous_pull_for_soft_deleted_public_repository(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(
                Repository(
                    name="public/app",
                    visibility="public",
                    deleted_at=datetime.now(timezone.utc),
                )
            )
            session.commit()

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Basic authentication is required."


def test_auth_token_rejects_stale_basic_public_push_request(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(Repository(name="public/app", visibility="public"))
            session.commit()

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull,push"},
            headers=_basic_auth("stale-user", "stale-secret"),
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid registry credentials."


def test_auth_token_requires_basic_auth_for_anonymous_push_on_public_repository(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(Repository(name="public/app", visibility="public"))
            session.commit()

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull,push"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Basic authentication is required."


def test_auth_token_accepts_pat_credentials(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        csrf = login.cookies.get("rcr_csrf")
        created = client.post(
            "/api/admin/tokens",
            json={"name": "cli"},
            headers={"X-CSRF-Token": csrf},
        )
        raw_token = created.json()["raw_token"]
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:pull"},
            headers=_basic_auth(settings.admin_username, raw_token),
        )

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["sub"] == settings.admin_username


def test_auth_token_accepts_robot_token_credentials(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        csrf = login.cookies.get("rcr_csrf")
        created_robot = client.post(
            "/api/admin/robots",
            json={"name": "ci-bot", "description": "CI robot"},
            headers={"X-CSRF-Token": csrf},
        )
        robot_id = created_robot.json()["robot"]["id"]
        created_token = client.post(
            f"/api/admin/robots/{robot_id}/tokens",
            json={"name": "ci"},
            headers={"X-CSRF-Token": csrf},
        )
        raw_token = created_token.json()["raw_token"]

        with app.state.session_factory() as session:
            robot = session.query(RobotAccount).filter(RobotAccount.id == robot_id).one()
            session.add(
                RepositoryPermission(
                    subject_type="robot",
                    subject_id=robot.id,
                    repository_pattern="builds/*",
                    can_pull=True,
                    can_push=True,
                    can_delete=False,
                )
            )
            session.commit()

        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:builds/app:pull,push"},
            headers=_basic_auth("ci-bot", raw_token),
        )

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["sub"] == "ci-bot"
    assert payload["access"][0]["actions"] == ["pull", "push"]


def test_auth_token_supports_account_alias(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            "/auth/token",
            params={
                "account": settings.admin_username,
                "service": settings.token_service,
                "scope": "repository:sheldylew/app:pull",
            },
            headers=_basic_auth(settings.admin_username, settings.admin_password),
        )

    assert response.status_code == 200


def test_auth_token_normalizes_repository_plugin_scopes(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository(plugin):sheldylew/app:pull"},
            headers=_basic_auth(settings.admin_username, settings.admin_password),
        )

    assert response.status_code == 200
    payload = _decode_token(app, response.json()["token"], settings.token_service)
    assert payload["access"][0]["type"] == "repository"


def test_auth_token_rejects_unknown_scope_types(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "unknown:sheldylew/app:pull"},
            headers=_basic_auth(settings.admin_username, settings.admin_password),
        )

    assert response.status_code == 400
    assert "Unsupported scope resource type" in response.json()["detail"]


def test_auth_token_rejects_invalid_scope_actions(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:admin"},
            headers=_basic_auth(settings.admin_username, settings.admin_password),
        )

    assert response.status_code == 400
    assert "Invalid repository scope actions" in response.json()["detail"]


def test_auth_token_denial_writes_audit_event_without_secret(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:pull"},
            headers=_basic_auth(settings.admin_username, "bad-secret"),
        )

        with app.state.session_factory() as session:
            events = session.scalars(select(AuditEvent).order_by(AuditEvent.id.asc())).all()

    assert response.status_code == 401
    assert events[-1].action == "registry_token_denied"
    assert "bad-secret" not in str(events[-1].metadata_json)
    assert metrics_snapshot()["registry_auth_token_denied_total"] == 1


def test_auth_token_rate_limits_repeated_invalid_credentials(settings) -> None:
    app = create_app(settings)
    app.state.auth_token_rate_limiter = FixedWindowRateLimiter(max_attempts=2, window_seconds=3600)

    with TestClient(app) as client:
        first = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:pull"},
            headers=_basic_auth(settings.admin_username, "bad-secret"),
        )
        second = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:pull"},
            headers=_basic_auth(settings.admin_username, "bad-secret"),
        )
        third = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:sheldylew/app:pull"},
            headers=_basic_auth(settings.admin_username, "bad-secret"),
        )

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert 3590 <= int(third.headers["retry-after"]) <= 3600


def test_metrics_endpoint_returns_counters(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            session.add(Repository(name="public/app", visibility="public"))
            session.commit()

        client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:public/app:pull"},
        )
        client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "registry_ui_logins_total 1" in response.text
    assert "registry_auth_token_requests_total 1" in response.text
    assert "registry_public_pull_tokens_issued_total 1" in response.text
