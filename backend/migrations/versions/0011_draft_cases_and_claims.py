"""cases: DRAFT workflow status, claims from intake text and a note on profile fields

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-23
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

STATUSES = "'NEW', 'ANALYSING', 'IN_PROGRESS', 'WITH_ATTORNEY', 'INFO_REQUESTED', 'APPROVED', 'REJECTED', 'APPLIED'"


def upgrade() -> None:
    op.execute("ALTER TABLE case_workflows DROP CONSTRAINT case_workflows_status_check")
    op.execute(f"ALTER TABLE case_workflows ADD CONSTRAINT case_workflows_status_check CHECK (status IN ({STATUSES}, 'DRAFT'))")
    op.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
    op.execute("ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('ANALYSE', 'AUTO_READ', 'INTAKE'))")
    op.execute("ALTER TABLE profile_fields ADD COLUMN note text")
    op.execute(
        """
        CREATE TABLE claims (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id text NOT NULL REFERENCES cases (case_id),
            source_id text NOT NULL,
            field_name text NOT NULL,
            value text NOT NULL,
            quote text NOT NULL,
            verified boolean NOT NULL DEFAULT false CHECK (NOT verified),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_claims_case_id ON claims (case_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS claims")
    op.execute("ALTER TABLE profile_fields DROP COLUMN IF EXISTS note")
    op.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
    op.execute("ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('ANALYSE', 'AUTO_READ'))")
    op.execute("UPDATE case_workflows SET status = 'NEW' WHERE status = 'DRAFT'")
    op.execute("ALTER TABLE case_workflows DROP CONSTRAINT case_workflows_status_check")
    op.execute(f"ALTER TABLE case_workflows ADD CONSTRAINT case_workflows_status_check CHECK (status IN ({STATUSES}))")
