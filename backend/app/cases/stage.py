"""Automatic case stage. Code moves the stage when documents arrive, when OPS submits to legal and when legal rejects.

A stage the attorney approved through a stage change proposal is only replaced by a document event while the case is still
in intake review, document collection or evidence review. Every move is written to the audit trail."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import audit
from app.core.contracts import AuditAction, ProposalKind, UploadOutcome
from app.core.security import Actor

DOCUMENT_STAGES = ("INTAKE_REVIEW", "DOCUMENT_COLLECTION", "EVIDENCE_REVIEW")
SUBMIT_KINDS = (ProposalKind.FORM_EXPORT, ProposalKind.PACKET_APPROVE)
_PROBLEMS = (UploadOutcome.QUARANTINED, UploadOutcome.NEEDS_HUMAN_REVIEW, UploadOutcome.PENDING, UploadOutcome.READING)
WAITING = "WAITING_FOR_PORTAL_EVENT"


def _current(db: Session, case_id: str) -> str | None:
    return db.scalar(text("SELECT operational_stage FROM cases WHERE case_id = :c"), {"c": case_id})


def _move(db: Session, actor: Actor, case_id: str, target: str, reason: str) -> None:
    current = _current(db, case_id)
    if current is None or current == target:
        return
    db.execute(text("UPDATE cases SET operational_stage = :s WHERE case_id = :c"), {"s": target, "c": case_id})
    audit.record(
        db, actor=actor, action=AuditAction.STAGE_CHANGED, case_id=case_id, target_type="case", target_id=case_id,
        before_state={"stage": current}, after_state={"stage": target}, details={"automatic": True, "reason": reason},
    )  # fmt: skip


def _wanted_for_documents(db: Session, case_id: str) -> tuple[str, str] | None:
    """A file being read or a file that needs a person means evidence review. Otherwise a required document that is missing or not
    usable, such as one that needs a translation, means document collection because the client has to send it."""
    from app.ingest import service as ingest

    outcomes = set(db.scalars(text("SELECT outcome FROM uploads WHERE case_id = :c AND deleted_at IS NULL"), {"c": case_id}))
    if not outcomes:
        return _collection(db, case_id)  # no file at all, so every required document is still owed
    if outcomes & {p.value for p in _PROBLEMS}:
        return "EVIDENCE_REVIEW", "A document is being read or needs attention"
    return _collection(db, case_id)


def _collection(db: Session, case_id: str) -> tuple[str, str] | None:
    from app.ingest import service as ingest

    if any(item.status in ("MISSING", "NOT_USABLE") for item in ingest.checklist(db, case_id)):
        return "DOCUMENT_COLLECTION", "A required document is missing or not usable"
    return None


def sync_documents(db: Session, actor: Actor, case_id: str) -> None:
    """Call after a file is received or read."""
    current = _current(db, case_id)
    if current == WAITING:
        # A case cannot wait on the portal while a required document is still owed by the client.
        wanted = _collection(db, case_id)
    elif current in DOCUMENT_STAGES:
        wanted = _wanted_for_documents(db, case_id)
    else:
        return
    if wanted is not None:
        _move(db, actor, case_id, *wanted)


def submitted(db: Session, actor: Actor, case_id: str) -> None:
    """OPS sent the form or the packet to legal. A case that still owes a document stays in document collection and a case
    waiting on the portal stays there."""
    if gap := _collection(db, case_id):
        _move(db, actor, case_id, *gap)
    elif _current(db, case_id) != WAITING:
        _move(db, actor, case_id, "READY_FOR_LEGAL_REVIEW", "Submitted to legal review")


def rejected(db: Session, actor: Actor, case_id: str) -> None:
    _move(db, actor, case_id, "ON_HOLD", "Legal rejected the submission")
