"""ai registry

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("category", sa.String(80), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("recognition_hint", sa.Text(), nullable=True),
        sa.Column("active_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("step in ('classify', 'read', 'other')", name="ck_prompts_step"),
    )
    op.create_index("ix_prompts_key", "prompts", ["key"], unique=True)

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("prompts.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_text", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("effort", sa.String(20), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=False),
        sa.Column("field_definitions", postgresql.JSONB(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("prompt_id", "version", name="uq_prompt_versions_prompt_version"),
    )
    op.create_index("ix_prompt_versions_prompt_id", "prompt_versions", ["prompt_id"])

    op.create_foreign_key(
        "fk_prompts_active_version", "prompts", "prompt_versions", ["active_version_id"], ["id"]
    )

    op.execute(
        """
        CREATE FUNCTION prompt_versions_insert_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'prompt_versions is insert-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER prompt_versions_no_change
        BEFORE UPDATE OR DELETE ON prompt_versions
        FOR EACH ROW EXECUTE FUNCTION prompt_versions_insert_only()
        """
    )

    op.create_table(
        "prompt_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prompt_key", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("case_id", sa.String(40), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("stop_reason", sa.String(40), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("rendered_prompt", sa.Text(), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prompt_runs_prompt_key", "prompt_runs", ["prompt_key"])
    op.create_index("ix_prompt_runs_input_hash", "prompt_runs", ["input_hash"])
    op.create_index("ix_prompt_runs_case_id", "prompt_runs", ["case_id"])


def downgrade() -> None:
    op.drop_table("prompt_runs")
    op.drop_constraint("fk_prompts_active_version", "prompts", type_="foreignkey")
    op.execute("DROP TRIGGER IF EXISTS prompt_versions_no_change ON prompt_versions")
    op.drop_table("prompt_versions")
    op.execute("DROP FUNCTION IF EXISTS prompt_versions_insert_only()")
    op.drop_table("prompts")
