"""ingest: per page record, extracted fields on reads and the READING upload outcome

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

OUTCOMES = "'PENDING', 'DUPLICATE', 'QUARANTINED', 'SUPERSEDED', 'INVALID', 'USABLE', 'NEEDS_HUMAN_REVIEW'"


def upgrade() -> None:
    op.execute("ALTER TABLE uploads DROP CONSTRAINT uploads_outcome_check")
    op.execute(f"ALTER TABLE uploads ADD CONSTRAINT uploads_outcome_check CHECK (outcome IN ({OUTCOMES}, 'READING'))")
    op.execute("ALTER TABLE document_reads ADD COLUMN extracted jsonb")
    op.execute(
        """
        CREATE TABLE document_pages (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            upload_id text NOT NULL REFERENCES uploads (upload_id),
            page_number integer NOT NULL,
            text_source text NOT NULL CHECK (text_source IN ('TEXT_LAYER', 'IMAGE')),
            char_count integer NOT NULL,
            rotation integer NOT NULL DEFAULT 0,
            owner_case_id text,
            image_sha256 char(64),
            reason text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (upload_id, page_number)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_pages")
    op.execute("ALTER TABLE document_reads DROP COLUMN IF EXISTS extracted")
    op.execute("UPDATE uploads SET outcome = 'PENDING' WHERE outcome = 'READING'")
    op.execute("ALTER TABLE uploads DROP CONSTRAINT uploads_outcome_check")
    op.execute(f"ALTER TABLE uploads ADD CONSTRAINT uploads_outcome_check CHECK (outcome IN ({OUTCOMES}))")
