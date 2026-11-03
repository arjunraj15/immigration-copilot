"""value matches: the gate now decides names and employers as well as addresses, so the table is per field

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-24
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE address_matches RENAME TO value_matches")
    op.execute("ALTER TABLE value_matches ADD COLUMN field text NOT NULL DEFAULT 'mailing_address'")
    op.execute("ALTER TABLE value_matches DROP CONSTRAINT address_matches_key_a_key_b_key")
    op.execute("ALTER TABLE value_matches ADD CONSTRAINT value_matches_field_key_a_key_b_key UNIQUE (field, key_a, key_b)")


def downgrade() -> None:
    op.execute("ALTER TABLE value_matches DROP CONSTRAINT value_matches_field_key_a_key_b_key")
    op.execute("DELETE FROM value_matches WHERE field <> 'mailing_address'")
    op.execute("ALTER TABLE value_matches DROP COLUMN field")
    op.execute("ALTER TABLE value_matches ADD CONSTRAINT address_matches_key_a_key_b_key UNIQUE (key_a, key_b)")
    op.execute("ALTER TABLE value_matches RENAME TO address_matches")
