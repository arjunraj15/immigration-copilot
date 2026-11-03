"""New data for one case, such as a judge's changed event, Zoom note or client message. Nothing is ever turned into a fact:
a note and a message stay claims, a calendar entry stays unverified, and only a portal event may carry the verified flag, and only the legal reviewer may set it.
The same record twice is stored once. Human decisions live in their own table and an import never touches them."""

import hashlib
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import repository
from app.cases.loader import EVENT_CONTENT, _upsert
from app.cases.repository import CaseRecord
from app.core import audit
from app.core.contracts import ActorRole, AuditAction
from app.core.errors import AppError
from app.core.security import Actor
from app.facts import engine
from app.validation import deadlines

PORTAL, CALENDAR = "MOCK_PORTAL", "GOOGLE_CALENDAR_MOCK"
BATCH = "IMPORT"
INSERTED, UPDATED, UNCHANGED, DUPLICATE = "INSERTED", "UPDATED", "UNCHANGED", "DUPLICATE_CONTENT"
NAME_RE = r"^[A-Z][A-Z0-9_]{2,59}$"


class EventIn(BaseModel):
    kind: Literal["EVENT"]
    event_id: str | None = Field(None, max_length=40)
    event_date: date
    event_type: str = Field(pattern=NAME_RE)
    event_source: Literal["MOCK_PORTAL", "GOOGLE_CALENDAR_MOCK"]
    source_reference: str = Field(min_length=1, max_length=80)
    details: str = Field(min_length=1, max_length=500)
    source_verified: bool = False


class NoteIn(BaseModel):
    kind: Literal["ZOOM_NOTE"]
    intake_id: str | None = Field(None, max_length=40)
    recorded_at: datetime
    speaker: str = Field("Intake Coordinator", min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=4000)
    raw_note_excerpt: str = Field("", max_length=4000)


class MessageIn(BaseModel):
    kind: Literal["MESSAGE"]
    message_id: str | None = Field(None, max_length=40)
    thread_id: str | None = Field(None, max_length=40)
    created_at: datetime
    channel: Literal["EMAIL", "WHATSAPP"]
    subject: str = Field("", max_length=200)
    body: str = Field(min_length=1, max_length=4000)


ImportIn = Annotated[EventIn | NoteIn | MessageIn, Field(discriminator="kind")]


class Change(BaseModel):
    field: str
    label: str
    before_state: str | None
    after_state: str | None
    before_value: str | None
    after_value: str | None


class DeadlineChange(BaseModel):
    before: str | None
    after: str | None
    before_state: str | None
    after_state: str | None


class ImportResult(BaseModel):
    case_id: str
    kind: str
    record_id: str
    result: str
    duplicate_of: str | None = None
    changes: list[Change] = []
    deadline: DeadlineChange | None = None


def _digest(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:8].upper()


def _number(case_id: str) -> str:
    return case_id.removeprefix("CASE-")


def _guard(db: Session, table: str, key: str, record_id: str, case_id: str) -> None:
    """A record id that belongs to another case is never touched, so an import cannot reach across cases."""
    owner = db.scalar(text(f"SELECT case_id FROM {table} WHERE {key} = :i"), {"i": record_id})
    if owner is not None and owner != case_id:
        raise AppError("RECORD_IN_OTHER_CASE", f"{record_id} belongs to another case", 409)


def _event(db: Session, case_id: str, item: EventIn) -> tuple[str, str, str | None]:
    if item.source_verified and item.event_source != PORTAL:
        raise AppError("ONLY_PORTAL_VERIFIED", "Only a portal event can be marked verified. A calendar entry is always a claim", 422)
    content = (case_id, item.event_date, item.event_type, item.event_source, item.source_reference, " ".join(item.details.split()))
    event_id = item.event_id or f"EV-{_number(case_id)}-IMP-{_digest(*content)}"
    _guard(db, "case_events", "event_id", event_id, case_id)
    twin = db.scalar(
        text(f"SELECT event_id FROM case_events WHERE event_id <> :i AND ({', '.join(EVENT_CONTENT)}) = (:c, :d, :t, :s, :r, :x)"),
        {"i": event_id, "c": content[0], "d": content[1], "t": content[2], "s": content[3], "r": content[4], "x": content[5]},
    )
    if twin:
        return event_id, DUPLICATE, twin
    row = dict(zip(EVENT_CONTENT, content, strict=True)) | {
        "event_id": event_id, "source_verified": item.source_verified, "import_batch": BATCH}
    return event_id, _result(_upsert(db, "case_events", "event_id", [row])), None


def _note(db: Session, case_id: str, item: NoteIn) -> tuple[str, str, str | None]:
    summary = " ".join(item.summary.split())
    note_id = item.intake_id or f"Z-IMP-{_digest(case_id, item.recorded_at, summary)}"
    _guard(db, "intake_notes", "intake_id", note_id, case_id)
    row = {"intake_id": note_id, "case_id": case_id, "recorded_at": item.recorded_at, "platform": "ZOOM_AI_SYNTHETIC",
           "speaker": item.speaker, "summary": summary, "raw_note_excerpt": item.raw_note_excerpt,
           "ai_generated": True, "approved_as_fact": False}  # fmt: skip
    return note_id, _result(_upsert(db, "intake_notes", "intake_id", [row])), None


def _message(db: Session, case_id: str, item: MessageIn) -> tuple[str, str, str | None]:
    body = " ".join(item.body.split())
    message_id = item.message_id or f"MSG-IMP-{_digest(case_id, item.created_at, item.channel, body)}"
    _guard(db, "messages", "message_id", message_id, case_id)
    row = {"message_id": message_id, "case_id": case_id, "thread_id": item.thread_id or f"THR-{_number(case_id)}",
           "created_at_source": item.created_at, "channel": item.channel, "direction": "INBOUND", "sender_role": "CLIENT",
           "subject": item.subject, "body": body, "attachment_refs": [], "delivery_state": "RECORDED_MOCK"}  # fmt: skip
    return message_id, _result(_upsert(db, "messages", "message_id", [row])), None


def _result(report) -> str:
    return INSERTED if report.inserted else UPDATED if report.updated else UNCHANGED


_STORES = {"EVENT": ("case_events", _event), "ZOOM_NOTE": ("intake_notes", _note), "MESSAGE": ("messages", _message)}
_CLAIM_SOURCE = {"ZOOM_NOTE", "MESSAGE"}


def _due(db: Session, case_id: str) -> deadlines.Due | None:
    ctx = repository.load_context(db)
    return deadlines.build_due(repository.list_events(db, case_id), ctx.deadline, False, ctx.as_of)


def _diff(before: list[engine.FieldState], after: list[engine.FieldState]) -> list[Change]:
    old = {s.field: s for s in before}
    return [
        Change(field=s.field, label=s.label, before_state=old[s.field].state if s.field in old else None, after_state=s.state,
               before_value=old[s.field].value if s.field in old else None, after_value=s.value)
        for s in after
        if s.field not in old or (old[s.field].state, old[s.field].value) != (s.state, s.value)
    ]  # fmt: skip


def import_record(db: Session, actor: Actor, case: CaseRecord, item: EventIn | NoteIn | MessageIn) -> ImportResult:
    """Store the record, audit it, rebuild the field states and say what changed. A repeat changes nothing."""
    _, store = _STORES[item.kind]
    verified = item.kind == "EVENT" and item.source_verified
    if verified and item.event_source != PORTAL:
        raise AppError("ONLY_PORTAL_VERIFIED", "Only a portal event can be marked verified. A calendar entry is always a claim", 422)
    if verified and actor.role != ActorRole.LEGAL:
        reason = f"{actor.label} cannot mark a portal event verified, only the assigned legal reviewer can"
        audit.record_denied(reason=reason, actor=actor, action=AuditAction.DATA_IMPORTED, case_id=case.case_id,
                            target_type="case_events", target_id=item.event_id or case.case_id)  # fmt: skip
        raise AppError("VERIFIED_IMPORT_LEGAL_ONLY", reason, 403)
    before = engine.read(db, case.case_id)
    due_before = _due(db, case.case_id)
    record_id, result, twin = store(db, case.case_id, item)
    if result in (INSERTED, UPDATED) and item.kind in _CLAIM_SOURCE:
        db.execute(text("DELETE FROM claims WHERE case_id = :c AND source_id = :s"), {"c": case.case_id, "s": record_id})
    audit.record(
        db, actor=actor, action=AuditAction.DATA_IMPORTED, case_id=case.case_id, target_type=_STORES[item.kind][0],
        target_id=record_id, evidence_ids=[record_id, *([twin] if twin else [])],
        details={"kind": item.kind, "result": result, **({"duplicate_of": twin} if twin else {}),
                 **({"event_source": item.event_source, "source_verified": item.source_verified} if item.kind == "EVENT" else {})},
    )  # fmt: skip
    db.commit()
    changes: list[Change] = []
    if result in (INSERTED, UPDATED):
        engine.recompute(db, case.case_id)
        changes = _diff(before, engine.read(db, case.case_id))
    due_after = _due(db, case.case_id)
    moved = (due_before and due_before.date, due_before and due_before.state) != (due_after and due_after.date, due_after and due_after.state)
    deadline = DeadlineChange(
        before=due_before.date.isoformat() if due_before else None, after=due_after.date.isoformat() if due_after else None,
        before_state=due_before.state if due_before else None, after_state=due_after.state if due_after else None,
    ) if moved else None  # fmt: skip
    return ImportResult(case_id=case.case_id, kind=item.kind, record_id=record_id, result=result, duplicate_of=twin,
                        changes=changes, deadline=deadline)  # fmt: skip
