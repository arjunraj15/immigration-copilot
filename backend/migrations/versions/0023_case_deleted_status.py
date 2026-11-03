"""a case can be deleted: the workflow status DELETED hides it everywhere and keeps its history

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-24
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_OLD = "'NEW', 'ANALYSING', 'IN_PROGRESS', 'WITH_ATTORNEY', 'INFO_REQUESTED', 'APPROVED', 'REJECTED', 'APPLIED', 'DRAFT'"


def upgrade() -> None:
    op.execute("ALTER TABLE case_workflows DROP CONSTRAINT case_workflows_status_check")
    op.execute(f"ALTER TABLE case_workflows ADD CONSTRAINT case_workflows_status_check CHECK (status IN ({_OLD}, 'DELETED'))")


def downgrade() -> None:
    op.execute("UPDATE case_workflows SET status = 'NEW' WHERE status = 'DELETED'")
    op.execute("ALTER TABLE case_workflows DROP CONSTRAINT case_workflows_status_check")
    op.execute(f"ALTER TABLE case_workflows ADD CONSTRAINT case_workflows_status_check CHECK (status IN ({_OLD}))")
