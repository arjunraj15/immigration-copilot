"""Draft cases for the new case wizard. Files are read first, a person picks the client name, then submits.

A draft is hidden from every list until it is submitted. Claims from call and message documents are never facts.
"""

import shutil
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import repository
from app.cases.access import assigned_to
from app.cases.uploads import storage_roots
from app.core import audit
from app.core.contracts import ActorRole, AuditAction
from app.core.errors import AppError
from app.core.security import Actor
from app.ingest import intake
from app.ingest.intake import Match

PLACEHOLDER_NAME = "New client (draft)"


class Candidate(BaseModel):
    value: str
    source_id: str
    source_kind: str
    quote: str
    from_image: bool = False


class Candidates(BaseModel):
    candidates: list[Candidate]
    conflict: bool
    status: str


def require_draft_owner(db: Session, actor: Actor, case_id: str) -> str:
    """The workflow status when the actor is the OPS user of this case, else a 403 with a denied audit line."""
    case = repository.get_case(db, case_id, repository.get_as_of(db))
    if case is None:
        raise AppError("CASE_NOT_FOUND", f"No case {case_id}", 404)
    if actor.role != ActorRole.OPS or not assigned_to(case, actor):
        reason = f"{actor.label} cannot change this case, only its operations user can"
        audit.record_denied(reason=reason, actor=actor, action=AuditAction.CASE_ACCESS, case_id=case_id, target_type="case", target_id=case_id)
        raise AppError("OPS_ONLY", reason, 403)
    return case.status


# ---------------------------------------------------------------- name candidates


def _doc_candidates(db: Session, case_id: str) -> list[Candidate]:
    rows = db.execute(
        text(
            "SELECT r.upload_id, r.extracted FROM (SELECT DISTINCT ON (upload_id) * FROM document_reads "
            "ORDER BY upload_id, read_at DESC, id DESC) r JOIN uploads u ON u.upload_id = r.upload_id "
            "WHERE u.case_id = :c AND u.deleted_at IS NULL AND u.outcome NOT IN ('QUARANTINED', 'DUPLICATE', 'INVALID') AND r.extracted IS NOT NULL "
            "ORDER BY u.uploaded_at, u.upload_id"
        ),
        {"c": case_id},
    ).all()
    found = []
    for row in rows:
        for key, item in (row.extracted.get("fields") or {}).items():
            if key.endswith(".Applicant") and item.get("value"):
                found.append(Candidate(value=item["value"], source_id=row.upload_id, source_kind="DOCUMENT",
                                       quote=item.get("quote") or "", from_image=bool(item.get("from_image"))))  # fmt: skip
    return found


def _claim_kind(source_id: str) -> str:
    return "INTAKE" if source_id.startswith("Z-") else "MESSAGE" if source_id.startswith("MSG-") else "COMMUNICATION"


def name_candidates(db: Session, case_id: str) -> Candidates:
    claims = db.execute(
        text("SELECT source_id, value, quote FROM claims WHERE case_id = :c AND field_name = 'full_name' ORDER BY id"), {"c": case_id}
    ).all()
    found = _doc_candidates(db, case_id) + [
        Candidate(value=c.value, source_id=c.source_id, source_kind=_claim_kind(c.source_id), quote=c.quote)
        for c in claims
    ]
    running = db.scalar(text("SELECT count(*) FROM jobs WHERE case_id = :c AND status = 'RUNNING' AND updated_at > now() - interval '30 minutes'"), {"c": case_id})
    return Candidates(candidates=found, conflict=len({intake._normal(c.value) for c in found}) > 1, status="PROCESSING" if running else "DONE")


# ---------------------------------------------------------------- submit and discard


class SubmitIn(BaseModel):
    client_name: str
    name_source: Literal["EXTRACTED", "MANUAL"]
    source_id: str | None = None
    confirm_new: bool = False


class SubmitOut(BaseModel):
    case_id: str
    name: str


def submit(db: Session, actor: Actor, case_id: str, body: SubmitIn) -> SubmitOut | list[Match]:
    """Name the client and open the case. A submitted case is returned again. Similar names come back as matches."""
    status = require_draft_owner(db, actor, case_id)
    if status != "DRAFT":
        return SubmitOut(case_id=case_id, name=repository.get_case(db, case_id, repository.get_as_of(db)).display_name)  # type: ignore[union-attr]
    name = " ".join(body.client_name.split())
    if not name:
        raise AppError("CLIENT_NAME_REQUIRED", "Enter the client name", 422)
    source = body.name_source
    if source == "EXTRACTED" and not any(intake._normal(c.value) == intake._normal(name) and c.source_id == body.source_id
                                         for c in name_candidates(db, case_id).candidates):  # fmt: skip
        raise AppError("NAME_NOT_EXTRACTED", "That name was not found in the documents or notes of this case", 422)
    matches = intake.similar_cases(db, actor, name)
    if matches and not body.confirm_new:
        return matches
    note = f"EXTRACTED from {body.source_id}" if source == "EXTRACTED" else f"MANUAL entered by {actor.label}"
    db.execute(
        text("UPDATE profile_fields SET verified_value = :n, verification_state = 'HUMAN_VERIFIED', verified_at = now(), "
             "verified_by = :a, note = :note, updated_at = now() WHERE case_id = :c AND field_name = :f"),
        {"n": name, "a": actor.label, "note": note, "c": case_id, "f": repository.NAME_FIELD},
    )  # fmt: skip
    db.execute(text("UPDATE case_workflows SET status = 'NEW', updated_at = now() WHERE case_id = :c AND status = 'DRAFT'"), {"c": case_id})
    audit.record(db, actor=actor, action=AuditAction.CASE_CREATED, case_id=case_id, target_type="case", target_id=case_id,
                 before_state={"status": "DRAFT"}, after_state={"status": "NEW"},
                 details={"name_source": source, "source_id": body.source_id})  # fmt: skip
    db.commit()
    from app.facts import engine

    engine.recompute(db, case_id)
    return SubmitOut(case_id=case_id, name=name)


_OWNED = ("fact_states", "facts", "claims", "intake_notes", "messages", "jobs", "review_requests", "proposals", "message_drafts",
          "case_notes", "profile_fields", "case_workflows")  # fmt: skip


def discard(db: Session, actor: Actor, case_id: str) -> None:
    """Delete everything a draft owns. The audit rows stay."""
    if require_draft_owner(db, actor, case_id) != "DRAFT":
        raise AppError("CASE_NOT_DRAFT", "Only a draft case can be discarded", 409)
    ids = {"c": case_id}
    db.execute(text("DELETE FROM document_reads WHERE upload_id IN (SELECT upload_id FROM uploads WHERE case_id = :c)"), ids)
    db.execute(text("DELETE FROM document_pages WHERE upload_id IN (SELECT upload_id FROM uploads WHERE case_id = :c)"), ids)
    db.execute(text("DELETE FROM uploads WHERE case_id = :c"), ids)
    for table in _OWNED:
        db.execute(text(f"DELETE FROM {table} WHERE case_id = :c"), ids)
    db.execute(text("DELETE FROM cases WHERE case_id = :c"), ids)
    audit.record(db, actor=actor, action=AuditAction.CASE_DRAFT_DISCARDED, case_id=case_id, target_type="case", target_id=case_id)
    db.commit()
    shutil.rmtree(storage_roots()["APP_STORAGE"] / case_id, ignore_errors=True)
