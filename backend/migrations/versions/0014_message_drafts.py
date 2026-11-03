"""replies: message drafts that are never sent

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-23
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE message_drafts (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            draft_id text NOT NULL UNIQUE,
            case_id text NOT NULL REFERENCES cases (case_id),
            kind text NOT NULL CHECK (kind IN ('STATUS_REPLY', 'REFUSAL', 'MISSING_FIELDS')),
            channel text NOT NULL CHECK (channel IN ('WHATSAPP', 'EMAIL')),
            subject text,
            body text NOT NULL CHECK (btrim(body) <> ''),
            reply_to_source_id text,
            source_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            triage jsonb,
            status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'PENDING_LEGAL_REVIEW', 'APPROVED', 'REJECTED')),
            proposal_id text,
            created_by text NOT NULL,
            send_status text NOT NULL DEFAULT 'DRAFT_NOT_SENT' CHECK (send_status = 'DRAFT_NOT_SENT'),
            idempotency_key text NOT NULL UNIQUE,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_message_drafts_case_id ON message_drafts (case_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS message_drafts")
