from __future__ import annotations

import os
import sys
import secrets
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/srv")

from backend.auth.signing_material import bootstrap_signing_material
from backend.config import load_settings
from backend.registry_config import render_registry_config
from backend.runtime_secrets import ensure_registry_notifications_token


APP_UID = int(os.getenv("APP_UID", "10001"))
APP_GID = int(os.getenv("APP_GID", "10001"))
REGISTRY_RENDERED_CONFIG_PATH = Path(
    os.getenv("REGISTRY_RENDERED_CONFIG_PATH", "/registry-config/config.yml")
)
REGISTRY_CONFIG_TEMPLATE_PATH = Path(
    os.getenv("REGISTRY_CONFIG_TEMPLATE_PATH", "/srv/docker/registry-config.yml.tmpl")
)


def _chown_tree(path: Path, *, uid: int, gid: int) -> None:
    if not path.exists():
        return
    os.chown(path, uid, gid)
    if not path.is_dir():
        return
    for root, dirnames, filenames in os.walk(path):
        root_path = Path(root)
        os.chown(root_path, uid, gid)
        for dirname in dirnames:
            os.chown(root_path / dirname, uid, gid)
        for filename in filenames:
            os.chown(root_path / filename, uid, gid)


def _render_registry_config(settings) -> None:
    template = REGISTRY_CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8")
    public_origin = settings.public_registry_origin or "http://localhost:8080"
    rendered = render_registry_config(
        template,
        settings,
        public_registry_origin=public_origin,
        registry_notifications_token=ensure_registry_notifications_token(settings),
    )
    REGISTRY_RENDERED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_RENDERED_CONFIG_PATH.write_text(rendered, encoding="utf-8")
    os.chmod(REGISTRY_RENDERED_CONFIG_PATH, 0o644)
    os.chown(REGISTRY_RENDERED_CONFIG_PATH, APP_UID, APP_GID)


def _normalize_registry_config_permissions() -> None:
    REGISTRY_RENDERED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    os.chown(REGISTRY_RENDERED_CONFIG_PATH.parent, APP_UID, APP_GID)
    os.chmod(REGISTRY_RENDERED_CONFIG_PATH.parent, 0o755)
    if REGISTRY_RENDERED_CONFIG_PATH.exists():
        os.chown(REGISTRY_RENDERED_CONFIG_PATH, APP_UID, APP_GID)
        os.chmod(REGISTRY_RENDERED_CONFIG_PATH, 0o644)


def _normalize_signing_material_permissions(settings) -> None:
    private_key = Path(settings.auth_private_key_path)
    public_cert = Path(settings.auth_public_cert_path)
    private_key.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(private_key.parent, 0o700)
    if private_key.exists():
        os.chmod(private_key, 0o600)
    if public_cert.exists():
        os.chmod(public_cert, 0o644)


def _env_bootstrap_available(settings) -> bool:
    values = [
        settings.admin_username,
        settings.admin_password,
        settings.admin_email,
        settings.public_registry_origin,
    ]
    return all(value is not None and value.strip() for value in values)


def _ensure_setup_token(settings, *, setup_is_required: bool):
    token_path = Path(settings.setup_token_path)
    if not setup_is_required:
        if token_path.exists():
            token_path.unlink()
        return None

    if token_path.exists():
        return None

    raw_token = secrets.token_urlsafe(32)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token_path.write_text(
        json.dumps({"token_hash": token_hash, "created_at": datetime.now(timezone.utc).isoformat()}) + "\n",
        encoding="utf-8",
    )
    os.chmod(token_path, 0o600)
    return raw_token


def main() -> None:
    settings = load_settings()
    setup_complete_marker = Path(settings.setup_complete_marker_path)
    _chown_tree(Path("/data"), uid=APP_UID, gid=APP_GID)
    _chown_tree(Path("/var/lib/registry"), uid=APP_UID, gid=APP_GID)
    _chown_tree(Path(settings.auth_private_key_path).parent, uid=APP_UID, gid=APP_GID)
    _chown_tree(Path(settings.auth_public_cert_path).parent, uid=APP_UID, gid=APP_GID)
    _normalize_registry_config_permissions()
    if not setup_complete_marker.exists() or not REGISTRY_RENDERED_CONFIG_PATH.exists():
        _render_registry_config(settings)
    _normalize_registry_config_permissions()
    _normalize_signing_material_permissions(settings)
    bootstrap_signing_material(settings)
    raw_setup_token = _ensure_setup_token(
        settings,
        setup_is_required=not setup_complete_marker.exists() and not _env_bootstrap_available(settings),
    )
    if raw_setup_token:
        print("Registry Control Plane setup is required.", flush=True)
        print("Open /setup and use this one-time setup token:", flush=True)
        print(raw_setup_token, flush=True)
    _chown_tree(Path(settings.auth_private_key_path), uid=APP_UID, gid=APP_GID)
    _chown_tree(Path(settings.auth_public_cert_path), uid=APP_UID, gid=APP_GID)
    _chown_tree(Path(settings.auth_bootstrap_marker_path), uid=APP_UID, gid=APP_GID)
    _chown_tree(Path(settings.setup_token_path), uid=APP_UID, gid=APP_GID)
    _chown_tree(Path(settings.setup_complete_marker_path), uid=APP_UID, gid=APP_GID)
    _chown_tree(Path(settings.registry_notifications_token_path), uid=APP_UID, gid=APP_GID)


if __name__ == "__main__":
    main()
