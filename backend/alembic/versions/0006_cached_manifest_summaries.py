"""cached manifest summaries

Revision ID: 0006_cached_manifest_summaries
Revises: 0005_app_settings
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_cached_manifest_summaries"
down_revision = "0005_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cached_manifest_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("manifest_digest", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=255)),
        sa.Column("config_digest", sa.String(length=255)),
        sa.Column("total_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("architectures", sa.JSON(), nullable=False),
        sa.Column("history_count", sa.Integer()),
        sa.Column("children_truncated", sa.Boolean(), nullable=False),
        sa.Column("history_truncated", sa.Boolean(), nullable=False),
        sa.Column("cached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repository_name", "manifest_digest", name="uq_cached_manifest_summary_repo_digest"),
    )
    op.create_index(
        "ix_cached_manifest_summaries_repo_last_seen_at",
        "cached_manifest_summaries",
        ["repository_name", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cached_manifest_summaries_repo_last_seen_at", table_name="cached_manifest_summaries")
    op.drop_table("cached_manifest_summaries")
