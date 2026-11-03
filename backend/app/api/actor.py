"""Who is acting. The UI uses /actors for the picker and /me to confirm the role the server derives."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cases import repository
from app.core.contracts import ActorRole
from app.core.security import Actor, get_actor
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["actor"])


class ActorOut(BaseModel):
    label: str
    role: ActorRole
    case_count: int


@router.get("/me")
def me(actor: Annotated[Actor, Depends(get_actor)], db: Annotated[Session, Depends(get_db)]) -> ActorOut:
    count = repository.count_cases_for_actor(db, actor=actor.label, role=actor.role)
    return ActorOut(label=actor.label, role=actor.role, case_count=count)


@router.get("/actors")
def actors(db: Annotated[Session, Depends(get_db)]) -> list[ActorOut]:
    """Every user that has cases assigned. Read from the data, so a new user in the kit appears here."""
    return [ActorOut.model_validate(row) for row in repository.list_actors(db)]
