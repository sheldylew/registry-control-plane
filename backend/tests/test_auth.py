from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.auth.passwords import hash_password, verify_password
from backend.auth.pats import authenticate_personal_access_token, issue_personal_access_token
from backend.auth.sessions import authenticate_session, create_session, revoke_session
from backend.main import create_app
from backend.models import PersonalAccessToken, User, WebSession


def test_password_hashes_verify_correctly() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", password_hash) is True


def test_wrong_password_fails() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("wrong password", password_hash) is False


def test_pat_raw_value_is_never_stored(db_session) -> None:
    user = User(
        username="pat-owner",
        email="pat-owner@example.com",
        password_hash=hash_password("local-pass"),
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    issued = issue_personal_access_token(db_session, user_id=user.id, name="cli")
    db_session.commit()

    stored = db_session.scalar(select(PersonalAccessToken).where(PersonalAccessToken.user_id == user.id))

    assert stored is not None
    assert issued.raw_token not in stored.token_hash
    assert stored.token_hash != issued.raw_token


def test_pat_prefix_lookup_works(db_session) -> None:
    user = User(
        username="prefix-owner",
        email="prefix-owner@example.com",
        password_hash=hash_password("local-pass"),
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    issued = issue_personal_access_token(db_session, user_id=user.id, name="cli")
    db_session.commit()

    token = authenticate_personal_access_token(db_session, issued.raw_token)

    assert token is not None
    assert token.token_prefix == issued.token_prefix


def test_revoked_pat_cannot_authenticate(db_session) -> None:
    user = User(
        username="revoked-owner",
        email="revoked-owner@example.com",
        password_hash=hash_password("local-pass"),
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    issued = issue_personal_access_token(db_session, user_id=user.id, name="cli")
    db_session.commit()

    token = authenticate_personal_access_token(db_session, issued.raw_token)
    assert token is not None
    token.revoked_at = datetime.now(timezone.utc)
    db_session.commit()

    assert authenticate_personal_access_token(db_session, issued.raw_token) is None


def test_expired_pat_cannot_authenticate(db_session) -> None:
    user = User(
        username="expired-owner",
        email="expired-owner@example.com",
        password_hash=hash_password("local-pass"),
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    issued = issue_personal_access_token(
        db_session,
        user_id=user.id,
        name="cli",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db_session.commit()

    assert authenticate_personal_access_token(db_session, issued.raw_token) is None


def test_creating_pat_shows_token_once(settings) -> None:
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/api/session/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        csrf = login.cookies.get("rcr_csrf")
        response = client.post(
            "/api/admin/tokens",
            json={"name": "cli"},
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["raw_token"].startswith("rcr_pat_")
    assert body["token"]["token_prefix"] in body["raw_token"]


def test_token_list_only_shows_prefix_not_secret(settings) -> None:
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
        response = client.get("/api/admin/tokens")

    assert response.status_code == 200
    token = response.json()["tokens"][0]
    assert "raw_token" not in token
    assert raw_token not in str(token)


def test_revoking_pat_prevents_later_auth(settings) -> None:
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
        body = created.json()
        revoke = client.post(
            f"/api/admin/tokens/{body['token']['id']}/revoke",
            headers={"X-CSRF-Token": csrf},
        )

        with app.state.session_factory() as session:
            token = authenticate_personal_access_token(session, body["raw_token"])

    assert revoke.status_code == 200
    assert token is None


def test_authenticate_session_matches_only_requested_hash(db_session, settings) -> None:
    user = User(
        username="session-owner",
        email="session-owner@example.com",
        password_hash=hash_password("local-pass"),
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    first = create_session(db_session, user=user, settings=settings)
    second = create_session(db_session, user=user, settings=settings)

    authenticated = authenticate_session(db_session, second.raw_token)

    assert authenticated is not None
    matched_session, matched_user = authenticated
    assert matched_session.session_hash == db_session.scalar(
        select(WebSession.session_hash).where(WebSession.csrf_token == second.csrf_token)
    )
    assert matched_user.id == user.id
    assert authenticate_session(db_session, "bogus-session-token") is None
    assert first.raw_token != second.raw_token


def test_revoke_session_marks_only_matching_hash(db_session, settings) -> None:
    user = User(
        username="revoke-owner",
        email="revoke-owner@example.com",
        password_hash=hash_password("local-pass"),
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    first = create_session(db_session, user=user, settings=settings)
    second = create_session(db_session, user=user, settings=settings)

    revoke_session(db_session, first.raw_token)

    sessions = db_session.scalars(select(WebSession).order_by(WebSession.id.asc())).all()
    assert sessions[0].revoked_at is not None
    assert sessions[1].revoked_at is None
    assert authenticate_session(db_session, first.raw_token) is None
    assert authenticate_session(db_session, second.raw_token) is not None
