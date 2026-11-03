"""Case queue, header, sources and timeline. Routes stay thin: rules live in app.cases.service."""

import secrets
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import communications, repository, service
from app.cases.access import AccessibleCase
from app.core import audit
from app.core.contracts import AuditAction, SourceKind
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.db.session import get_db, transaction
from app.ingest import draft
from app.ingest import service as ingest
from app.validation import deadlines

router = APIRouter(prefix="/api/cases", tags=["cases"])
# Newest ledger lines kept on the Case activity lane. The Activity tab pages through all of them.
ACTIVITY_LIMIT = 500

Db = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


class QueueOut(BaseModel):
    as_of: date
    groups: list[service.QueueGroup]


class PortalStatus(BaseModel):
    event_id: str
    date: date
    label: str | None
    details: str


class CaseOut(BaseModel):
    case_id: str
    name: str
    number: str
    archetype: str
    stage: str
    stage_code: str
    ops_user: str
    legal_reviewer: str
    workflow_status: str
    portal_status: PortalStatus | None


class SourcesOut(BaseModel):
    intake_notes: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    profile_fields: list[dict[str, Any]]
    events: list[dict[str, Any]]


class TimelineOut(BaseModel):
    as_of: date
    items: list[service.TimelineItem]


@router.get("")
def list_cases(db: Db, actor: CurrentActor, q: str | None = None, group: str | None = None) -> QueueOut:
    as_of = repository.get_as_of(db)
    records = repository.list_cases_for_actor(db, actor=actor.label, role=actor.role, term=q, as_of=as_of)
    groups = service.build_queue(actor.role, records)
    return QueueOut(as_of=as_of, groups=[g for g in groups if group is None or g.key == group])


@router.get("/{case_id}")
def get_case(case: AccessibleCase, db: Db, actor: CurrentActor, tasks: BackgroundTasks) -> CaseOut:
    ingest.ensure_case_read(db, tasks, actor, case.case_id)  # fire and forget, never fails this request
    status = repository.get_portal_status(db, case.case_id)
    portal = (
        PortalStatus(
            event_id=status["event_id"], date=status["event_date"], details=status["details"],
            label=service.portal_status_label(status["details"]),
        )  # fmt: skip
        if status
        else None
    )
    return CaseOut(
        case_id=case.case_id, name=case.display_name, number=service.case_number(case.case_id),
        archetype=service.humanize(case.case_archetype), stage=service.humanize(case.operational_stage), stage_code=case.operational_stage,
        ops_user=case.assigned_ops_user, legal_reviewer=case.assigned_legal_reviewer,
        workflow_status=case.status, portal_status=portal,
    )  # fmt: skip


@router.get("/{case_id}/sources")
def get_sources(case: AccessibleCase, db: Db) -> SourcesOut:
    """Claims and evidence side by side, each row labelled with its source kind."""
    claim, evidence = SourceKind.CLAIM.value, SourceKind.EVIDENCE.value
    events = [
        {**event, "source_kind": evidence if service.is_evidence_event(event) else claim}
        for event in repository.list_events(db, case.case_id)
    ]
    return SourcesOut(
        intake_notes=[{**row, "source_kind": claim} for row in repository.list_intake_notes(db, case.case_id)],
        messages=[{**row, "source_kind": claim} for row in repository.list_messages(db, case.case_id)],
        profile_fields=[{**row, "source_kind": evidence} for row in repository.list_profile_fields(db, case.case_id)],
        events=events,
    )


@router.get("/{case_id}/timeline")
def get_timeline(case: AccessibleCase, db: Db) -> TimelineOut:
    ctx = repository.load_context(db)
    events = repository.list_events(db, case.case_id)
    due = deadlines.build_due(events, ctx.deadline, False, ctx.as_of)  # the one deadline implementation
    calls = service.communication_items(communications.list_communications(db, case.case_id))
    _, entries = audit.list_entries(db, case.case_id, actions=service.ACTIVITY_ACTIONS, limit=ACTIVITY_LIMIT)
    activity = service.activity_items(entries)
    return TimelineOut(as_of=ctx.as_of, items=service.build_timeline(events, ctx.as_of, due, calls + activity))


class CalendarEventIn(BaseModel):
    event_date: date
    event_type: Literal["CALENDAR_DEADLINE", "CALENDAR_REMINDER", "CALENDAR_NOTE"]
    details: str = Field(min_length=1, max_length=500)


@router.post("/{case_id}/calendar-events", status_code=201)
def add_calendar_event(case: AccessibleCase, db: Db, body: CalendarEventIn) -> TimelineOut:
    """Demo control: type an office calendar entry by hand. It is stored unverified, so it is a claim and
    can never set a deadline. A deadline entry that disagrees with the portal shows as wrong."""
    details = " ".join(body.details.split())
    code = secrets.token_hex(3).upper()
    with transaction(db):
        stored = repository.add_calendar_event(
            db, case.case_id, event_date=body.event_date, event_type=body.event_type, details=details,
            event_id=f"EV-{service.case_number(case.case_id)}-CAL-{code}", reference=f"CAL-MANUAL-{code}",
        )  # fmt: skip
        if not stored:
            raise AppError("CALENDAR_EVENT_EXISTS", "That calendar entry is already on the timeline", 409)
    return get_timeline(case, db)


@router.delete("/{case_id}/calendar-events/{event_id}")
def delete_calendar_event(case: AccessibleCase, db: Db, event_id: str) -> TimelineOut:
    """Undo for the demo form. Only entries added through it can be removed."""
    with transaction(db):
        if not repository.delete_calendar_event(db, case.case_id, event_id):
            raise AppError("CALENDAR_EVENT_NOT_FOUND", "No demo calendar entry with that id on this case", 404)
    return get_timeline(case, db)


@router.delete("/{case_id}")
def delete_case(case: AccessibleCase, db: Db, actor: CurrentActor) -> dict[str, str]:
    """Delete a case. It disappears from every list and its page, and only the assigned operations user or legal reviewer
    may do it. A draft owns nothing worth keeping and is removed. Any other case keeps its rows and its ledger lines, because
    reviews and the audit trail are insert only, and is marked DELETED so nothing shows it."""
    if case.status == "DRAFT":
        draft.discard(db, actor, case.case_id)
        return {"case_id": case.case_id, "status": "DELETED"}
    with transaction(db):
        db.execute(text("UPDATE case_workflows SET status = 'DELETED', updated_at = now() WHERE case_id = :c"), {"c": case.case_id})
        audit.record(db, actor=actor, action=AuditAction.CASE_DELETED, case_id=case.case_id, target_type="case", target_id=case.case_id,
                     before_state={"status": case.status}, after_state={"status": "DELETED"})  # fmt: skip
    return {"case_id": case.case_id, "status": "DELETED"}
