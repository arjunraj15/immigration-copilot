"""uploads keep the date and text a Zoom note file states about itself, so the timeline dates it by the call

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-24
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE uploads ADD COLUMN occurred_at timestamptz, ADD COLUMN note_text text")


def downgrade() -> None:
    op.execute("ALTER TABLE uploads DROP COLUMN note_text, DROP COLUMN occurred_at")
