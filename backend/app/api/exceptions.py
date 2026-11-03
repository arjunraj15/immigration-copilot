"""The Exceptions list for the acting user's own cases. Rules live in app.cases.exceptions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.cases import exceptions
from app.cases.access import AccessibleCase
from app.core.security import Actor, get_actor
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["exceptions"])


@router.get("/exceptions")
def get_exceptions(
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(get_actor)],
    kind: Annotated[str | None, Query(alias="type")] = None,
    q: str | None = None,
) -> exceptions.ExceptionList:
    return exceptions.build_list(db, actor, kind=kind, q=q)


@router.get("/cases/{case_id}/exceptions")
def get_case_exceptions(
    case: AccessibleCase,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(get_actor)],
) -> exceptions.ExceptionList:
    """The exceptions of one case: its missing and defective documents, deadlines and proposals, and its field conflicts."""
    items = [i for i in exceptions.build_items(db, actor) if i.case_id == case.case_id]
    counts: dict[str, int] = {}
    for item in items:
        counts[item.type] = counts.get(item.type, 0) + 1
    return exceptions.ExceptionList(items=items, counts=counts, total=len(items))
