"""ai: plain document type names and the document_reads table for the review list

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-23
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE prompts SET title = 'Unknown document' WHERE key = 'doc.read.generic' AND title = 'Read generic document'")
    op.execute(
        """
        UPDATE prompts SET title = upper(substr(title, 6, 1)) || substr(title, 7)
        WHERE step = 'read' AND key <> 'doc.read.generic' AND title LIKE 'Read %' AND length(title) > 5
        """
    )
    op.execute(
        """
        CREATE TABLE document_reads (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            upload_id text NOT NULL REFERENCES uploads (upload_id),
            category text NOT NULL,
            status text NOT NULL CHECK (status IN ('READ', 'REVIEW_REQUIRED')),
            legible boolean NOT NULL DEFAULT true,
            injection_flag boolean NOT NULL DEFAULT false,
            language text,
            page_count integer,
            reason text,
            read_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_document_reads_upload ON document_reads (upload_id, read_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS document_reads")
