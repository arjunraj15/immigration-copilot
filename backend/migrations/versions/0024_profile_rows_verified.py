"""profile rows are human verified as the kit has them: any row stored as IMPORTED goes back to HUMAN_VERIFIED

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-24
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE profile_fields SET verification_state = 'HUMAN_VERIFIED' WHERE verification_state = 'IMPORTED'")


def downgrade() -> None:
    pass
