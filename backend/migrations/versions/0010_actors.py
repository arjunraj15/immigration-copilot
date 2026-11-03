"""actors: operations and legal users kept apart from the cases they are assigned to

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-23
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE actors (
            label text PRIMARY KEY,
            role text NOT NULL CHECK (role IN ('OPS', 'LEGAL'))
        )
        """
    )
    op.execute(
        """
        INSERT INTO actors (label, role)
        SELECT assigned_ops_user, 'OPS' FROM cases
        UNION SELECT assigned_legal_reviewer, 'LEGAL' FROM cases
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE actors")
