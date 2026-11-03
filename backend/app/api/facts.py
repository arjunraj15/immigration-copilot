"""Facts and conflicts of one case. Rules live in app.facts. Only a human resolves a conflict."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases.access import AccessibleCase
from app.cases.repository import CaseRecord
from app.core import audit
from app.core.contracts import ActorRole, AuditAction, UploadOutcome
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.db.session import get_db, transaction
from app.facts import engine, explain, sources
from app.facts.engine import CONFLICT, HUMAN_DECIDED, UNVERIFIED, FieldState
from app.facts.normalize import compare_key, normalize, parse_date
from app.ingest import service as ingest

router = APIRouter(prefix="/api/cases", tags=["facts"])

Db = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
NEEDS_ATTENTION = (CONFLICT, UNVERIFIED)


class FactsOut(BaseModel):
    case_id: str
    fields: list[FieldState]


class SuggestionOut(BaseModel):
    suggested_value: str | None
    leave_to_attorney: bool
    reason: str
    actor: str
    created_at: str


class ConflictOut(FieldState):
    can_resolve: bool
    explanation: str
    explanation_origin: str
    cited_source_ids: list[str]
    suggestion: SuggestionOut | None


class ConflictsOut(BaseModel):
    case_id: str
    conflicts: list[ConflictOut]


class SuggestIn(BaseModel):
    value: str | None = Field(default=None, max_length=500)
    leave_to_attorney: bool = False
    reason: str = Field(max_length=1000)


class ResolveIn(BaseModel):
    value: str = Field(min_length=1, max_length=500)
    reason: str | None = Field(default=None, max_length=1000)


IDENTITY_NOTE = "Identity conflicts need the legal reviewer"


def can_resolve(case: CaseRecord, actor: Actor, severity: str) -> bool:
    """The assigned legal reviewer decides any conflict. The assigned operations user decides only a medium one."""
    if actor.role == ActorRole.LEGAL:
        return case.assigned_legal_reviewer == actor.label
    return actor.role == ActorRole.OPS and case.assigned_ops_user == actor.label and severity != "high"


def _refuse(actor: Actor, action: AuditAction, case_id: str, field: str, reason: str) -> AppError:
    audit.record_denied(reason=reason, actor=actor, action=action, case_id=case_id, target_type="field", target_id=field)
    return AppError("ACTION_NOT_ALLOWED", reason, 403)


def _state(states: list[FieldState], field: str) -> FieldState:
    found = next((s for s in states if s.field == field), None)
    if found is None:
        raise AppError("FIELD_NOT_FOUND", f"No form field {field}", 404)
    return found


def _suggestion(db: Session, case_id: str, field: str) -> SuggestionOut | None:
    row = db.execute(
        text("SELECT suggested_value, leave_to_attorney, reason, actor, created_at FROM conflict_suggestions "
             "WHERE case_id = :c AND field = :f ORDER BY id DESC LIMIT 1"),
        {"c": case_id, "f": field},
    ).first()  # fmt: skip
    return SuggestionOut(**{**row._mapping, "created_at": row.created_at.isoformat()}) if row else None


@router.get("/{case_id}/facts")
def get_facts(case: AccessibleCase, db: Db) -> FactsOut:
    """The stored state of every form field. It is rebuilt when the case changes, not when it is read."""
    # An additional client field with no source is not a gap, so it is left out until a document gives it a value.
    states = [s for s in engine.read(db, case.case_id) if s.field in sources.FIELDS or s.state != engine.NO_SOURCE]
    return FactsOut(case_id=case.case_id, fields=states)


@router.get("/{case_id}/conflicts")
def get_conflicts(case: AccessibleCase, db: Db, actor: CurrentActor) -> ConflictsOut:
    """Fields where the sources disagree, each with a plain words explanation and the newest suggestion.
    A field with only a call or message claim is not a conflict. It stays UNVERIFIED on the facts and checklist."""
    states = engine.read(db, case.case_id)
    open_states = [s for s in states if s.state == CONFLICT]
    said = explain.explain(case.case_id, open_states)
    return ConflictsOut(case_id=case.case_id, conflicts=[
        ConflictOut(**s.model_dump(), can_resolve=can_resolve(case, actor, s.severity), explanation=said[s.field].text, explanation_origin=said[s.field].origin,
                    cited_source_ids=said[s.field].cited_source_ids, suggestion=_suggestion(db, case.case_id, s.field))
        for s in open_states
    ])  # fmt: skip


@router.post("/{case_id}/conflicts/{field}/suggest")
def suggest(field: str, body: SuggestIn, case: AccessibleCase, db: Db, actor: CurrentActor) -> SuggestionOut:
    """The assigned operations user suggests one of the source values, or leaves the choice to the attorney."""
    if actor.role != ActorRole.OPS or case.assigned_ops_user != actor.label:
        raise _refuse(actor, AuditAction.CONFLICT_SUGGESTED, case.case_id, field, "Only the assigned operations user can suggest")
    state = _state(engine.read(db, case.case_id), field)
    reason = " ".join(body.reason.split())
    if not reason:
        raise AppError("REASON_REQUIRED", "Give a reason for the suggestion", 400)
    if state.state not in NEEDS_ATTENTION:
        raise AppError("NOT_A_CONFLICT", f"{state.label} has no open conflict", 409)
    chosen = None
    if not body.leave_to_attorney:
        shown = engine.source_values(state)
        chosen = shown.get(compare_key(normalize(field, body.value or "", sources.date_fields(db))))
        if chosen is None:
            raise AppError("VALUE_NOT_A_SOURCE", "Pick one of the values the sources give, or leave it to the attorney", 422)
    with transaction(db):
        db.execute(
            text("INSERT INTO conflict_suggestions (case_id, field, suggested_value, leave_to_attorney, reason, actor) "
                 "VALUES (:c, :f, :v, :l, :r, :a)"),
            {"c": case.case_id, "f": field, "v": chosen, "l": body.leave_to_attorney, "r": reason, "a": actor.label},
        )  # fmt: skip
        ids = [s.source_id for s in state.sources if chosen is not None and compare_key(s.value) == compare_key(chosen)]
        audit.record(db, actor=actor, action=AuditAction.CONFLICT_SUGGESTED, case_id=case.case_id, target_type="field",
                     target_id=field, evidence_ids=ids, details={"reason": reason, "leave_to_attorney": body.leave_to_attorney})  # fmt: skip
        saved = _suggestion(db, case.case_id, field)
    return saved  # type: ignore[return-value]


def _chosen_value(state: FieldState, body: ResolveIn, dates: tuple[str, ...]) -> tuple[str, str | None, str | None]:
    """The value to store, the source it came from and the reason. A typed value needs a reason and a real date."""
    value = normalize(state.field, body.value, dates)
    reason = " ".join((body.reason or "").split()) or None
    source = next((s for s in state.sources if compare_key(s.value) == compare_key(value)), None)
    if source is not None:
        return source.value, source.source_id, reason
    if reason is None:
        raise AppError("REASON_REQUIRED", "Give a reason when you type a value that no source gives", 400)
    if state.field in dates and parse_date(value) is None:
        raise AppError("INVALID_DATE", "Enter the date as YYYY-MM-DD", 422)
    return value, None, reason


@router.post("/{case_id}/profile/{field}/confirm")
def confirm_profile(field: str, case: AccessibleCase, db: Db, actor: CurrentActor) -> FieldState:
    """A person confirms an imported profile value. This records who and when, and the value then counts as verified."""
    assigned = (actor.role == ActorRole.OPS and case.assigned_ops_user == actor.label) or (
        actor.role == ActorRole.LEGAL and case.assigned_legal_reviewer == actor.label)
    if not assigned:
        raise _refuse(actor, AuditAction.PROFILE_CONFIRMED, case.case_id, field, "Only the assigned operations user or legal reviewer can confirm a profile value")
    row = db.execute(text("SELECT verification_state FROM profile_fields WHERE case_id = :c AND field_name = :f"),
                     {"c": case.case_id, "f": field}).first()  # fmt: skip
    if row is None or row.verification_state == "DRAFT_PLACEHOLDER":
        raise AppError("NO_PROFILE_VALUE", f"{field} has no profile value to confirm", 404)
    if row.verification_state == "HUMAN_VERIFIED":
        return _state(engine.read(db, case.case_id), field)
    with transaction(db):
        db.execute(
            text("UPDATE profile_fields SET verification_state = 'HUMAN_VERIFIED', verified_at = now(), verified_by = :a, "
                 "note = :n, updated_at = now() WHERE case_id = :c AND field_name = :f"),
            {"a": actor.label, "n": f"Confirmed in app by {actor.label}", "c": case.case_id, "f": field},
        )  # fmt: skip
        confirmed = _state(engine.rebuild_facts(db, case.case_id), field)
        audit.record(db, actor=actor, action=AuditAction.PROFILE_CONFIRMED, case_id=case.case_id, target_type="field", target_id=field,
                     before_state={"verification_state": row.verification_state}, after_state={"verification_state": "HUMAN_VERIFIED"},
                     details={"role": actor.role.value})  # fmt: skip
    return confirmed


@router.post("/{case_id}/conflicts/{field}/resolve")
def resolve(field: str, body: ResolveIn, case: AccessibleCase, db: Db, actor: CurrentActor, tasks: BackgroundTasks) -> FieldState:
    """The assigned legal reviewer decides any conflict. The assigned operations user decides a medium one only."""
    if not can_resolve(case, actor, engine.severity_of(field)):
        mine = actor.role == ActorRole.OPS and case.assigned_ops_user == actor.label
        note = IDENTITY_NOTE if mine else "Only the assigned legal reviewer or operations user can resolve a conflict"
        raise _refuse(actor, AuditAction.CONFLICT_RESOLVED, case.case_id, field, note)
    state = _state(engine.read(db, case.case_id), field)
    if state.state not in (*NEEDS_ATTENTION, HUMAN_DECIDED):
        raise AppError("NOTHING_TO_RESOLVE", f"{state.label} has no conflict to resolve", 409)
    value, source_ref, reason = _chosen_value(state, body, sources.date_fields(db))
    if reason is None and actor.role == ActorRole.OPS:
        raise AppError("REASON_REQUIRED", "Give a reason for the decision", 400)
    if state.state == HUMAN_DECIDED and state.value is not None and compare_key(state.value) == compare_key(value):
        return state
    with transaction(db):
        db.execute(
            text("INSERT INTO review_decisions (decision_id, case_id, field_name, corrected_value, decision, reviewer_role, "
                 "reviewer_id, reason, source_ref, recorded_at) VALUES (:d, :c, :f, :v, 'APPROVED', :role, :a, :r, :s, now())"),
            {"d": f"DEC-FACT-{uuid.uuid4().hex[:12]}", "c": case.case_id, "f": field, "v": value, "role": actor.role.value, "a": actor.label, "r": reason, "s": source_ref},
        )  # fmt: skip
        decided = _state(engine.rebuild_facts(db, case.case_id), field)
        audit.record(db, actor=actor, action=AuditAction.CONFLICT_RESOLVED, case_id=case.case_id, target_type="field", target_id=field,
                     before_state={"state": state.state}, after_state={"state": HUMAN_DECIDED},
                     evidence_ids=[source_ref] if source_ref else [], details={"reason": reason or "Chose a source value", "typed": source_ref is None, "role": actor.role.value})  # fmt: skip
    if field == "full_name":
        # Files held back because their applicant differed from the case client are checked again against the decided name.
        ingest.start_case_job(db, tasks, actor, case.case_id, (UploadOutcome.NEEDS_HUMAN_REVIEW.value,), "ANALYSE")
    return decided
