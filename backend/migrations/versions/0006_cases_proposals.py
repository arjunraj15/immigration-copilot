"""cases: proposals waiting for legal review

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-23
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE proposal_number_seq")
    op.execute(
        """
        CREATE TABLE proposals (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            proposal_id text NOT NULL UNIQUE DEFAULT 'ACT-' || lpad(nextval('proposal_number_seq')::text, 6, '0'),
            case_id text NOT NULL REFERENCES cases (case_id),
            kind text NOT NULL CHECK (kind IN ('DEADLINE_ACTIVATE', 'FORM_EXPORT', 'PACKET_APPROVE', 'MESSAGE_APPROVE')),
            status text NOT NULL DEFAULT 'PENDING_LEGAL_REVIEW' CHECK (status IN (
                'PENDING_LEGAL_REVIEW', 'APPROVED', 'REJECTED', 'COMMITTED')),
            idempotency_key text NOT NULL UNIQUE,
            target_type text,
            target_id text,
            value jsonb NOT NULL,
            evidence_ids text[] NOT NULL DEFAULT '{}',
            proposed_by text NOT NULL,
            reviewed_by text,
            review_reason text,
            committed_by text,
            proposed_at timestamptz NOT NULL DEFAULT now(),
            reviewed_at timestamptz,
            committed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_proposals_case ON proposals (case_id)")
    op.execute("CREATE INDEX ix_proposals_status ON proposals (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS proposals CASCADE")
    op.execute("DROP SEQUENCE IF EXISTS proposal_number_seq")
