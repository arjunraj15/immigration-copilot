"""The review-only form draft for one case. The form definition comes from the loaded rule sets, so a new field
is a change to the JSON files and no code. Values come only from case evidence and an unknown stays empty."""

import re
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.facts import engine, sources
from app.facts.engine import AGREE, CONFLICT, HUMAN_DECIDED, SINGLE, UNVERIFIED, FieldState
from app.facts.normalize import compare_key

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROFILE_NOTE = "From the profile, checked earlier and possibly out of date. No document has checked it yet."
# A field no document can supply, such as the mailing address, rests on the profile alone.
PROFILE_ONLY_NOTE = "From the profile, checked earlier and possibly out of date."
MISSING_NOTE = "Nothing is guessed."
HELD_NOTE = "Sources disagree, an attorney must decide"


def _rule_body(db: Session, key: str) -> dict[str, Any]:
    """Newest version of a rule set. The rules are loaded from the starter kit."""
    row = db.execute(text("SELECT body FROM rule_sets WHERE key = :key ORDER BY version DESC LIMIT 1"), {"key": key}).first()
    return row.body if row else {}


def label_for(target: str) -> str:
    """applicant.legal_name becomes Legal name."""
    words = target.split(".")[-1].replace("_", " ")
    return words[:1].upper() + words[1:]


def _us(moment: datetime) -> str:
    return f"{moment.month:02d}/{moment.day:02d}/{moment.year}"


def _held(target: str, state: FieldState) -> dict[str, Any]:
    return _fields(target, None, "HELD_FOR_REVIEW", [s.source_id for s in state.sources], HELD_NOTE)


def confidence_of(state: FieldState) -> float:
    """A score from what backs the value, never from a model's own guess. Two or more agreeing sources 0.95, one document 0.8,
    the profile alone 0.5, a claim alone 0.3, an attorney decision 1.0. A value read only from a scanned image loses 0.15."""
    if state.state == HUMAN_DECIDED:
        return 1.0
    kinds = [s.source_kind for s in state.sources]
    if state.state == AGREE:
        score = 0.95
    elif "DOCUMENT" in kinds:
        score = 0.8
    elif "PROFILE" in kinds:
        score = 0.5
    else:
        score = 0.3
    documents = [s for s in state.sources if s.source_kind == "DOCUMENT"]
    return round(score - 0.15 if documents and all(s.from_image for s in documents) else score, 2)


def _fields(target: str, value: str | None, status: str, refs: list[str], note: str, confidence: float | None = None) -> dict[str, Any]:
    """A row with no value has no confidence."""
    return {
        "target": target, "value": value, "status": status, "evidence_refs": refs, "confidence": confidence if value is not None else None,
        "needs_legal_review": status == "HELD_FOR_REVIEW", "review_notes": note,
    }  # fmt: skip


def _decided(target: str, state: FieldState) -> dict[str, Any]:
    decision = state.decided_by
    agreeing = [s.source_id for s in state.sources if compare_key(s.value) == compare_key(state.value or "")]
    why = f" Reason: {decision.reason}" if decision and decision.reason else ""
    note = f"Decided by {decision.reviewer_id} on {_us(decision.recorded_at)}.{why}" if decision else "Decided by an attorney."
    return _fields(target, state.value, "PROPOSED", agreeing, note, confidence_of(state))


def _claimed(target: str, state: FieldState, label: str = "") -> dict[str, Any]:
    """A value only a claim or the profile gives. For a field a required document gives, nothing is proposed until the document
    is there. For any other field it fills the row, cites its source and waits for legal review."""
    refs = [s.source_id for s in state.sources]
    held = [s.source_id for s in state.sources if s.source_kind == "DOCUMENT"]
    claims = [s.source_id for s in state.sources if s.source_kind != "DOCUMENT"]
    if held:
        # The document is real but a check held it back, such as an applicant name that differs from the case client.
        note = f"{', '.join(held)} is held for review, so it does not count as evidence yet."
        note += f" Claim from {', '.join(claims)}." if claims else ""
    else:
        checked = "No document has checked it yet." if state.document_source else "A person must confirm it."
        note = f"Claim from {', '.join(refs)}. {checked}"
    if state.requires_document:
        # A required document gives this field. Without it the profile and the claims are shown but nothing is proposed.
        # Every note here starts with "Needs a document: <name>." so the screens can flag the row and name the document.
        need = f"Needs a document: {label}." if label else "Needs a document."
        if held:
            note = f"{need} {', '.join(held)} is held for review, so it does not count yet."
        else:
            said = " ".join(f"{'The profile' if s.source_kind == 'PROFILE' else 'A claim'} ({s.source_id}) says {s.value}." for s in state.sources)
            note = f"{need} {said} That is not enough on its own."
        return _fields(target, None, "NOT_AVAILABLE", refs, note)
    row = _fields(target, state.sources[0].value, "PROPOSED", refs, note, confidence_of(state))
    row["needs_legal_review"] = True
    return row


def _row(target: str, state: FieldState | None, label: str = "") -> dict[str, Any]:
    """One form row from the state of its field. A claim fills the row but is marked for review, a conflict never gets a value."""
    if state is not None and state.state == UNVERIFIED and state.sources:
        return _claimed(target, state, label)
    if state is None or state.state not in (AGREE, SINGLE, CONFLICT, HUMAN_DECIDED):
        required = state is not None and state.requires_document
        if required:
            return _fields(target, None, "NOT_AVAILABLE", [], f"Needs a document: {label}. {MISSING_NOTE}" if label else f"Needs a document. {MISSING_NOTE}")
        return _fields(target, None, "NOT_AVAILABLE", [], "No value on file. Nothing is guessed." if state is not None and state.document_source else "No value yet. A person must enter or confirm it.")
    if state.state == CONFLICT:
        return _held(target, state)
    if state.state == HUMAN_DECIDED:
        return _decided(target, state)
    refs = [s.source_id for s in state.sources]
    if state.state == SINGLE:
        profile = state.sources[0].source_kind == "PROFILE"
        # A profile value is evidence under the rule file, checked earlier and possibly out of date, so it is not held back.
        note = (PROFILE_NOTE if state.document_source else PROFILE_ONLY_NOTE) if profile else f"Read from {refs[0]}."
        return _fields(target, state.value, "PROPOSED", refs, note, confidence_of(state))
    return _fields(target, state.value, "PROPOSED", refs, "All sources agree: " + ", ".join(refs) + ".", confidence_of(state))


def build_form_draft(db: Session, case_id: str) -> dict[str, Any]:
    """Sections and one row per target. Values come from the stored field states, which are rebuilt when the case changes."""
    template = _rule_body(db, "form_template")
    field_map = _rule_body(db, "form_field_map")
    states = {s.field: s for s in engine.read(db, case_id)}
    labels = sources.required_document_labels(db)
    rows = {
        target: _row(target, states.get(sources.TARGET_FIELD.get(target, "")), labels.get(sources.TARGET_FIELD.get(target, ""), ""))
        for section in template.get("sections", [])
        for target in section["fields"]
    }
    sections = [
        {
            "title": section["title"],
            "fields": [
                {"target": t, "label": label_for(t), "date": bool(ISO_DATE.match(rows[t]["value"] or ""))}
                for t in section["fields"]
            ],
        }
        for section in template.get("sections", [])
    ]
    extras = sources.additional_fields(db)
    if extras:
        # User added fields. They are optional extras, so the form never marks them required.
        for extra in extras:
            rows[extra.target] = _row(extra.target, states.get(extra.target))
        sections.append({
            "title": sources.ADDITIONAL_SECTION,
            "fields": [{"target": f.target, "label": f.label, "date": bool(ISO_DATE.match(rows[f.target]["value"] or "")), "required": False} for f in extras],
        })  # fmt: skip
    return {
        "form_id": template.get("template_id", field_map.get("form_id", "")), "sections": sections, "fields": list(rows.values()),
        "release_status": "PENDING_LEGAL_REVIEW_ONLY",
    }  # fmt: skip
