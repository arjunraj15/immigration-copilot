"""additional client fields, extra Form draft inputs that users add from the AI tab

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-24
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE additional_form_fields (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            target text NOT NULL UNIQUE,
            label text NOT NULL,
            value_type text NOT NULL DEFAULT 'string' CHECK (value_type IN ('string', 'date', 'number')),
            enabled boolean NOT NULL DEFAULT true,
            created_by text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE additional_form_fields")
