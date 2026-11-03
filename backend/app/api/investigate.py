"""Why is this case blocked. A read only explanation with cited tool results. Nothing is sent or changed."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.cases.access import AccessibleCase
from app.core.security import Actor, get_actor
from app.db.session import get_db, transaction
from app.investigate import agent
from app.investigate.answer import InvestigationOut

router = APIRouter(prefix="/api/cases", tags=["investigate"])


class InvestigateIn(BaseModel):
    question: str = Field(default=agent.DEFAULT_QUESTION, max_length=agent.MAX_QUESTION_CHARS)


@router.post("/{case_id}/investigate")
def investigate(
    case: AccessibleCase,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[Actor, Depends(get_actor)],
    body: InvestigateIn | None = None,
) -> InvestigationOut:
    with transaction(db):
        out = agent.investigate(db, actor, case, body.question if body else None)
    return out
