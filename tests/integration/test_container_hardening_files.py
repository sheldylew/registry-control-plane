from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_compose_file_contains_runtime_hardening() -> None:
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'cap_drop:\n      - ALL' in compose_text
    assert 'security_opt:\n      - no-new-privileges:true' in compose_text
    assert 'read_only: true' in compose_text
    assert 'user: "10001:10001"' in compose_text
    assert 'user: "101:101"' in compose_text
    assert '- "${RCP_HTTP_BIND:-127.0.0.1:8080}:8080"' in compose_text
    assert "condition: service_healthy" in compose_text
    assert "healthcheck:" in compose_text
    assert 'PUBLIC_REGISTRY_ORIGIN: ${PUBLIC_REGISTRY_ORIGIN:-}' in compose_text
    assert 'SETUP_TOKEN_PATH: /data/setup-token.json' in compose_text
    assert 'ADMIN_PASSWORD: ${ADMIN_PASSWORD:-}' in compose_text
    assert 'APP_BUILD_TIME: ${APP_BUILD_TIME:-}' in compose_text
    assert 'APP_REVISION: ${APP_REVISION:-dev}' in compose_text


def test_dockerfile_runs_api_and_web_as_non_root() -> None:
    dockerfile_text = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile_text.count("USER 10001:10001") == 2
    assert "--chown=10001:10001" in dockerfile_text
    assert "useradd --uid 10001" not in dockerfile_text
    assert "adduser -S -D -H -u 10001" not in dockerfile_text
