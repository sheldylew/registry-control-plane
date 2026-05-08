"""gc jobs

Revision ID: 0003_gc_jobs
Revises: 0002_web_sessions
Create Date: 2026-05-04 16:40:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_gc_jobs"
down_revision = "0002_web_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gc_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("delete_untagged", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("prune_empty_dirs", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("bytes_before", sa.Integer(), nullable=True),
        sa.Column("bytes_after", sa.Integer(), nullable=True),
        sa.Column("log_output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_gc_jobs_status_created_at", "gc_jobs", ["status", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gc_jobs_status_created_at", table_name="gc_jobs")
    op.drop_table("gc_jobs")
