"""core: audit ledger tables, immutability trigger and the limited app role

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""
import re

from alembic import op
from sqlalchemy.engine import make_url

from app.core.config import get_settings

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ZERO_HASH = "0" * 64


def _app_role() -> tuple[str, str]:
    """Role name and password come from the app's own DATABASE_URL, so config stays in one place."""
    url = make_url(get_settings().database_url)
    role, password = url.username or "", url.password or ""
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", role):
        raise RuntimeError(f"Unsupported app database role name {role!r}")
    return role, password.replace("'", "''")


def upgrade() -> None:
    role, password = _app_role()

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} LOGIN PASSWORD '{password}';
            ELSE
                ALTER ROLE {role} LOGIN PASSWORD '{password}';
            END IF;
        END $$;
        """
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    # Later tables created by the owner are usable by the app role. The audit tables are tightened below.
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}")

    op.execute(
        f"""
        CREATE TABLE audit_log (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            stream_id text NOT NULL,
            seq bigint NOT NULL CHECK (seq >= 1),
            occurred_at timestamptz NOT NULL,
            actor text NOT NULL,
            actor_role text NOT NULL CHECK (actor_role IN ('OPS', 'LEGAL', 'SYSTEM')),
            action text NOT NULL,
            outcome text NOT NULL CHECK (outcome IN ('ALLOWED', 'DENIED', 'SYSTEM')),
            case_id text,
            target_type text,
            target_id text,
            before_state jsonb,
            after_state jsonb,
            evidence_ids text[] NOT NULL DEFAULT '{{}}',
            idempotency_key text,
            request_id text,
            prompt_run_id bigint,
            details jsonb NOT NULL DEFAULT '{{}}',
            prev_hash char(64) NOT NULL,
            row_hash char(64) NOT NULL,
            CONSTRAINT audit_log_stream_seq UNIQUE (stream_id, seq)
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_log_case_id ON audit_log (case_id)")
    op.execute(
        f"""
        CREATE TABLE audit_heads (
            stream_id text PRIMARY KEY,
            last_seq bigint NOT NULL DEFAULT 0,
            last_hash char(64) NOT NULL DEFAULT '{ZERO_HASH}',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE FUNCTION audit_log_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is insert-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()"
    )
    op.execute(
        "CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_log_immutable()"
    )

    op.execute(f"REVOKE ALL ON audit_log FROM {role}")
    op.execute(f"GRANT SELECT, INSERT ON audit_log TO {role}")
    op.execute(f"REVOKE DELETE ON audit_heads FROM {role}")


def downgrade() -> None:
    role, _ = _app_role()
    op.execute("DROP TABLE IF EXISTS audit_heads")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_immutable()")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {role}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {role}")
