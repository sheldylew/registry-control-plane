from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import CachedManifestSummary, Repository, RepositoryPermission, RepositoryTag


ROOT = Path(__file__).resolve().parents[2]

# v0.0.17 shipped with the cached manifest summary schema. The registry state
# read model is the next revision and must upgrade live databases in place.
PREVIOUS_RELEASE_REVISION = "0006_cached_manifest_summaries"


def _alembic_config() -> Config:
    config = Config(str(ROOT / "backend/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend/alembic"))
    return config


def test_upgrade_from_previous_release_preserves_state_and_adds_registry_read_model(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'upgrade.db'}"
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _alembic_config()

    command.upgrade(config, PREVIOUS_RELEASE_REVISION)

    engine = create_engine(database_url, future=True)
    now = datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users (id, username, email, password_hash, is_admin, is_active, created_at, updated_at)
                VALUES
                    (1, 'admin', 'admin@example.com', 'hash', 1, 1, :now, :now),
                    (2, 'reader', 'reader@example.com', 'hash', 0, 1, :now, :now)
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO repositories (id, name, visibility, created_at)
                VALUES
                    (1, 'public/app', 'public', :now),
                    (2, 'private/app', 'private', :now)
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO repository_permissions (
                    id,
                    subject_type,
                    subject_id,
                    repository_pattern,
                    can_pull,
                    can_push,
                    can_delete,
                    created_at
                )
                VALUES (1, 'user', 2, 'private/*', 1, 0, 0, :now)
                """
            ),
            {"now": now},
        )
        connection.execute(
            text(
                """
                INSERT INTO cached_manifest_summaries (
                    id,
                    repository_name,
                    manifest_digest,
                    media_type,
                    config_digest,
                    total_size,
                    created_at,
                    architectures,
                    history_count,
                    children_truncated,
                    history_truncated,
                    cached_at,
                    last_seen_at
                )
                VALUES (
                    1,
                    'public/app',
                    'sha256:old',
                    'application/vnd.oci.image.manifest.v1+json',
                    'sha256:config',
                    128,
                    :now,
                    '[\"amd64\"]',
                    3,
                    0,
                    0,
                    :now,
                    :now
                )
                """
            ),
            {"now": now},
        )
    engine.dispose()

    command.upgrade(config, "head")

    upgraded_engine = create_engine(database_url, future=True)
    inspector = inspect(upgraded_engine)
    assert {"repository_tags", "registry_event_inbox", "registry_state_rebuild_jobs"}.issubset(
        set(inspector.get_table_names())
    )
    repository_columns = {column["name"] for column in inspector.get_columns("repositories")}
    assert {"updated_at", "last_seen_at", "deleted_at"}.issubset(repository_columns)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    assert {"deleted_at", "deleted_by", "deleted_username"}.issubset(user_columns)

    with Session(upgraded_engine) as db:
        public_repo = db.scalar(select(Repository).where(Repository.name == "public/app"))
        private_repo = db.scalar(select(Repository).where(Repository.name == "private/app"))
        assert public_repo is not None
        assert private_repo is not None
        assert public_repo.visibility == "public"
        assert private_repo.visibility == "private"
        assert public_repo.updated_at is not None
        assert private_repo.updated_at is not None
        assert public_repo.deleted_at is None
        assert private_repo.deleted_at is None

        permission = db.scalar(select(RepositoryPermission).where(RepositoryPermission.subject_id == 2))
        assert permission is not None
        assert permission.repository_pattern == "private/*"
        assert permission.can_pull is True

        summary = db.scalar(
            select(CachedManifestSummary).where(
                CachedManifestSummary.repository_name == "public/app",
                CachedManifestSummary.manifest_digest == "sha256:old",
            )
        )
        assert summary is not None
        assert summary.total_size == 128
        assert summary.architectures == ["amd64"]

        public_repo.tags.append(
            RepositoryTag(
                name="latest",
                manifest_digest="sha256:old",
                media_type="application/vnd.oci.image.manifest.v1+json",
                pushed_at=now,
                last_seen_at=now,
            )
        )
        private_repo.tags.append(
            RepositoryTag(
                name="stale",
                manifest_digest="sha256:stale",
                media_type="application/vnd.oci.image.manifest.v1+json",
                pushed_at=now,
                last_seen_at=now,
                deleted_at=now,
            )
        )
        db.commit()

        active_repo_names = db.scalars(
            select(Repository.name)
            .join(RepositoryTag)
            .where(Repository.deleted_at.is_(None), RepositoryTag.deleted_at.is_(None))
            .order_by(Repository.name)
            .distinct()
        ).all()
        assert active_repo_names == ["public/app"]

        db.add(
            RepositoryTag(
                repository_id=public_repo.id,
                name="latest",
                manifest_digest="sha256:duplicate",
                last_seen_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
