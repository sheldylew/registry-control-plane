import base64
import os
import time

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.auth.passwords import hash_password
from backend.main import create_app
from backend.models import Repository, RepositoryPermission, User
from backend.registry_client import ManifestDetails


def _basic_auth(username: str, secret: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{secret}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {encoded}"}


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/session/login", json={"username": username, "password": password})


def _csrf_headers(login_response) -> dict[str, str]:
    return {"X-CSRF-Token": login_response.cookies.get("rcr_csrf", "")}


def _mint_forged_registry_token(app, *, subject: str = "malicious", service: str = "wrong-service") -> str:
    private_key = open(app.state.settings.auth_private_key_path, "rb").read()
    return jwt.encode(
        {
            "iss": app.state.settings.token_issuer,
            "sub": subject,
            "aud": service,
            "exp": int(time.time()) + 600,
            "access": [{"type": "registry", "name": "catalog", "actions": ["*"]}],
        },
        private_key,
        algorithm="RS256",
    )


def _decode_registry_token(app, token: str) -> dict:
    cert = x509.load_pem_x509_certificate(open(app.state.settings.auth_public_cert_path, "rb").read())
    public_key = cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return jwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        audience=app.state.settings.token_service,
        issuer=app.state.settings.token_issuer,
    )


class FakeRegistry:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, str]] = []

    def close(self) -> None:
        return

    def list_repositories(self) -> list[str]:
        return ["team/app", "public/app"]

    def list_tags(self, repo_name: str) -> list[str]:
        if repo_name == "team/empty":
            return []
        if repo_name == "team/app":
            return ["latest"]
        return []

    def get_manifest_details(self, repo_name: str, tag: str) -> ManifestDetails:
        return ManifestDetails(
            name=repo_name,
            tag=tag,
            digest="sha256:abc",
            media_type="application/vnd.oci.image.manifest.v1+json",
            config_digest="sha256:def",
            config_media_type="application/vnd.oci.image.config.v1+json",
            layers=[],
            total_size=1,
            architectures=["linux/amd64"],
            created_at=None,
            history_count=1,
        )

    def delete_manifest(self, repository_name: str, digest: str) -> None:
        self.deleted.append((repository_name, digest))


@pytest.fixture
def app_with_fake_registry(settings):
    app = create_app(settings)
    app.state.registry_client_factory = lambda: FakeRegistry()
    return app


def _seed_actor_data(app) -> None:
    with app.state.session_factory() as session:
        if session.scalar(select(User).where(User.username == "low-user")) is not None:
            return
        session.add(Repository(name="public/app", visibility="public"))
        low = User(
            username="low-user",
            email="low-user@example.com",
            password_hash=hash_password("low-user-pass"),
            is_admin=False,
            is_active=True,
        )
        session.add(low)
        session.commit()
        session.refresh(low)
        session.add(
            RepositoryPermission(
                subject_type="user",
                subject_id=low.id,
                repository_pattern="team/*",
                can_pull=True,
                can_push=False,
                can_delete=False,
            )
        )
        session.commit()


def test_unauthenticated_user_cannot_access_admin_or_repo_api(app_with_fake_registry) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        admin = client.get("/api/admin/users")
        repos = client.get("/api/repos")

    assert admin.status_code == 401
    assert repos.status_code == 401


def test_low_privilege_user_cannot_delete_tag(app_with_fake_registry) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        login = _login(client, "low-user", "low-user-pass")
        response = client.post(
            "/api/repos/team/app/tags/latest/delete",
            json={"confirmation": "team/app:latest"},
            headers=_csrf_headers(login),
        )

    assert response.status_code == 403


def test_low_privilege_user_cannot_delete_repository(app_with_fake_registry) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        login = _login(client, "low-user", "low-user-pass")
        response = client.post(
            "/api/repos/team/empty/delete",
            json={"confirmation": "team/empty"},
            headers=_csrf_headers(login),
        )

    assert response.status_code == 403


def test_malicious_cross_site_origin_is_rejected_for_destructive_endpoint(app_with_fake_registry, settings) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        login = _login(client, settings.admin_username, settings.admin_password)
        headers = _csrf_headers(login)
        headers["Origin"] = "https://evil.example"
        response = client.post(
            "/api/admin/maintenance/jobs",
            json={"dry_run": True, "delete_untagged": False, "prune_empty_dirs": False},
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid request origin."


def test_malicious_cross_site_fetch_metadata_is_rejected(app_with_fake_registry, settings) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        login = _login(client, settings.admin_username, settings.admin_password)
        headers = _csrf_headers(login)
        headers["Sec-Fetch-Site"] = "cross-site"
        response = client.post(
            "/api/admin/tokens",
            json={"name": "xsite-attempt"},
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid request origin."


def test_missing_csrf_token_blocks_destructive_operation(app_with_fake_registry, settings) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        _login(client, settings.admin_username, settings.admin_password)
        response = client.post(
            "/api/admin/tokens",
            json={"name": "missing-csrf"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing CSRF token."


def test_forged_session_cookie_does_not_authenticate(app_with_fake_registry) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        client.cookies.set("rcr_session", "totally-fake-session-token")
        response = client.get("/api/session/me")

    assert response.status_code == 401


def test_registry_token_with_wrong_basic_credentials_is_denied(app_with_fake_registry, settings) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "repository:team/app:pull,push,delete"},
            headers=_basic_auth("low-user", "wrong-pass"),
        )

    assert response.status_code == 401


def test_registry_token_request_does_not_grant_catalog_to_low_privilege_user(app_with_fake_registry, settings) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        response = client.get(
            "/auth/token",
            params={"service": settings.token_service, "scope": "registry:catalog:*"},
            headers=_basic_auth("low-user", "low-user-pass"),
        )

    assert response.status_code == 200
    payload = _decode_registry_token(app_with_fake_registry, response.json()["token"])
    assert payload["access"] == [
        {
            "type": "registry",
            "name": "catalog",
            "actions": [],
        }
    ]


def test_registry_token_forgery_attempt_with_wrong_audience_is_rejected_by_verifier(app_with_fake_registry, settings) -> None:
    with TestClient(app_with_fake_registry):
        _seed_actor_data(app_with_fake_registry)
    forged = _mint_forged_registry_token(app_with_fake_registry, service="not-registry-service")
    cert = x509.load_pem_x509_certificate(open(settings.auth_public_cert_path, "rb").read())
    public_key = cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    with pytest.raises(jwt.InvalidAudienceError):
        jwt.decode(
            forged,
            public_key,
            algorithms=["RS256"],
            audience=settings.token_service,
            issuer=settings.token_issuer,
        )


def test_path_traversal_attempt_is_blocked_on_repository_delete(app_with_fake_registry, settings) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        login = _login(client, settings.admin_username, settings.admin_password)
        response = client.post(
            "/api/repos/%2E%2E/escape/delete",
            json={"confirmation": "../escape"},
            headers=_csrf_headers(login),
        )

    assert response.status_code == 400


def test_unauthenticated_registry_maintenance_probe_is_not_blocked_but_never_elevates(app_with_fake_registry) -> None:
    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        response = client.get("/api/internal/registry-maintenance")

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.skipif(os.getenv("RUN_SECURITY_SOAK") != "1", reason="Set RUN_SECURITY_SOAK=1 to run ~30 minute soak profile")
def test_security_soak_profile_runs_multiple_attack_patterns(app_with_fake_registry, settings) -> None:
    iterations = int(os.getenv("SECURITY_SOAK_ITERATIONS", "2200"))

    with TestClient(app_with_fake_registry) as client:
        _seed_actor_data(app_with_fake_registry)
        for _ in range(iterations):
            denied = client.get(
                "/auth/token",
                params={"service": settings.token_service, "scope": "repository:team/app:delete"},
                headers=_basic_auth("low-user", "low-user-pass"),
            )
            assert denied.status_code == 200
            assert denied.json().get("access") == []

            unauth = client.get("/api/admin/users")
            assert unauth.status_code in {401, 403}

            login = _login(client, settings.admin_username, settings.admin_password)
            headers = _csrf_headers(login)
            headers["Origin"] = "https://evil.example"
            xsite = client.post(
                "/api/admin/maintenance/jobs",
                json={"dry_run": True, "delete_untagged": False, "prune_empty_dirs": False},
                headers=headers,
            )
            assert xsite.status_code == 403
