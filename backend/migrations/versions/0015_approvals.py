"""approvals: stage change proposals, sent back status and attorney notes

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-24
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

KINDS = "'DEADLINE_ACTIVATE', 'FORM_EXPORT', 'PACKET_APPROVE', 'MESSAGE_APPROVE'"
STATUSES = "'PENDING_LEGAL_REVIEW', 'APPROVED', 'REJECTED', 'COMMITTED'"


def upgrade() -> None:
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute(f"ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check CHECK (kind IN ({KINDS}, 'STAGE_CHANGE'))")
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_status_check")
    op.execute(f"ALTER TABLE proposals ADD CONSTRAINT proposals_status_check CHECK (status IN ({STATUSES}, 'SENT_BACK'))")
    op.execute(
        """
        CREATE TABLE case_notes (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id text NOT NULL REFERENCES cases (case_id),
            proposal_id text REFERENCES proposals (proposal_id),
            kind text NOT NULL CHECK (kind IN ('DIFFERENT_DATE', 'QUESTION')),
            body text NOT NULL,
            suggested_date date,
            author text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_case_notes_case_id ON case_notes (case_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS case_notes")
    op.execute("UPDATE proposals SET status = 'REJECTED' WHERE status = 'SENT_BACK'")
    op.execute("DELETE FROM proposals WHERE kind = 'STAGE_CHANGE'")
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_status_check")
    op.execute(f"ALTER TABLE proposals ADD CONSTRAINT proposals_status_check CHECK (status IN ({STATUSES}))")
    op.execute("ALTER TABLE proposals DROP CONSTRAINT proposals_kind_check")
    op.execute(f"ALTER TABLE proposals ADD CONSTRAINT proposals_kind_check CHECK (kind IN ({KINDS}))")
