from pathlib import Path

from backend.registry_config import render_registry_config


def test_render_registry_config_uses_configured_public_origin(settings) -> None:
    template = Path("docker/registry-config.yml.tmpl").read_text(encoding="utf-8")

    rendered = render_registry_config(template, settings)

    assert "realm: http://localhost:8080/auth/token" in rendered
    assert f"service: {settings.token_service}" in rendered
    assert f"issuer: {settings.token_issuer}" in rendered
