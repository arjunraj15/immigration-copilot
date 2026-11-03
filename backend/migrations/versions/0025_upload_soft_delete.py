"""an upload can be deleted: the row stays for the audit trail and every view skips it

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-24
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE uploads ADD COLUMN deleted_at timestamptz, ADD COLUMN deleted_by text, ADD COLUMN delete_reason text")
    op.execute("CREATE INDEX ix_uploads_live ON uploads (case_id) WHERE deleted_at IS NULL")


def downgrade() -> None:
    op.execute("DROP INDEX ix_uploads_live")
    op.execute("ALTER TABLE uploads DROP COLUMN deleted_at, DROP COLUMN deleted_by, DROP COLUMN delete_reason")
