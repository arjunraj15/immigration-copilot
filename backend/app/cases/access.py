"""Case access. A case is open only to the OPS user and the LEGAL reviewer assigned to it.
Every route that returns case data depends on case_for_actor, so scoping is checked in one place."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.cases import repository
from app.cases.repository import CaseRecord
from app.core import audit
from app.core.contracts import ActorRole, AuditAction
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.db.session import get_db


def assigned_to(record: CaseRecord, actor: Actor) -> bool:
    expected = record.assigned_ops_user if actor.role == ActorRole.OPS else record.assigned_legal_reviewer
    return actor.role != ActorRole.SYSTEM and expected == actor.label


def case_for_actor(
    case_id: str, db: Annotated[Session, Depends(get_db)], actor: Annotated[Actor, Depends(get_actor)]
) -> CaseRecord:
    record = repository.get_case(db, case_id, repository.get_as_of(db))
    if record is None or record.status == "DELETED":
        raise AppError("CASE_NOT_FOUND", f"No case {case_id}", 404)
    if not assigned_to(record, actor):
        reason = f"{actor.label} is not assigned to this case"
        audit.record_denied(
            reason=reason, actor=actor, action=AuditAction.CASE_ACCESS, case_id=case_id,
            target_type="case", target_id=case_id,
        )  # fmt: skip
        raise AppError("CASE_NOT_ASSIGNED", reason, 403)
    return record


AccessibleCase = Annotated[CaseRecord, Depends(case_for_actor)]
