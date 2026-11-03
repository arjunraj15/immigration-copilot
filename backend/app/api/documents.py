"""The documents list: uploads on the acting user's cases with paging and filters. Rules live in app.cases.documents."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.cases import documents
from app.core.security import Actor, get_actor
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents")
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(get_actor)],
    case: str | None = None,
    client: str | None = None,
    outcome: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=documents.MAX_PAGE_SIZE)] = 25,
) -> documents.DocumentPage:
    return documents.list_documents(
        db, actor=actor.label, role=actor.role, case=case, client=client, outcome=outcome, page=page, page_size=page_size
    )
