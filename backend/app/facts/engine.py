"""Field states from the facts of one case. Code decides every state. The model only explains.

AGREE and SINGLE_SOURCE_EVIDENCE need evidence. A difference is always a CONFLICT with no value.
An attorney decision in review_decisions wins over every extraction, on every rebuild."""

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import audit
from app.core.contracts import AuditAction, AuditOutcome
from app.facts import match_gate, sources
from app.facts.normalize import compare_key
from app.facts.sources import CLAIM, EVIDENCE, FIELDS, Assertion

log = logging.getLogger(__name__)

AGREE, CONFLICT, UNVERIFIED = "AGREE", "CONFLICT", "UNVERIFIED"
SINGLE, NO_SOURCE, HUMAN_DECIDED = "SINGLE_SOURCE_EVIDENCE", "NO_SOURCE", "HUMAN_DECIDED"
HIGH_FIELDS = ("full_name", "date_of_birth", "passport_number", "prior_receipt_number")
CONFLICT_NOTE = "Sources disagree, an attorney must decide"
UNVERIFIED_NOTE = "Needs a document"
HELD_DOCUMENT_NOTE = "A document is held for review, so it does not count yet"
PROFILE_NEEDS_DOCUMENT_NOTE = "Needs a document, the profile alone is not enough"
CONFIRM_NOTE = "Needs a person to confirm it"  # a field no document can supply, such as the mailing address


class SourceOut(BaseModel):
    source_id: str
    source_kind: str
    trust: str
    value: str
    quote: str | None
    page: int | None
    verified: bool
    from_image: bool
    odd: bool = False
    phase: str = "UPDATE"


class Decision(BaseModel):
    decision_id: str
    reviewer_id: str
    reviewer_role: str | None = None
    recorded_at: datetime
    reason: str | None
    source_ref: str | None


class FieldState(BaseModel):
    field: str
    label: str
    state: str
    severity: str
    value: str | None
    trust: dict[str, int]
    sources: list[SourceOut]
    decided_by: Decision | None
    note: str | None
    review_open: bool = False
    change: bool = False
    document_source: bool = True  # False when the form field map names no document type for the field
    requires_document: bool = False  # True when a required document gives this field, so the profile alone is not enough


def label_for(field: str) -> str:
    words = field.replace("_", " ")
    return words[:1].upper() + words[1:]


def severity_of(field: str) -> str:
    return "high" if field in HIGH_FIELDS else "medium"


def _odd_ids(groups: dict[str, list[Assertion]]) -> set[int]:
    """Positions of the assertions outside the one largest group. With no single largest group nobody is odd."""
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    if len(sizes) < 2 or sizes[0] == sizes[1]:
        return set()
    biggest = max(groups.values(), key=len)
    return {id(a) for g in groups.values() if g is not biggest for a in g}


def _shown_value(items: list[Assertion]) -> str:
    """The agreed value as written. An evidence source is preferred over a claim."""
    return next((a for a in items if a.trust == EVIDENCE), items[0]).normalized_value


def _changed_after_call(items: list[Assertion]) -> bool:
    """True when a later message or file says something other than the intake call said."""
    first = {compare_key(a.normalized_value) for a in items if a.phase == "BASELINE"}
    later = {compare_key(a.normalized_value) for a in items if a.phase == "UPDATE" and a.source_kind != "DOCUMENT"}
    # A shorter or longer way to write the same value, such as an address without the city, is not a change.
    return bool(first) and any(not any(a in b or b in a for b in first) for a in later)


def build_state(field: str, items: list[Assertion], decision: Decision | None, decided_value: str | None,
                document_source: bool = True, requires_document: bool = False) -> FieldState:  # fmt: skip
    groups: dict[str, list[Assertion]] = {}
    for a in items:
        groups.setdefault(a.group_key or compare_key(a.normalized_value), []).append(a)
    odd = _odd_ids(groups) if len(groups) > 1 else set()
    out = [
        SourceOut(source_id=a.source_id, source_kind=a.source_kind, trust=a.trust, value=a.normalized_value, quote=a.quote,
                  page=a.page, verified=a.verified, from_image=a.from_image, odd=id(a) in odd, phase=a.phase)
        for a in items
    ]  # fmt: skip
    evidence = sum(1 for a in items if a.trust == EVIDENCE)
    trust = {"evidence": evidence, "claim": len(items) - evidence}
    state, value, note = NO_SOURCE, None, None
    if decision is not None:
        state, value, note = HUMAN_DECIDED, decided_value, f"Decided by {decision.reviewer_id}"
    elif len(groups) > 1:
        state, note = CONFLICT, CONFLICT_NOTE
    elif items and (not evidence or (requires_document and not any(a.source_kind == "DOCUMENT" and a.trust == EVIDENCE for a in items))):
        held = any(a.source_kind == "DOCUMENT" for a in items)  # a document exists but a check held it back
        note = HELD_DOCUMENT_NOTE if held else (UNVERIFIED_NOTE if document_source else CONFIRM_NOTE)
        state, note = UNVERIFIED, PROFILE_NEEDS_DOCUMENT_NOTE if evidence and not held else note
    elif items:
        state, value = (AGREE if len(items) > 1 else SINGLE), _shown_value(items)
    return FieldState(field=field, label=label_for(field), state=state, severity=severity_of(field), value=value, trust=trust,
                      sources=out, decided_by=decision, note=note, change=_changed_after_call(items), document_source=document_source,
                      requires_document=requires_document)  # fmt: skip


def load_decisions(db: Session, case_id: str) -> dict[str, tuple[Decision, str]]:
    """The newest human value for each field. Rows are insert only, so a later row is a later human choice."""
    rows = db.execute(
        text(
            "SELECT DISTINCT ON (field_name) decision_id, field_name, corrected_value, reviewer_id, reviewer_role, reason, source_ref, recorded_at "
            "FROM review_decisions WHERE case_id = :c AND field_name = ANY(:f) AND corrected_value IS NOT NULL "
            "ORDER BY field_name, recorded_at DESC, id DESC"
        ),
        {"c": case_id, "f": list(sources.field_names(db))},
    ).all()
    return {
        r.field_name: (Decision(decision_id=r.decision_id, reviewer_id=r.reviewer_id, reviewer_role=r.reviewer_role, recorded_at=r.recorded_at, reason=r.reason,
                                source_ref=r.source_ref), r.corrected_value)
        for r in rows
    }  # fmt: skip


def states_from(items: list[Assertion], decisions: dict[str, tuple[Decision, str]], no_document: frozenset[str] = frozenset(),
                needs_document: frozenset[str] = frozenset(), names: tuple[str, ...] = FIELDS,
                labels: dict[str, str] | None = None) -> list[FieldState]:  # fmt: skip
    result = []
    for field in names:
        decision, value = decisions.get(field, (None, None))
        state = build_state(field, [a for a in items if a.field == field], decision, value, field not in no_document, field in needs_document)
        state.label = (labels or {}).get(field, state.label)
        result.append(state)
    return result


def _all_states(db: Session, case_id: str, items: list[Assertion]) -> list[FieldState]:
    """The nine form fields and the additional client fields, from the assertions of one case."""
    labels = {f.target: f.label for f in sources.additional_fields(db)}
    return states_from(items, load_decisions(db, case_id), sources.no_document_fields(db), sources.document_required_fields(db),
                       sources.field_names(db), labels)  # fmt: skip


def compute_states(db: Session, case_id: str) -> list[FieldState]:
    """Read only. Nothing is written and no model is called, so the home page can use it for every case."""
    return _all_states(db, case_id, sources.collect(db, case_id))


def _store(db: Session, case_id: str, items: list[Assertion]) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"facts:{case_id}"})
    db.execute(text("DELETE FROM facts WHERE case_id = :c"), {"c": case_id})
    for a in items:
        db.execute(
            text("INSERT INTO facts (case_id, field, value, normalized_value, source_kind, source_id, quote, page, verified, "
                 "trust, from_image) VALUES (:c, :field, :value, :normalized_value, :source_kind, :source_id, :quote, :page, "
                 ":verified, :trust, :from_image)"),
            {"c": case_id, **a.model_dump()},
        )  # fmt: skip


def _sync_requests(db: Session, case_id: str, states: list[FieldState]) -> None:
    """One open review request per conflict. The audit lines are written once, when it opens."""
    for s in states:
        if s.state != CONFLICT:
            db.execute(
                text("UPDATE review_requests SET status = 'RESOLVED', resolved_at = now() "
                     "WHERE case_id = :c AND field = :f AND status = 'OPEN'"),
                {"c": case_id, "f": s.field},
            )  # fmt: skip
            continue
        opened = db.execute(
            text("INSERT INTO review_requests (case_id, field) VALUES (:c, :f) ON CONFLICT (case_id, field) DO UPDATE "
                 "SET status = 'OPEN', opened_at = now(), resolved_at = NULL WHERE review_requests.status = 'RESOLVED' RETURNING id"),
            {"c": case_id, "f": s.field},
        ).first()  # fmt: skip
        s.review_open = True
        if opened is None:
            continue
        ids = [a.source_id for a in s.sources]
        for action in (AuditAction.CONFLICT_OPENED, AuditAction.REVIEW_REQUESTED):
            audit.record(db, actor=audit.SYSTEM_ACTOR, action=action, outcome=AuditOutcome.SYSTEM, case_id=case_id,
                         target_type="field", target_id=s.field, evidence_ids=ids, details={"severity": s.severity})  # fmt: skip


def rebuild_facts(db: Session, case_id: str) -> list[FieldState]:
    """Replace the case facts from the sources, work out every field state and open review requests. Idempotent."""
    items = sources.collect(db, case_id)
    if match_gate.settle(db, items, case_id):
        items = sources.collect(db, case_id)
    states = _all_states(db, case_id, items)
    _store(db, case_id, items)
    _sync_requests(db, case_id, states)
    _save_states(db, case_id, states)
    return states


def _save_states(db: Session, case_id: str, states: list[FieldState]) -> None:
    """Keep the computed states, so a read can load them instead of rebuilding."""
    db.execute(text("DELETE FROM fact_states WHERE case_id = :c"), {"c": case_id})
    for s in states:
        db.execute(
            text("INSERT INTO fact_states (case_id, field, state) VALUES (:c, :f, CAST(:s AS jsonb))"),
            {"c": case_id, "f": s.field, "s": s.model_dump_json()},
        )


def invalidate(db: Session, case_id: str | None = None) -> None:
    """Forget the stored states of one case, or of every case. The next read builds them again, once."""
    if case_id is None:
        db.execute(text("DELETE FROM fact_states"))
    else:
        db.execute(text("DELETE FROM fact_states WHERE case_id = :c"), {"c": case_id})


def read(db: Session, case_id: str) -> list[FieldState]:
    """The stored states. A case that was never built is built and stored now, then loaded from the table from then on."""
    rows = db.execute(text("SELECT field, state FROM fact_states WHERE case_id = :c"), {"c": case_id}).all()
    stored = {r.field: FieldState.model_validate(r.state) for r in rows}
    names = sources.field_names(db)
    if all(f in stored for f in names):
        return [stored[f] for f in names]
    states = refresh(db, case_id)
    db.commit()
    return states


def recompute(db: Session, case_id: str) -> None:
    """Call after a record, a document, a name or a decision changed. Rebuilds and stores the states. Never raises."""
    try:
        refresh(db, case_id)
        db.commit()
    except Exception:
        log.exception("Could not rebuild the facts of %s", case_id)
        db.rollback()


def refresh(db: Session, case_id: str) -> list[FieldState]:
    """Read the notes and messages that have no claims yet, then rebuild. The caller commits."""
    sources.ensure_claims(db, case_id)
    return rebuild_facts(db, case_id)


def source_values(state: FieldState) -> dict[str, str]:
    """Comparison key to the value as shown, for every source of the field."""
    return {compare_key(s.value): s.value for s in state.sources}


def as_dict(state: FieldState) -> dict[str, Any]:
    return state.model_dump(mode="json")
