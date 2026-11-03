"""Additional client fields: extra Form draft inputs a user adds from the AI tab, beyond the nine of the form template."""

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import form_draft
from app.core import audit
from app.core.contracts import AuditAction
from app.core.security import Actor
from app.facts import sources

VALUE_TYPES = ("string", "date", "number")
PREFIX = "additional."
MAX_LABEL = 80


class FormFieldError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def targets(db: Session) -> list[dict[str, str]]:
    """The form fields an extracted field can fill: the targets of the form template that this app builds a value for,
    then the additional client fields."""
    template = form_draft._rule_body(db, "form_template")
    found = [
        {"target": t, "label": form_draft.label_for(t), "section": section["title"]}
        for section in template.get("sections", [])
        for t in section["fields"]
        if t in sources.TARGET_FIELD
    ]
    return found + [{"target": f.target, "label": f.label, "section": sources.ADDITIONAL_SECTION} for f in sources.additional_fields(db)]


def target_for(label: str) -> str | None:
    """The code-built target of a label, such as additional.aadhaar_number. None when the label has no letters or digits."""
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:60]
    return PREFIX + slug if slug else None


def add_field(db: Session, actor: Actor, label: str, value_type: str = "string") -> sources.ExtraField:
    """Insert one field and write its audit line. The caller commits, so both land in one transaction."""
    label = " ".join(label.split())
    target = target_for(label)
    if target is None or len(label) > MAX_LABEL:
        raise FormFieldError(422, "INVALID_FIELD_LABEL", f"Give a label of 1 to {MAX_LABEL} characters with letters or digits")
    if value_type not in VALUE_TYPES:
        raise FormFieldError(422, "INVALID_FIELD_TYPE", f"Type must be one of {', '.join(VALUE_TYPES)}")
    if db.execute(text("SELECT 1 FROM additional_form_fields WHERE target = :t"), {"t": target}).first():
        raise FormFieldError(409, "FIELD_EXISTS", f"There is already an additional client field called {label}")
    db.execute(
        text("INSERT INTO additional_form_fields (target, label, value_type, created_by) VALUES (:t, :l, :v, :a)"),
        {"t": target, "l": label, "v": value_type, "a": actor.label},
    )
    audit.record(db, actor=actor, action=AuditAction.FORM_FIELD_ADDED, target_type="form_field", target_id=target,
                 after_state={"label": label, "value_type": value_type})  # fmt: skip
    return sources.ExtraField(target=target, label=label, value_type=value_type)
