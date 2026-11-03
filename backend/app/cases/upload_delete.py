"""Deleting an uploaded file. The row and the stored bytes stay, because the audit trail and old reviews point at them.
Every view skips a deleted upload, and the ledger records who deleted it, when and why."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import stage
from app.cases.repository import CaseRecord
from app.core import audit
from app.core.contracts import AuditAction
from app.core.errors import AppError
from app.core.security import Actor
from app.ingest import comm

MIN_REASON = 3
# A proposal in any of these states still cites its evidence, so the file cannot go. A rejected one no longer does.
CITING = ("PENDING_LEGAL_REVIEW", "APPROVED", "COMMITTED")


def _clean_reason(reason: str | None) -> str:
    cleaned = " ".join((reason or "").split())
    if len(cleaned) < MIN_REASON:
        raise AppError("DELETE_REASON_REQUIRED", "Give a reason for deleting this file", 422)
    return cleaned[:500]


def _citing(db: Session, case_id: str, upload_id: str) -> list[str]:
    return list(db.scalars(
        text("SELECT proposal_id FROM proposals WHERE case_id = :c AND :u = ANY(evidence_ids) AND status = ANY(:s) ORDER BY id"),
        {"c": case_id, "u": upload_id, "s": list(CITING)},
    ))  # fmt: skip


def delete_upload(db: Session, actor: Actor, case: CaseRecord, upload_id: str, reason: str | None) -> list[str]:
    """Mark the upload deleted and audit it. Returns the ids of duplicates that were waiting on it and need a new read.
    The caller then rebuilds the facts, so the deleted file stops being a source."""
    why = _clean_reason(reason)
    row = db.execute(
        text("SELECT outcome, original_filename, sha256, category FROM uploads WHERE upload_id = :u AND case_id = :c "
             "AND deleted_at IS NULL FOR UPDATE"),
        {"u": upload_id, "c": case.case_id},
    ).first()  # fmt: skip
    if row is None:
        raise AppError("UPLOAD_NOT_FOUND", f"No upload {upload_id} in {case.case_id}", 404)
    if row.outcome == "READING":
        raise AppError("UPLOAD_BUSY", "This file is being read. Try again when the read has finished", 409)
    proposals = _citing(db, case.case_id, upload_id)
    if proposals:
        raise AppError("UPLOAD_IN_USE", f"{upload_id} is cited by {', '.join(proposals)}. Reject those first", 409)
    db.execute(
        text("UPDATE uploads SET deleted_at = now(), deleted_by = :a, delete_reason = :r, updated_at = now() WHERE upload_id = :u"),
        {"a": actor.label, "r": why, "u": upload_id},
    )
    comm.store_claims(db, case.case_id, upload_id, [])
    waiting = list(db.scalars(
        text("UPDATE uploads SET outcome = 'PENDING', reason_code = NULL, outcome_reason = NULL, duplicate_of_upload_id = NULL, "
             "updated_at = now() WHERE case_id = :c AND duplicate_of_upload_id = :u AND deleted_at IS NULL RETURNING upload_id"),
        {"c": case.case_id, "u": upload_id},
    ))  # fmt: skip
    audit.record(
        db, actor=actor, action=AuditAction.UPLOAD_DELETED, case_id=case.case_id, target_type="upload", target_id=upload_id,
        before_state={"outcome": row.outcome, "deleted": False}, after_state={"deleted": True}, evidence_ids=[upload_id],
        details={"filename": row.original_filename, "sha256": row.sha256, "category": row.category, "reason": why,
                 "duplicates_reopened": len(waiting)},
    )  # fmt: skip
    stage.sync_documents(db, actor, case.case_id)
    return waiting
