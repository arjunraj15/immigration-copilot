"""prompt runs keep the full call trace, zlib compressed JSON, written when the run ends

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-24
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE prompt_runs ADD COLUMN trace bytea")


def downgrade() -> None:
    op.execute("ALTER TABLE prompt_runs DROP COLUMN trace")
