"""prompt enabled flag and soft delete

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("prompts", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("prompts", "deleted_at")
    op.drop_column("prompts", "enabled")
