"""registry state read model

Revision ID: 0007_registry_state_read_model
Revises: 0006_cached_manifest_summaries
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_registry_state_read_model"
down_revision = "0006_cached_manifest_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repositories",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("repositories", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repositories", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE repositories SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)")
    with op.batch_alter_table("repositories") as batch_op:
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )

    op.create_table(
        "repository_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("manifest_digest", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["repositories.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("repository_id", "name", name="uq_repository_tags_repo_name"),
    )
    op.create_index(
        "ix_repository_tags_repo_deleted_name",
        "repository_tags",
        ["repository_id", "deleted_at", "name"],
        unique=False,
    )
    op.create_index("ix_repository_tags_digest", "repository_tags", ["manifest_digest"], unique=False)

    op.create_table(
        "registry_event_inbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("tag", sa.String(length=255), nullable=True),
        sa.Column("digest", sa.String(length=255), nullable=True),
        sa.Column("media_type", sa.String(length=255), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_registry_event_inbox_status_received_at",
        "registry_event_inbox",
        ["status", "received_at"],
        unique=False,
    )
    op.create_index("ix_registry_event_inbox_dedupe_key", "registry_event_inbox", ["dedupe_key"], unique=False)

    op.create_table(
        "registry_state_rebuild_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repositories_scanned", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("repositories_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("repositories_deleted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tags_scanned", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tags_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tags_deleted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("manifest_summaries_updated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("log_output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_registry_state_rebuild_jobs_status_created_at",
        "registry_state_rebuild_jobs",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_registry_state_rebuild_jobs_status_created_at", table_name="registry_state_rebuild_jobs")
    op.drop_table("registry_state_rebuild_jobs")
    op.drop_index("ix_registry_event_inbox_dedupe_key", table_name="registry_event_inbox")
    op.drop_index("ix_registry_event_inbox_status_received_at", table_name="registry_event_inbox")
    op.drop_table("registry_event_inbox")
    op.drop_index("ix_repository_tags_digest", table_name="repository_tags")
    op.drop_index("ix_repository_tags_repo_deleted_name", table_name="repository_tags")
    op.drop_table("repository_tags")
    op.drop_column("repositories", "deleted_at")
    op.drop_column("repositories", "last_seen_at")
    op.drop_column("repositories", "updated_at")
