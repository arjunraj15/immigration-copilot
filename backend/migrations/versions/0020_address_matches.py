"""address matches: whether two differently written addresses are the same place, decided once by the AI gate

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-24
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE address_matches (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            key_a text NOT NULL,
            key_b text NOT NULL,
            same boolean NOT NULL,
            reason text,
            prompt_run_id integer,
            decided_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (key_a, key_b),
            CHECK (key_a < key_b)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE address_matches")
