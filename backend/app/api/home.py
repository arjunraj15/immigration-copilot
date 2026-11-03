"""Home page rows for the acting user. Rules live in app.cases.home."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.cases import home
from app.core.security import Actor, get_actor
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/home")
def get_home(
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(get_actor)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=home.PAGE_SIZE)] = home.PAGE_SIZE,
    kpi: Annotated[str | None, Query(pattern=f"^({'|'.join(home.KPI_KEYS)})$")] = None,
    stage: str | None = None,
    reason: str | None = None,
    term: str | None = None,
    just_me: bool = True,
    case_id: str | None = None,
) -> home.Home:
    filters = home.Filters(kpi=kpi, stage=stage, reason=reason, term=term, just_me=just_me, case_id=case_id)
    return home.build_home(db, actor, filters, page, page_size)
