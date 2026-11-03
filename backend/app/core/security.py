"""Demo actor handling. The X-Actor label is a demo control, not authentication, but the server
still decides the role from it and rejects anything it does not recognise."""

import re
from typing import Annotated

from fastapi import Header
from pydantic import BaseModel

from app.core.contracts import ActorRole
from app.core.errors import AppError

ACTOR_PATTERN = re.compile(r"^(OPS|LEGAL)-\d{2}$")


class Actor(BaseModel):
    label: str
    role: ActorRole


def parse_actor(label: str | None) -> Actor:
    if not label:
        raise AppError("ACTOR_REQUIRED", "Send the X-Actor header, for example OPS-01", 401)
    match = ACTOR_PATTERN.match(label.strip())
    if not match:
        raise AppError("ACTOR_INVALID", f"Unknown actor label {label!r}. Use OPS-xx or LEGAL-xx", 401)
    return Actor(label=label.strip(), role=ActorRole(match.group(1)))


def get_actor(x_actor: Annotated[str | None, Header()] = None) -> Actor:
    """FastAPI dependency for every route that reads or changes case data."""
    return parse_actor(x_actor)
