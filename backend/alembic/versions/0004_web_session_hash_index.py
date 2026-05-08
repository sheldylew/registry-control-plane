"""add explicit web session hash index

Revision ID: 0004_web_session_hash_index
Revises: 0003_gc_jobs
Create Date: 2026-05-07
"""

from alembic import op


revision = "0004_web_session_hash_index"
down_revision = "0003_gc_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_web_sessions_session_hash", "web_sessions", ["session_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_web_sessions_session_hash", table_name="web_sessions")
