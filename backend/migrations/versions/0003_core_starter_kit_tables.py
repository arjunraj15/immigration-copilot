"""core: starter kit source tables, rule sets, review decisions and case workflow

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""
from alembic import op

from app.core.config import get_settings
from sqlalchemy.engine import make_url

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = [
    "case_workflows", "review_decisions", "uploads", "case_events", "profile_fields", "messages",
    "intake_notes", "rule_sets", "cases",
]  # fmt: skip


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE cases (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id text NOT NULL UNIQUE,
            web_record_id text NOT NULL,
            client_ref text NOT NULL,
            case_archetype text NOT NULL,
            operational_stage text NOT NULL,
            assigned_ops_user text NOT NULL,
            assigned_legal_reviewer text NOT NULL,
            opened_at date NOT NULL,
            matter_visibility text NOT NULL,
            priority text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_cases_ops ON cases (assigned_ops_user)")
    op.execute("CREATE INDEX ix_cases_legal ON cases (assigned_legal_reviewer)")

    op.execute(
        """
        CREATE TABLE intake_notes (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            intake_id text NOT NULL UNIQUE,
            case_id text NOT NULL REFERENCES cases (case_id),
            recorded_at timestamptz NOT NULL,
            platform text NOT NULL,
            speaker text NOT NULL,
            summary text NOT NULL,
            raw_note_excerpt text NOT NULL,
            ai_generated boolean NOT NULL,
            approved_as_fact boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_intake_notes_case_id ON intake_notes (case_id)")

    op.execute(
        """
        CREATE TABLE messages (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            message_id text NOT NULL UNIQUE,
            case_id text NOT NULL REFERENCES cases (case_id),
            thread_id text NOT NULL,
            created_at_source timestamptz NOT NULL,
            channel text NOT NULL,
            direction text NOT NULL,
            sender_role text NOT NULL,
            subject text NOT NULL,
            body text NOT NULL,
            attachment_refs text[] NOT NULL DEFAULT '{}',
            delivery_state text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_messages_case_id ON messages (case_id)")

    op.execute(
        """
        CREATE TABLE profile_fields (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            source_id text NOT NULL UNIQUE,
            case_id text NOT NULL REFERENCES cases (case_id),
            field_name text NOT NULL,
            verified_value text NOT NULL,
            verification_state text NOT NULL,
            verified_at timestamptz NOT NULL,
            verified_by text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (case_id, field_name)
        )
        """
    )
    op.execute("CREATE INDEX ix_profile_fields_case_id ON profile_fields (case_id)")

    op.execute(
        """
        CREATE TABLE case_events (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            event_id text NOT NULL UNIQUE,
            case_id text NOT NULL REFERENCES cases (case_id),
            event_date date NOT NULL,
            event_type text NOT NULL,
            event_source text NOT NULL,
            source_reference text NOT NULL,
            details text NOT NULL,
            source_verified boolean NOT NULL,
            import_batch text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_case_events_case_id ON case_events (case_id)")
    # The same event arriving again under a new id is stored once.
    op.execute(
        "CREATE UNIQUE INDEX ux_case_events_content ON case_events "
        "(case_id, event_date, event_type, event_source, source_reference, details)"
    )

    op.execute(
        """
        CREATE TABLE uploads (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            upload_id text NOT NULL UNIQUE,
            case_id text NOT NULL REFERENCES cases (case_id),
            storage_object_id text,
            storage_root text NOT NULL CHECK (storage_root IN ('STARTER_KIT', 'APP_STORAGE')),
            storage_path text NOT NULL,
            original_filename text NOT NULL,
            mime_type text NOT NULL,
            file_size_bytes bigint NOT NULL,
            sha256 char(64) NOT NULL,
            uploaded_at timestamptz NOT NULL,
            uploader_role text NOT NULL,
            ingestion_source text NOT NULL,
            client_supplied_type text NOT NULL,
            version_label text NOT NULL,
            category text,
            outcome text NOT NULL DEFAULT 'PENDING' CHECK (outcome IN (
                'PENDING', 'DUPLICATE', 'QUARANTINED', 'SUPERSEDED', 'INVALID', 'USABLE', 'NEEDS_HUMAN_REVIEW')),
            outcome_reason text,
            reason_code text,
            duplicate_of_upload_id text,
            superseded_by_upload_id text,
            owner_case_id text,
            flags jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_uploads_case_id ON uploads (case_id)")
    op.execute("CREATE INDEX ix_uploads_sha256 ON uploads (sha256)")

    op.execute(
        """
        CREATE TABLE rule_sets (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            key text NOT NULL,
            version int NOT NULL,
            source_file text NOT NULL,
            body jsonb NOT NULL,
            sha256 char(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (key, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE review_decisions (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            decision_id text NOT NULL UNIQUE,
            case_id text NOT NULL REFERENCES cases (case_id),
            proposal_id text,
            field_name text,
            rejected_value text,
            corrected_value text,
            decision text NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED', 'REJECTED_EXTRACTION')),
            reviewer_role text NOT NULL,
            reviewer_id text NOT NULL,
            reason text,
            source_ref text,
            recorded_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_review_decisions_case_id ON review_decisions (case_id)")
    op.execute(
        """
        CREATE FUNCTION insert_only_guard() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is insert-only: % is not allowed', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER review_decisions_no_change BEFORE UPDATE OR DELETE ON review_decisions "
        "FOR EACH ROW EXECUTE FUNCTION insert_only_guard()"
    )
    op.execute(
        "CREATE TRIGGER review_decisions_no_truncate BEFORE TRUNCATE ON review_decisions "
        "FOR EACH STATEMENT EXECUTE FUNCTION insert_only_guard()"
    )

    op.execute(
        """
        CREATE TABLE case_workflows (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            case_id text NOT NULL UNIQUE REFERENCES cases (case_id),
            status text NOT NULL DEFAULT 'NEW' CHECK (status IN (
                'NEW', 'ANALYSING', 'IN_PROGRESS', 'WITH_ATTORNEY', 'INFO_REQUESTED',
                'APPROVED', 'REJECTED', 'APPLIED')),
            wizard_step int NOT NULL DEFAULT 0,
            submitted_by text,
            submitted_to text,
            submitted_at timestamptz,
            note text,
            decided_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    role = make_url(get_settings().database_url).username
    op.execute(f"REVOKE UPDATE, DELETE ON review_decisions FROM {role}")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS insert_only_guard()")
