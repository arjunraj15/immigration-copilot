"""facts: one fact table per case, conflict suggestions and review requests

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-23
"""
from alembic import op

from app.core.config import get_settings
from sqlalchemy.engine import make_url

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE facts (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id text NOT NULL REFERENCES cases (case_id),
            field text NOT NULL,
            value text NOT NULL,
            normalized_value text NOT NULL,
            source_kind text NOT NULL CHECK (source_kind IN ('DOCUMENT', 'PROFILE', 'INTAKE', 'MESSAGE', 'CLAIM')),
            source_id text NOT NULL,
            quote text,
            page integer,
            verified boolean NOT NULL DEFAULT false,
            from_image boolean NOT NULL DEFAULT false,
            trust text NOT NULL CHECK (trust IN ('EVIDENCE', 'CLAIM')),
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (source_kind IN ('DOCUMENT', 'PROFILE') OR trust = 'CLAIM')
        )
        """
    )
    op.execute("CREATE INDEX ix_facts_case_id ON facts (case_id)")
    op.execute(
        """
        CREATE TABLE conflict_suggestions (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id text NOT NULL REFERENCES cases (case_id),
            field text NOT NULL,
            suggested_value text,
            leave_to_attorney boolean NOT NULL DEFAULT false,
            reason text NOT NULL,
            actor text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((suggested_value IS NULL) = leave_to_attorney)
        )
        """
    )
    op.execute("CREATE INDEX ix_conflict_suggestions_case_id ON conflict_suggestions (case_id)")
    op.execute(
        "CREATE TRIGGER conflict_suggestions_no_change BEFORE UPDATE OR DELETE ON conflict_suggestions "
        "FOR EACH ROW EXECUTE FUNCTION insert_only_guard()"
    )
    op.execute(
        "CREATE TRIGGER conflict_suggestions_no_truncate BEFORE TRUNCATE ON conflict_suggestions "
        "FOR EACH STATEMENT EXECUTE FUNCTION insert_only_guard()"
    )
    op.execute(
        """
        CREATE TABLE review_requests (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id text NOT NULL REFERENCES cases (case_id),
            field text NOT NULL,
            status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'RESOLVED')),
            opened_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz,
            UNIQUE (case_id, field)
        )
        """
    )
    role = make_url(get_settings().database_url).username
    op.execute(f"REVOKE UPDATE, DELETE ON conflict_suggestions FROM {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_requests")
    op.execute("DROP TABLE IF EXISTS conflict_suggestions")
    op.execute("DROP TABLE IF EXISTS facts")
