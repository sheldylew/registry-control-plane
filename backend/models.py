from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    personal_access_tokens: Mapped[list["PersonalAccessToken"]] = relationship(back_populates="user")


class PersonalAccessToken(Base):
    __tablename__ = "personal_access_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user: Mapped[User] = relationship(back_populates="personal_access_tokens")


class WebSession(Base):
    __tablename__ = "web_sessions"
    __table_args__ = (
        Index("ix_web_sessions_session_hash", "session_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    user: Mapped[User] = relationship()


class RobotAccount(Base):
    __tablename__ = "robot_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    robot_tokens: Mapped[list["RobotToken"]] = relationship(back_populates="robot")


class RobotToken(Base):
    __tablename__ = "robot_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    robot_id: Mapped[int] = mapped_column(ForeignKey("robot_accounts.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    token_prefix: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    robot: Mapped[RobotAccount] = relationship(back_populates="robot_tokens")


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    tags: Mapped[list["RepositoryTag"]] = relationship(back_populates="repository")


class RepositoryTag(Base):
    __tablename__ = "repository_tags"
    __table_args__ = (
        UniqueConstraint("repository_id", "name", name="uq_repository_tags_repo_name"),
        Index("ix_repository_tags_repo_deleted_name", "repository_id", "deleted_at", "name"),
        Index("ix_repository_tags_digest", "manifest_digest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[Optional[str]] = mapped_column(String(255))
    pushed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    repository: Mapped[Repository] = relationship(back_populates="tags")


class RegistryEventInbox(Base):
    __tablename__ = "registry_event_inbox"
    __table_args__ = (
        Index("ix_registry_event_inbox_status_received_at", "status", "received_at"),
        Index("ix_registry_event_inbox_dedupe_key", "dedupe_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(255))
    digest: Mapped[Optional[str]] = mapped_column(String(255))
    media_type: Mapped[Optional[str]] = mapped_column(String(255))
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RegistryStateRebuildJob(Base):
    __tablename__ = "registry_state_rebuild_jobs"
    __table_args__ = (
        Index("ix_registry_state_rebuild_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    repositories_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repositories_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repositories_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tags_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manifest_summaries_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    log_output: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class CachedManifestSummary(Base):
    __tablename__ = "cached_manifest_summaries"
    __table_args__ = (
        UniqueConstraint("repository_name", "manifest_digest", name="uq_cached_manifest_summary_repo_digest"),
        Index("ix_cached_manifest_summaries_repo_last_seen_at", "repository_name", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest_digest: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[Optional[str]] = mapped_column(String(255))
    config_digest: Mapped[Optional[str]] = mapped_column(String(255))
    total_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    architectures: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    history_count: Mapped[Optional[int]] = mapped_column(Integer)
    children_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    history_truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class RepositoryPermission(Base):
    __tablename__ = "repository_permissions"
    __table_args__ = (
        Index("ix_repository_permissions_subject_lookup", "subject_type", "subject_id"),
        UniqueConstraint("subject_type", "subject_id", "repository_pattern", name="uq_repository_permission_subject_pattern"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    repository_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    can_pull: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_push: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(32))
    target_id: Mapped[Optional[int]] = mapped_column(Integer)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class GcJob(Base):
    __tablename__ = "gc_jobs"
    __table_args__ = (
        Index("ix_gc_jobs_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delete_untagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prune_empty_dirs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bytes_before: Mapped[Optional[int]] = mapped_column(Integer)
    bytes_after: Mapped[Optional[int]] = mapped_column(Integer)
    log_output: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    requester: Mapped[User] = relationship()
