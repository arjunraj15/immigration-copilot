"""the address proof read prompt and the value match prompt are in the database from the start

A fresh database gets these two prompts from this migration, so the address proof document type and the value gate
do not depend on the startup seed. A prompt that already exists is left alone, deleted or not, because versions are
insert only and an edit made in the app must survive. The text comes from the same YAML files as the startup seed.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-24
"""
import json
from pathlib import Path

import sqlalchemy as sa
import yaml
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

_PROMPTS = Path(__file__).resolve().parents[2] / "app" / "ai" / "prompts"
_FILES = ("read_address_proof.yaml", "facts_value_match.yaml")
_VERSION_FIELDS = ("system_text", "user_template", "model", "effort", "max_tokens", "output_schema", "field_definitions", "tools", "note")


def upgrade() -> None:
    db = op.get_bind()
    for name in _FILES:
        data = yaml.safe_load((_PROMPTS / name).read_text(encoding="utf-8"))
        if db.execute(sa.text("SELECT 1 FROM prompts WHERE key = :k"), {"k": data["key"]}).first():
            continue
        prompt_id = db.execute(
            sa.text("INSERT INTO prompts (key, step, category, title, recognition_hint) VALUES (:k, :s, :c, :t, :h) RETURNING id"),
            {"k": data["key"], "s": data["step"], "c": data.get("category"), "t": data["title"], "h": data.get("recognition_hint")},
        ).scalar_one()
        row = {f: data.get(f) for f in _VERSION_FIELDS}
        version_id = db.execute(
            sa.text(
                "INSERT INTO prompt_versions (prompt_id, version, system_text, user_template, model, effort, max_tokens, output_schema, "
                "field_definitions, tools, note, created_by) VALUES (:p, 1, :system_text, :user_template, :model, :effort, :max_tokens, "
                "CAST(:output_schema AS jsonb), CAST(:field_definitions AS jsonb), CAST(:tools AS jsonb), :note, 'seed') RETURNING id"
            ),
            {"p": prompt_id, **row, "output_schema": json.dumps(row["output_schema"]),
             "field_definitions": json.dumps(row["field_definitions"] or []), "tools": json.dumps(row["tools"] or [])},
        ).scalar_one()
        db.execute(sa.text("UPDATE prompts SET active_version_id = :v WHERE id = :p"), {"v": version_id, "p": prompt_id})


def downgrade() -> None:
    # The prompts stay. Versions are insert only, so a downgrade cannot remove them without breaking the history.
    pass
