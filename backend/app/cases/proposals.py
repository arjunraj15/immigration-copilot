"""Proposals: sensitive changes that OPS drafts, the assigned LEGAL reviewer decides, and OPS commits (flow figure 4).

Every step writes its audit line in the caller's transaction and the route commits. The same idempotency key
twice returns the same proposal, and a human decision is never overwritten by a rerun."""

import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import repository, stage
from app.cases.repository import CaseRecord
from app.core import audit
from app.core.contracts import ActorRole, AuditAction, ProposalKind, ProposalStatus, ReviewChoice
from app.core.errors import AppError
from app.core.security import Actor

COLUMNS = (
    "proposal_id, case_id, kind, status, idempotency_key, target_type, target_id, value, evidence_ids, "
    "proposed_by, reviewed_by, review_reason, committed_by, proposed_at, reviewed_at, committed_at"
)
DECIDED = {ReviewChoice.APPROVE: ProposalStatus.APPROVED, ReviewChoice.REJECT: ProposalStatus.REJECTED}
STAGES = ("INTAKE_REVIEW", "DOCUMENT_COLLECTION", "EVIDENCE_REVIEW", "READY_FOR_LEGAL_REVIEW", "WAITING_FOR_PORTAL_EVENT", "ON_HOLD")
WORKFLOW = {ProposalStatus.APPROVED: "APPROVED", ProposalStatus.REJECTED: "REJECTED", ProposalStatus.COMMITTED: "APPLIED"}


class CaseNote(BaseModel):
    kind: str
    body: str
    suggested_date: date | None
    author: str
    proposal_id: str | None
    created_at: datetime


class Proposal(BaseModel):
    proposal_id: str
    case_id: str
    kind: ProposalKind
    status: ProposalStatus
    idempotency_key: str
    target_type: str | None
    target_id: str | None
    value: dict[str, Any]
    evidence_ids: list[str]
    proposed_by: str
    reviewed_by: str | None
    review_reason: str | None
    committed_by: str | None
    proposed_at: datetime
    reviewed_at: datetime | None
    committed_at: datetime | None
    client_name: str | None = None  # filled by list_for_actor and get_for_actor so a table can show who the case is about


def _refuse(actor: Actor, action: AuditAction, case_id: str, proposal_id: str | None, reason: str) -> AppError:
    """Log the refused attempt and return the error to raise."""
    audit.record_denied(reason=reason, actor=actor, action=action, case_id=case_id, target_type="proposal", target_id=proposal_id)
    return AppError("ACTION_NOT_ALLOWED", reason, 403)


def get(db: Session, proposal_id: str, *, lock: bool = False) -> Proposal:
    suffix = " FOR UPDATE" if lock else ""
    row = db.execute(text(f"SELECT {COLUMNS} FROM proposals WHERE proposal_id = :id{suffix}"), {"id": proposal_id}).first()
    if row is None:
        raise AppError("PROPOSAL_NOT_FOUND", f"No proposal {proposal_id}", 404)
    return Proposal.model_validate(row._mapping)


def _case(db: Session, case_id: str) -> CaseRecord:
    record = repository.get_case(db, case_id, repository.get_as_of(db))
    if record is None:
        raise AppError("CASE_NOT_FOUND", f"No case {case_id}", 404)
    return record


def list_for_case(db: Session, case_id: str) -> list[Proposal]:
    rows = db.execute(text(f"SELECT {COLUMNS} FROM proposals WHERE case_id = :case_id ORDER BY id DESC"), {"case_id": case_id}).all()
    return [Proposal.model_validate(row._mapping) for row in rows]


def list_for_actor(db: Session, actor: Actor, status: ProposalStatus | None = None) -> list[Proposal]:
    """OPS sees proposals on the cases assigned to them and LEGAL sees the ones assigned for review."""
    owner = "c.assigned_ops_user" if actor.role == ActorRole.OPS else "c.assigned_legal_reviewer"
    columns = ", ".join(f"p.{name}" for name in COLUMNS.split(", "))
    rows = db.execute(
        text(
            f"SELECT {columns} FROM proposals p JOIN cases c ON c.case_id = p.case_id "
            f"WHERE {owner} = :actor AND (CAST(:status AS text) IS NULL OR p.status = :status) ORDER BY p.id DESC"
        ),
        {"actor": actor.label, "status": status.value if status else None},
    ).all()
    found = [Proposal.model_validate(row._mapping) for row in rows]
    as_of = repository.get_as_of(db)
    names = {cid: record.display_name for cid in {p.case_id for p in found} if (record := repository.get_case(db, cid, as_of))}
    return [p.model_copy(update={"client_name": names.get(p.case_id)}) for p in found]


def list_notes(db: Session, case_id: str) -> list[CaseNote]:
    rows = db.execute(
        text("SELECT kind, body, suggested_date, author, proposal_id, created_at FROM case_notes WHERE case_id = :c ORDER BY id DESC"),
        {"c": case_id},
    ).all()
    return [CaseNote.model_validate(row._mapping) for row in rows]


def check_stage(case: CaseRecord, value: dict[str, Any]) -> dict[str, Any]:
    """A stage change names one of the six stages and differs from the current one. The from stage is set here, not by the caller."""
    target = value.get("to_stage")
    if target not in STAGES:
        raise AppError("STAGE_UNKNOWN", f"to_stage must be one of {', '.join(STAGES)}", 400)
    if target == case.operational_stage:
        raise AppError("STAGE_UNCHANGED", f"The case is already in {target}", 400)
    reason = str(value.get("reason") or "").strip()
    return {"from_stage": case.operational_stage, "to_stage": target, "reason": reason}


def _set_workflow(db: Session, case_id: str, status: str) -> None:
    db.execute(
        text("UPDATE case_workflows SET status = :status, updated_at = now() WHERE case_id = :case_id"),
        {"status": status, "case_id": case_id},
    )


def _follow_draft(db: Session, proposal: Proposal, decided: ProposalStatus) -> None:
    """A decided message approval moves its draft to the same status. Approved never means sent."""
    if proposal.kind != ProposalKind.MESSAGE_APPROVE or proposal.target_id is None:
        return
    db.execute(
        text("UPDATE message_drafts SET status = :status, updated_at = now() "
             "WHERE draft_id = :id AND case_id = :case_id AND status = 'PENDING_LEGAL_REVIEW'"),
        {"status": decided.value, "id": proposal.target_id, "case_id": proposal.case_id},
    )  # fmt: skip


def _prior_rejection(db: Session, case_id: str, kind: ProposalKind, value: dict[str, Any]) -> Proposal | None:
    row = db.execute(
        text(
            f"SELECT {COLUMNS} FROM proposals WHERE case_id = :case_id AND kind = :kind AND status = 'REJECTED' "
            "AND value = CAST(:value AS jsonb) ORDER BY id DESC LIMIT 1"
        ),
        {"case_id": case_id, "kind": kind.value, "value": json.dumps(value)},
    ).first()
    return Proposal.model_validate(row._mapping) if row else None


def propose(
    db: Session, actor: Actor, case: CaseRecord, *, kind: ProposalKind, idempotency_key: str,
    value: dict[str, Any], evidence_ids: list[str], target_type: str | None = None, target_id: str | None = None,
) -> Proposal:  # fmt: skip
    """OPS proposes. A repeated key returns the first proposal. An unchanged value that was rejected is not proposed again."""
    if actor.role != ActorRole.OPS or case.assigned_ops_user != actor.label:
        raise _refuse(actor, AuditAction.PROPOSE, case.case_id, None, "Only the assigned operations user can propose")
    existing = db.execute(text(f"SELECT {COLUMNS} FROM proposals WHERE idempotency_key = :key"), {"key": idempotency_key}).first()
    if existing is not None:
        if existing.case_id != case.case_id:
            raise AppError("IDEMPOTENCY_KEY_REUSED", "That key belongs to a different case", 409)
        return Proposal.model_validate(existing._mapping)
    rejected = _prior_rejection(db, case.case_id, kind, value)
    if rejected is not None:
        audit.record(
            db, actor=actor, action=AuditAction.RERUN_SKIPPED_PRIOR_REJECTION, case_id=case.case_id,
            target_type="proposal", target_id=rejected.proposal_id, idempotency_key=idempotency_key,
        )  # fmt: skip
        return rejected
    row = db.execute(
        text(
            f"INSERT INTO proposals (case_id, kind, idempotency_key, target_type, target_id, value, evidence_ids, proposed_by) "
            f"VALUES (:case_id, :kind, :key, :target_type, :target_id, CAST(:value AS jsonb), :evidence_ids, :actor) RETURNING {COLUMNS}"
        ),
        {
            "case_id": case.case_id, "kind": kind.value, "key": idempotency_key, "target_type": target_type,
            "target_id": target_id, "value": json.dumps(value), "evidence_ids": evidence_ids, "actor": actor.label,
        },
    ).one()  # fmt: skip
    proposal = Proposal.model_validate(row._mapping)
    db.execute(
        text(
            "UPDATE case_workflows SET status = 'WITH_ATTORNEY', submitted_by = :ops, submitted_to = :legal, "
            "submitted_at = now(), updated_at = now() WHERE case_id = :case_id"
        ),
        {"ops": actor.label, "legal": case.assigned_legal_reviewer, "case_id": case.case_id},
    )
    audit.record(
        db, actor=actor, action=AuditAction.PROPOSE, case_id=case.case_id, target_type="proposal",
        target_id=proposal.proposal_id, after_state={"status": proposal.status.value, "kind": kind.value},
        evidence_ids=evidence_ids, idempotency_key=idempotency_key,
    )  # fmt: skip
    if kind in stage.SUBMIT_KINDS:
        stage.submitted(db, actor, case.case_id)
    return proposal


def review(db: Session, actor: Actor, proposal_id: str, choice: ReviewChoice, reason: str | None) -> Proposal:
    """Only the LEGAL reviewer assigned to the case decides. Rejecting needs a reason. Deciding twice the same way is a no-op."""
    action = AuditAction.REVIEW_APPROVE if choice == ReviewChoice.APPROVE else AuditAction.REVIEW_REJECT
    proposal = get(db, proposal_id, lock=True)
    case = _case(db, proposal.case_id)
    if actor.role != ActorRole.LEGAL or case.assigned_legal_reviewer != actor.label:
        raise _refuse(actor, action, case.case_id, proposal_id, "Only the assigned legal reviewer can decide")
    decided = DECIDED[choice]
    if proposal.status == decided or (choice == ReviewChoice.APPROVE and proposal.status == ProposalStatus.COMMITTED):
        return proposal
    if proposal.status != ProposalStatus.PENDING_LEGAL_REVIEW:
        raise AppError("ALREADY_DECIDED", f"{proposal_id} is already {proposal.status.value}", 409)
    note = (reason or "").strip()
    if choice == ReviewChoice.REJECT and not note:
        raise AppError("REASON_REQUIRED", "Give a reason when rejecting", 400)
    row = db.execute(
        text(
            "UPDATE proposals SET status = :status, reviewed_by = :actor, review_reason = :reason, reviewed_at = now(), "
            f"updated_at = now() WHERE proposal_id = :id RETURNING {COLUMNS}"
        ),
        {"status": decided.value, "actor": actor.label, "reason": note or None, "id": proposal_id},
    ).one()
    db.execute(
        text(
            "INSERT INTO review_decisions (decision_id, case_id, proposal_id, decision, reviewer_role, reviewer_id, reason, recorded_at) "
            "VALUES (:decision_id, :case_id, :proposal_id, :decision, 'LEGAL', :actor, :reason, now())"
        ),
        {"decision_id": f"DEC-{proposal_id}", "case_id": case.case_id, "proposal_id": proposal_id, "decision": decided.value,
         "actor": actor.label, "reason": note or None},
    )  # fmt: skip
    _set_workflow(db, case.case_id, WORKFLOW[decided])
    if choice == ReviewChoice.REJECT and proposal.kind in stage.SUBMIT_KINDS:
        stage.rejected(db, actor, case.case_id)
    _follow_draft(db, proposal, decided)
    db.execute(text("UPDATE case_workflows SET decided_at = now() WHERE case_id = :case_id"), {"case_id": case.case_id})
    audit.record(
        db, actor=actor, action=action, case_id=case.case_id, target_type="proposal", target_id=proposal_id,
        before_state={"status": proposal.status.value}, after_state={"status": decided.value},
        evidence_ids=proposal.evidence_ids, details={"reason": note} if note else None,
    )  # fmt: skip
    return Proposal.model_validate(row._mapping)


def commit(db: Session, actor: Actor, proposal_id: str) -> Proposal:
    """OPS applies an approved proposal. Anything not approved is refused. A second commit returns the first result."""
    proposal = get(db, proposal_id, lock=True)
    case = _case(db, proposal.case_id)
    if actor.role != ActorRole.OPS or case.assigned_ops_user != actor.label:
        raise _refuse(actor, AuditAction.COMMIT, case.case_id, proposal_id, "Only the assigned operations user can commit")
    if proposal.status == ProposalStatus.COMMITTED:
        return proposal
    if proposal.status != ProposalStatus.APPROVED:
        raise AppError("NOT_APPROVED", "Commit is refused until a legal reviewer approves", 409)
    if proposal.kind == ProposalKind.STAGE_CHANGE and case.operational_stage not in (proposal.value["from_stage"], proposal.value["to_stage"]):
        raise AppError("STAGE_STALE", f"The case moved to {case.operational_stage} after this change was approved, so it must be proposed again", 409)
    row = db.execute(
        text(
            "UPDATE proposals SET status = 'COMMITTED', committed_by = :actor, committed_at = now(), updated_at = now() "
            f"WHERE proposal_id = :id RETURNING {COLUMNS}"
        ),
        {"actor": actor.label, "id": proposal_id},
    ).one()
    _set_workflow(db, case.case_id, WORKFLOW[ProposalStatus.COMMITTED])
    if proposal.kind == ProposalKind.STAGE_CHANGE:
        _apply_stage(db, actor, case, proposal)
    audit.record(
        db, actor=actor, action=AuditAction.COMMIT, case_id=case.case_id, target_type="proposal", target_id=proposal_id,
        before_state={"status": proposal.status.value}, after_state={"status": ProposalStatus.COMMITTED.value},
        evidence_ids=proposal.evidence_ids,
    )  # fmt: skip
    return Proposal.model_validate(row._mapping)


def change_stage(db: Session, actor: Actor, case: CaseRecord, *, idempotency_key: str, value: dict[str, Any]) -> Proposal:
    """The assigned OPS or LEGAL user moves the stage at once. The change is kept as a committed proposal and audited."""
    existing = db.execute(text(f"SELECT {COLUMNS} FROM proposals WHERE idempotency_key = :key"), {"key": idempotency_key}).first()
    if existing is not None:
        if existing.case_id != case.case_id:
            raise AppError("IDEMPOTENCY_KEY_REUSED", "That key belongs to a different case", 409)
        return Proposal.model_validate(existing._mapping)
    row = db.execute(
        text(
            "INSERT INTO proposals (case_id, kind, status, idempotency_key, value, proposed_by, reviewed_by, committed_by, "
            f"reviewed_at, committed_at) VALUES (:case_id, 'STAGE_CHANGE', 'COMMITTED', :key, CAST(:value AS jsonb), :actor, :actor, "
            f":actor, now(), now()) RETURNING {COLUMNS}"
        ),
        {"case_id": case.case_id, "key": idempotency_key, "value": json.dumps(value), "actor": actor.label},
    ).one()
    proposal = Proposal.model_validate(row._mapping)
    _apply_stage(db, actor, case, proposal)
    return proposal


def _apply_stage(db: Session, actor: Actor, case: CaseRecord, proposal: Proposal) -> None:
    """The only place a case stage changes. The stage was approved, so commit writes it."""
    target = proposal.value["to_stage"]
    db.execute(text("UPDATE cases SET operational_stage = :stage WHERE case_id = :c"), {"stage": target, "c": case.case_id})
    audit.record(
        db, actor=actor, action=AuditAction.STAGE_CHANGED, case_id=case.case_id, target_type="case", target_id=case.case_id,
        before_state={"stage": case.operational_stage}, after_state={"stage": target}, evidence_ids=proposal.evidence_ids,
    )  # fmt: skip


def send_back(db: Session, actor: Actor, proposal_id: str, *, kind: str, body: str, suggested_date: date | None) -> Proposal:
    """The assigned legal reviewer answers without deciding: a different date or a question. The note is saved,
    the proposal goes back to operations and nothing is approved."""
    proposal = get(db, proposal_id, lock=True)
    case = _case(db, proposal.case_id)
    if actor.role != ActorRole.LEGAL or case.assigned_legal_reviewer != actor.label:
        raise _refuse(actor, AuditAction.PROPOSAL_SENT_BACK, case.case_id, proposal_id, "Only the assigned legal reviewer can send back")
    if proposal.status != ProposalStatus.PENDING_LEGAL_REVIEW:
        raise AppError("ALREADY_DECIDED", f"{proposal_id} is already {proposal.status.value}", 409)
    note = body.strip()
    if not note:
        raise AppError("NOTE_REQUIRED", "Write the note or the question", 400)
    if kind == "DIFFERENT_DATE" and suggested_date is None:
        raise AppError("DATE_REQUIRED", "Give the date you would use", 400)
    if kind not in ("DIFFERENT_DATE", "QUESTION"):
        raise AppError("NOTE_KIND_UNKNOWN", "kind must be DIFFERENT_DATE or QUESTION", 400)
    db.execute(
        text("INSERT INTO case_notes (case_id, proposal_id, kind, body, suggested_date, author) VALUES (:c, :p, :k, :b, :d, :a)"),
        {"c": case.case_id, "p": proposal_id, "k": kind, "b": note, "d": suggested_date, "a": actor.label},
    )
    row = db.execute(
        text(f"UPDATE proposals SET status = 'SENT_BACK', updated_at = now() WHERE proposal_id = :id RETURNING {COLUMNS}"),
        {"id": proposal_id},
    ).one()
    _set_workflow(db, case.case_id, "INFO_REQUESTED")
    db.execute(text("UPDATE case_workflows SET decided_at = now() WHERE case_id = :case_id"), {"case_id": case.case_id})
    audit.record(
        db, actor=actor, action=AuditAction.PROPOSAL_SENT_BACK, case_id=case.case_id, target_type="proposal", target_id=proposal_id,
        before_state={"status": proposal.status.value}, after_state={"status": ProposalStatus.SENT_BACK.value},
        evidence_ids=proposal.evidence_ids, details={"kind": kind},
    )  # fmt: skip
    return Proposal.model_validate(row._mapping)
