"""Proposals for legal review: propose, list, review, commit and the approved form PDF. Rules live in app.cases.proposals."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sqlalchemy import text

from app.cases import exceptions, form_draft, packet, proposals, repository
from app.cases.access import AccessibleCase, assigned_to
from app.core import audit
from app.core.contracts import AuditAction, ProposalKind, ProposalStatus, ReviewChoice
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.db.session import get_db
from app.validation import deadlines

router = APIRouter(prefix="/api", tags=["proposals"])

Db = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


class ProposeIn(BaseModel):
    kind: ProposalKind
    idempotency_key: str = Field(min_length=8, max_length=100)
    value: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewIn(BaseModel):
    decision: ReviewChoice
    reason: str | None = Field(default=None, max_length=1000)


class SendBackIn(BaseModel):
    kind: str
    note: str = Field(max_length=1000)
    suggested_date: date | None = None


def _check_deadline(db: Session, case_id: str, value: dict[str, Any]) -> None:
    """Recompute the deadline with the one validation implementation and refuse a value that differs."""
    ctx = repository.load_context(db)
    due = deadlines.build_due(repository.list_events(db, case_id), ctx.deadline, False, ctx.as_of)
    if failed := deadlines.check_proposed_value(value, due):
        raise AppError(failed.code.value, failed.message, 400)


@router.get("/cases/{case_id}/form-draft")
def get_form_draft(case: AccessibleCase, db: Db) -> dict[str, Any]:
    """The server's draft for this case. The page only shows it."""
    draft = form_draft.build_form_draft(db, case.case_id)
    db.commit()  # the rebuild writes the facts and opens review requests
    return draft


@router.get("/cases/{case_id}/packet")
def get_packet(case: AccessibleCase, db: Db) -> dict[str, Any]:
    """The evidence index built from the checklist. Only usable documents are listed under their category."""
    return packet.build_packet_index(db, case.case_id)


@router.get("/cases/{case_id}/notes")
def list_notes(case: AccessibleCase, db: Db) -> list[proposals.CaseNote]:
    return proposals.list_notes(db, case.case_id)


@router.get("/cases/{case_id}/proposals")
def list_case_proposals(case: AccessibleCase, db: Db) -> list[proposals.Proposal]:
    return proposals.list_for_case(db, case.case_id)


def _is_repeat(db: Session, key: str) -> bool:
    """A repeated key returns the proposal that was sent first, so it is never refused again."""
    return db.execute(text("SELECT 1 FROM proposals WHERE idempotency_key = :k"), {"k": key}).first() is not None


@router.post("/cases/{case_id}/proposals", status_code=201)
def create_proposal(body: ProposeIn, case: AccessibleCase, db: Db, actor: CurrentActor) -> proposals.Proposal:
    """A form export is always built here from the case evidence, never taken from the request."""
    if body.kind == ProposalKind.MESSAGE_APPROVE:
        raise AppError("USE_DRAFT_SUBMIT", "Send a message draft for review from its draft instead", 400)
    if body.kind == ProposalKind.FORM_EXPORT:
        # A repeated key returns the proposal that was sent first. A new one is refused while the case has an open exception.
        blocking = [] if _is_repeat(db, body.idempotency_key) else exceptions.blocking_items(db, actor, case.case_id)
        if blocking:
            reason = f"{len(blocking)} {'exception is' if len(blocking) == 1 else 'exceptions are'} still open on this case, settle {'it' if len(blocking) == 1 else 'them'} before sending to legal"
            audit.record_denied(reason=reason, actor=actor, action=AuditAction.PROPOSE, case_id=case.case_id, target_type="case", target_id=case.case_id)
            raise AppError("OPEN_EXCEPTIONS", reason, 409)
        draft = form_draft.build_form_draft(db, case.case_id)
        refs = sorted({ref for row in draft["fields"] for ref in row["evidence_refs"]})
        created = proposals.propose(
            db, actor, case, kind=body.kind, idempotency_key=body.idempotency_key, value=draft, evidence_ids=refs,
            target_type="form", target_id=draft["form_id"],
        )  # fmt: skip
    elif body.kind == ProposalKind.PACKET_APPROVE:
        index = packet.build_packet_index(db, case.case_id)
        if index["usable_count"] == 0:
            raise AppError("PACKET_EMPTY", "No usable document yet, so there is no packet to approve", 400)
        if not _is_repeat(db, body.idempotency_key):
            blocking = exceptions.blocking_items(db, actor, case.case_id)
            gaps = len(index["missing"]) + len(index["not_usable_labels"])
            if blocking or gaps:
                reason = f"Resolve {len(blocking)} open exception(s) and {gaps} missing or unusable document(s) before sending to legal"
                audit.record_denied(reason=reason, actor=actor, action=AuditAction.PROPOSE, case_id=case.case_id, target_type="case", target_id=case.case_id)
                raise AppError("OPEN_EXCEPTIONS", reason, 409)
        created = proposals.propose(
            db, actor, case, kind=body.kind, idempotency_key=body.idempotency_key, value=index,
            evidence_ids=index["usable_ids"], target_type="packet", target_id=index["packet_id"],
        )  # fmt: skip
    else:
        if body.value is None:
            raise AppError("VALUE_REQUIRED", "Send the value to propose", 400)
        if body.kind == ProposalKind.DEADLINE_ACTIVATE:
            _check_deadline(db, case.case_id, body.value)
        if body.kind == ProposalKind.STAGE_CHANGE:
            created = proposals.change_stage(
                db, actor, case, idempotency_key=body.idempotency_key, value=proposals.check_stage(case, body.value)
            )
            db.commit()
            return created
        created = proposals.propose(
            db, actor, case, kind=body.kind, idempotency_key=body.idempotency_key, value=body.value,
            evidence_ids=body.evidence_ids,
        )  # fmt: skip
    db.commit()
    return created


@router.get("/proposals")
def list_proposals(db: Db, actor: CurrentActor, status: ProposalStatus | None = None) -> list[proposals.Proposal]:
    return proposals.list_for_actor(db, actor, status)


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str, db: Db, actor: CurrentActor) -> proposals.Proposal:
    """One proposal for the review screen. Only the OPS owner and the assigned LEGAL reviewer can open it."""
    proposal = proposals.get(db, proposal_id)
    case = repository.get_case(db, proposal.case_id, repository.get_as_of(db))
    if case is None or not assigned_to(case, actor):
        reason = f"{actor.label} is not assigned to this case"
        audit.record_denied(reason=reason, actor=actor, action=AuditAction.CASE_ACCESS, case_id=proposal.case_id,
                            target_type="proposal", target_id=proposal_id)  # fmt: skip
        raise AppError("CASE_NOT_ASSIGNED", reason, 403)
    return proposal.model_copy(update={"client_name": case.display_name})


@router.post("/proposals/{proposal_id}/review")
def review_proposal(proposal_id: str, body: ReviewIn, db: Db, actor: CurrentActor) -> proposals.Proposal:
    decided = proposals.review(db, actor, proposal_id, body.decision, body.reason)
    db.commit()
    return decided


@router.post("/proposals/{proposal_id}/send-back")
def send_back_proposal(proposal_id: str, body: SendBackIn, db: Db, actor: CurrentActor) -> proposals.Proposal:
    """A different date saved as a note, or a question. Neither approves or rejects the proposal."""
    sent = proposals.send_back(db, actor, proposal_id, kind=body.kind, body=body.note, suggested_date=body.suggested_date)
    db.commit()
    return sent


@router.post("/proposals/{proposal_id}/commit")
def commit_proposal(proposal_id: str, db: Db, actor: CurrentActor) -> proposals.Proposal:
    committed = proposals.commit(db, actor, proposal_id)
    db.commit()
    return committed


@router.get("/proposals/{proposal_id}/export.pdf")
def export_form_pdf(proposal_id: str, db: Db, actor: CurrentActor) -> Response:
    """The approved form as a watermarked PDF. Only a form export that a legal reviewer approved can be downloaded."""
    proposal = proposals.get(db, proposal_id)
    case = repository.get_case(db, proposal.case_id, repository.get_as_of(db))
    if case is None or not assigned_to(case, actor):
        reason = f"{actor.label} is not assigned to this case"
        audit.record_denied(reason=reason, actor=actor, action=AuditAction.FORM_EXPORTED, case_id=proposal.case_id,
                            target_type="proposal", target_id=proposal_id)  # fmt: skip
        raise AppError("CASE_NOT_ASSIGNED", reason, 403)
    approved = proposal.status in (ProposalStatus.APPROVED, ProposalStatus.COMMITTED)
    if proposal.kind != ProposalKind.FORM_EXPORT or not approved or proposal.reviewed_at is None:
        raise AppError("NOT_APPROVED", "Only an approved form export can be downloaded", 409)
    from app.cases.form_pdf import render_form_pdf  # reportlab loads on the first export

    data = proposal.value
    pdf = render_form_pdf(
        case_id=case.case_id, client_name=case.display_name, form_id=data["form_id"], sections=data["sections"],
        fields=data["fields"], proposal_id=proposal.proposal_id, approved_by=proposal.reviewed_by or "",
        approved_at=proposal.reviewed_at,
    )  # fmt: skip
    audit.record(db, actor=actor, action=AuditAction.FORM_EXPORTED, case_id=case.case_id, target_type="proposal",
                 target_id=proposal.proposal_id, evidence_ids=proposal.evidence_ids)  # fmt: skip
    db.commit()
    headers = {"Content-Disposition": f'attachment; filename="{case.case_id}-form-draft.pdf"'}
    return Response(content=pdf, media_type="application/pdf", headers=headers)
