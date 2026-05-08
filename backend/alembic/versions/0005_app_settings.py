"""app settings

Revision ID: 0005_app_settings
Revises: 0004_web_session_hash_index
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_app_settings"
down_revision = "0004_web_session_hash_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
