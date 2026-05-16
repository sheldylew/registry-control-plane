from pathlib import Path

from backend.registry_config import render_registry_config
from backend.runtime_secrets import ensure_registry_notifications_token


def test_render_registry_config_uses_configured_public_origin(settings) -> None:
    template = Path("docker/registry-config.yml.tmpl").read_text(encoding="utf-8")
    notification_token = ensure_registry_notifications_token(settings)

    rendered = render_registry_config(template, settings, registry_notifications_token=notification_token)

    assert "host: http://localhost:8080" in rendered
    assert "relativeurls: true" in rendered
    assert "realm: http://localhost:8080/auth/token" in rendered
    assert f"service: {settings.token_service}" in rendered
    assert f"issuer: {settings.token_issuer}" in rendered
    assert "notifications:" in rendered
    assert "url: http://api:8000/api/internal/registry-events" in rendered
    assert f"- Bearer {notification_token}" in rendered
    assert "ignoredmediatypes:" in rendered
    assert "mediatypes:" in rendered
    assert "- application/octet-stream" in rendered
    assert "actions:" in rendered
    assert "- pull" in rendered
    assert "- mount" in rendered
