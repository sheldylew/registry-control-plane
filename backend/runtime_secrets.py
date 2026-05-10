from __future__ import annotations

import os
import secrets
from pathlib import Path

from backend.config import Settings


def ensure_registry_notifications_token(settings: Settings) -> str:
    token_path = Path(settings.registry_notifications_token_path)
    if token_path.exists():
        try:
            existing = token_path.read_text(encoding="utf-8").strip()
        except OSError:
            existing = ""
        if existing:
            return existing

    raw_token = secrets.token_urlsafe(32)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(raw_token + "\n", encoding="utf-8")
    os.chmod(token_path, 0o600)
    return raw_token
