"""ingest: CLAIM_SOURCE upload outcome and the page of a claim

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-23
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

OUTCOMES = "'PENDING', 'DUPLICATE', 'QUARANTINED', 'SUPERSEDED', 'INVALID', 'USABLE', 'NEEDS_HUMAN_REVIEW', 'READING'"


def upgrade() -> None:
    op.execute("ALTER TABLE uploads DROP CONSTRAINT uploads_outcome_check")
    op.execute(f"ALTER TABLE uploads ADD CONSTRAINT uploads_outcome_check CHECK (outcome IN ({OUTCOMES}, 'CLAIM_SOURCE'))")
    op.execute("ALTER TABLE claims ADD COLUMN page integer")


def downgrade() -> None:
    op.execute("ALTER TABLE claims DROP COLUMN IF EXISTS page")
    op.execute("UPDATE uploads SET outcome = 'NEEDS_HUMAN_REVIEW' WHERE outcome = 'CLAIM_SOURCE'")
    op.execute("ALTER TABLE uploads DROP CONSTRAINT uploads_outcome_check")
    op.execute(f"ALTER TABLE uploads ADD CONSTRAINT uploads_outcome_check CHECK (outcome IN ({OUTCOMES}))")
