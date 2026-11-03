"""Uploaded files. The route stays thin, the access rule and path checks live in app.cases.uploads."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.cases import uploads
from app.core.security import Actor, get_actor
from app.db.session import get_db

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.get("/{upload_id}/file")
def get_upload_file(
    upload_id: str, db: Annotated[Session, Depends(get_db)], actor: Annotated[Actor, Depends(get_actor)]
) -> Response:
    """The stored bytes with the stored type, shown inline in the viewer."""
    found = uploads.open_upload(db, actor, upload_id)
    name = found.filename.replace('"', "")
    headers = {"Content-Disposition": f'inline; filename="{name}"'}
    return Response(content=found.path.read_bytes(), media_type=found.mime_type, headers=headers)
