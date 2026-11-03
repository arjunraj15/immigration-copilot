"""Audit ledger routes. History tab, system chain and chain verification."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cases.access import AccessibleCase
from app.core import audit
from app.core.audit import AuditEntry, VerifyResult
from app.core.audit_display import AuditDisplay, describe
from app.core.contracts import AuditAction
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.db.session import get_db, transaction

router = APIRouter(prefix="/api", tags=["audit"])

Db = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]


class AuditLine(BaseModel):
    entry: AuditEntry
    display: AuditDisplay


class AuditPage(BaseModel):
    stream_id: str
    total: int
    limit: int
    offset: int
    entries: list[AuditLine]


class VerifyAll(BaseModel):
    valid: bool
    chains: list[VerifyResult]


def _parse_actions(raw: str | None) -> list[AuditAction]:
    if not raw:
        return []
    try:
        return [AuditAction(name.strip()) for name in raw.split(",") if name.strip()]
    except ValueError as error:
        raise AppError("VALIDATION_ERROR", f"Unknown audit action in filter: {error}", 422) from error


def _page(db: Session, stream_id: str, action: str | None, limit: int, offset: int) -> AuditPage:
    total, entries = audit.list_entries(db, stream_id, actions=_parse_actions(action), limit=limit, offset=offset)
    lines = [AuditLine(entry=entry, display=describe(entry)) for entry in entries]
    return AuditPage(stream_id=stream_id, total=total, limit=limit, offset=offset, entries=lines)


@router.get("/cases/{case_id}/audit")
def case_audit(
    case: AccessibleCase,
    db: Db,
    action: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    return _page(db, case.case_id, action, limit, offset)


@router.get("/cases/{case_id}/audit/verify")
def verify_case(case: AccessibleCase, db: Db, actor: CurrentActor) -> VerifyResult:
    case_id = case.case_id
    with transaction(db):
        result = audit.verify_stream(db, case_id)
        audit.record(
            db, actor=actor, action=AuditAction.CHAIN_VERIFIED, case_id=case_id, target_type="audit_chain",
            target_id=case_id, details={"valid": result.valid, "entries_checked": result.entries_checked},
        )  # fmt: skip
    return result


@router.get("/audit")
def system_audit(
    db: Db,
    actor: CurrentActor,
    action: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    audit.require_legal(actor, action=AuditAction.CHAIN_VERIFIED, target_type="audit_chain", target_id="SYSTEM")
    return _page(db, audit.SYSTEM_STREAM, action, limit, offset)


@router.get("/audit/verify")
def verify_all(db: Db, actor: CurrentActor) -> VerifyAll:
    audit.require_legal(actor, action=AuditAction.CHAIN_VERIFIED, target_type="audit_chain", target_id="ALL")
    with transaction(db):
        chains = [audit.verify_stream(db, stream_id) for stream_id in audit.list_streams(db)]
        result = VerifyAll(valid=all(chain.valid for chain in chains), chains=chains)
        audit.record(
            db, actor=actor, action=AuditAction.CHAIN_VERIFIED, target_type="audit_chain", target_id="ALL",
            details={"valid": result.valid, "chains_checked": len(chains)},
        )  # fmt: skip
    return result
