"""user soft delete

Revision ID: 0008_user_soft_delete
Revises: 0007_registry_state_read_model
Create Date: 2026-05-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_user_soft_delete"
down_revision = "0007_registry_state_read_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_by", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("deleted_username", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "deleted_username")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
