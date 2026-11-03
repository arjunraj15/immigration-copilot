"""prompt versions list the read only date tools the model may call

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-24
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# The tools that were chosen in code before this column existed, so these prompts keep behaving the same.
_CHAT = '["get_today", "parse_date", "add_days", "days_between"]'
_BACKFILL = {
    "doc.read.email_message": _CHAT,
    "doc.read.whatsapp_chat": _CHAT,
    "doc.read.zoom_notes": _CHAT,
    "doc.read.prior_notice": '["parse_date", "add_days", "date_in_range"]',
    "doc.read.arrival_record": '["parse_date", "date_in_range"]',
}


def upgrade() -> None:
    op.execute("ALTER TABLE prompt_versions ADD COLUMN tools jsonb NOT NULL DEFAULT '[]'::jsonb")
    # Versions are insert only, so each of these prompts gets a new version that copies its active one and adds the tools.
    for key, tools in _BACKFILL.items():
        op.execute(
            f"""
            WITH ins AS (
                INSERT INTO prompt_versions (prompt_id, version, system_text, user_template, model, effort, max_tokens,
                                             output_schema, field_definitions, tools, note, created_by)
                SELECT v.prompt_id, (SELECT max(version) + 1 FROM prompt_versions WHERE prompt_id = v.prompt_id),
                       v.system_text, v.user_template, v.model, v.effort, v.max_tokens, v.output_schema,
                       v.field_definitions, '{tools}'::jsonb, 'Turn on the date tools', 'migration'
                FROM prompts p JOIN prompt_versions v ON v.id = p.active_version_id
                WHERE p.key = '{key}'
                RETURNING id, prompt_id
            )
            UPDATE prompts SET active_version_id = ins.id FROM ins WHERE prompts.id = ins.prompt_id
            """
        )


def downgrade() -> None:
    op.execute("ALTER TABLE prompt_versions DROP COLUMN tools")
