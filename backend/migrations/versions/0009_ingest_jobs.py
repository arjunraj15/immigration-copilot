"""ingest: jobs table so background reads survive a restart

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE jobs (
            id text PRIMARY KEY,
            kind text NOT NULL CHECK (kind IN ('ANALYSE', 'AUTO_READ')),
            case_id text NOT NULL REFERENCES cases (case_id),
            actor text NOT NULL,
            status text NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED')),
            total integer NOT NULL,
            done integer NOT NULL DEFAULT 0,
            events jsonb NOT NULL DEFAULT '[]',
            workflow_before text,
            reason text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX ix_jobs_case_id ON jobs (case_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS jobs")
