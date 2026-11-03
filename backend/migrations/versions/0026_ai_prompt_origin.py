"""prompts get an origin so document types made in the app are listed as additional document types

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("origin", sa.String(20), nullable=False, server_default="BUILT_IN"))
    op.create_check_constraint("ck_prompts_origin", "prompts", "origin IN ('BUILT_IN', 'ADDITIONAL')")


def downgrade() -> None:
    op.drop_constraint("ck_prompts_origin", "prompts", type_="check")
    op.drop_column("prompts", "origin")
