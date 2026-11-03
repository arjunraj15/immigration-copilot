"""fact states: the computed state of each form field, stored when a case changes so a read never rebuilds it

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-24
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE fact_states (
            case_id text NOT NULL,
            field text NOT NULL,
            state jsonb NOT NULL,
            computed_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (case_id, field)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE fact_states")
