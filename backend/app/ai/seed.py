"""Load prompts/*.yaml into the registry. Only missing keys are inserted, edits are never overwritten."""

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import registry
from app.ai.models import Prompt, PromptVersion

PROMPTS_DIR = Path(__file__).parent / "prompts"
SEED_ACTOR = "seed"
_VERSION_FIELDS = (
    "system_text",
    "user_template",
    "model",
    "effort",
    "max_tokens",
    "output_schema",
    "field_definitions",
    "tools",
    "note",
)


def seed_prompts(db: Session, directory: Path = PROMPTS_DIR) -> list[str]:
    """Insert each YAML prompt whose key is not in the database. Returns the keys added."""
    if not directory.is_dir():
        return []
    existing = set(db.scalars(select(Prompt.key)))
    added: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("key") in existing:
            continue
        _insert(db, data)
        added.append(data["key"])
    added_targets = _backfill_form_targets(db, directory)
    db.commit()
    return added + added_targets


def _insert(db: Session, data: dict[str, Any]) -> None:
    row = registry.create_version([], None, {k: data.get(k) for k in _VERSION_FIELDS} | {"created_by": SEED_ACTOR})
    prompt = Prompt(
        key=data["key"],
        step=data["step"],
        category=data.get("category"),
        title=data["title"],
        recognition_hint=data.get("recognition_hint"),
    )
    db.add(prompt)
    db.flush()
    version = PromptVersion(prompt_id=prompt.id, **row)
    db.add(version)
    db.flush()
    prompt.active_version_id = version.id


def _backfill_form_targets(db: Session, directory: Path) -> list[str]:
    """A database seeded before form_target existed gets one new version per untouched seed prompt that carries the targets.
    A prompt a person has edited is left alone, so an admin's choice, including 'validate only', is never put back."""
    changed: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        wanted = {d["key"]: d["form_target"] for d in data.get("field_definitions") or [] if d.get("form_target")}
        prompt = db.scalar(select(Prompt).where(Prompt.key == data.get("key")))
        if not wanted or prompt is None or prompt.active_version_id is None:
            continue
        active = db.get(PromptVersion, prompt.active_version_id)
        if active is None or active.created_by != SEED_ACTOR or any(d.get("form_target") for d in active.field_definitions):
            continue
        definitions = [{**d, "form_target": wanted[d["key"]]} if d["key"] in wanted else dict(d) for d in active.field_definitions]
        versions = [{"version": v} for v in db.scalars(select(PromptVersion.version).where(PromptVersion.prompt_id == prompt.id))]
        fields = {k: getattr(active, k) for k in _VERSION_FIELDS} | {"field_definitions": definitions, "created_by": SEED_ACTOR}
        row = registry.create_version(versions, {"field_definitions": active.field_definitions}, fields)
        version = PromptVersion(prompt_id=prompt.id, **row)
        db.add(version)
        db.flush()
        prompt.active_version_id = version.id
        changed.append(prompt.key)
    return changed
