"""Open a case from the upload wizard and add documents to a case. Rules live in app.ingest.intake."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.cases import communications, documents, importer, upload_delete
from app.cases.access import AccessibleCase
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.facts import engine
from app.db.session import get_db, transaction
from app.ingest import draft, intake
from app.ingest import service as ingest

router = APIRouter(prefix="/api/cases", tags=["intake"])

Db = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
Files = Annotated[list[UploadFile], File()]


class IntakeOut(BaseModel):
    case_id: str
    results: list[intake.FileResult]
    job_id: str | None = None


def _incoming(files: list[UploadFile]) -> list[intake.Incoming]:
    return [intake.Incoming(f.filename or "file", f.file) for f in files]


@router.post("")
def create_case(db: Db, actor: CurrentActor, tasks: BackgroundTasks, client_name: Annotated[str, Form()],
                files: Annotated[list[UploadFile] | None, File()] = None, confirm_new: Annotated[bool, Form()] = False):  # fmt: skip
    """Open a new case. A similar client name answers 409 with the matches until confirm_new is true."""
    intake.refuse_unless_ops(actor)
    name = " ".join(client_name.split())
    if not name:
        raise AppError("CLIENT_NAME_REQUIRED", "Enter the client name", 422)
    matches = intake.similar_cases(db, actor, name)
    if matches and not confirm_new:
        return _matches_409(matches)
    with transaction(db):
        case_id = intake.create_case(db, actor, name)
        results = intake.receive_files(db, actor, case_id, _incoming(files or []))
    ingest.ensure_case_read(db, tasks, actor, case_id)
    return IntakeOut(case_id=case_id, results=results)


@router.post("/{case_id}/documents")
def add_documents(case: AccessibleCase, db: Db, actor: CurrentActor, tasks: BackgroundTasks, files: Files) -> IntakeOut:
    """Check and store the files, then start the automatic read."""
    with transaction(db):
        results = intake.receive_files(db, actor, case.case_id, _incoming(files))
    ingest.ensure_case_read(db, tasks, actor, case.case_id)
    return IntakeOut(case_id=case.case_id, results=results)


def _matches_409(matches: list[intake.Match]) -> JSONResponse:
    body = {"error": {"code": "POSSIBLE_DUPLICATE_CLIENT", "message": "A case for a similar client name exists",
                      "matches": [m.model_dump() for m in matches]}}  # fmt: skip
    return JSONResponse(status_code=409, content=body)


@router.post("/draft")
def create_draft(db: Db, actor: CurrentActor, tasks: BackgroundTasks, files: Files) -> IntakeOut:
    """Start a draft case from files. A pasted call or message arrives as a text file. The AI reads them in one job."""
    intake.refuse_unless_ops(actor)
    with transaction(db):
        case_id = intake.create_case(db, actor, draft.PLACEHOLDER_NAME, draft=True)
        results = intake.receive_files(db, actor, case_id, _incoming(files))
    job_id = ingest.start_draft_job(db, tasks, actor, case_id)
    return IntakeOut(case_id=case_id, results=results, job_id=job_id)


@router.get("/{case_id}/documents")
def list_case_documents(
    case: AccessibleCase, db: Db, actor: CurrentActor, page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=documents.MAX_PAGE_SIZE)] = 25, outcome: str | None = None,
) -> documents.DocumentPage:  # fmt: skip
    """One page of the uploads of one case, newest first, a draft included. The case lists never show a draft.
    outcome takes one or more outcomes separated by commas. counts always covers the whole case."""
    return documents.list_documents(db, actor=actor.label, role=actor.role, case=None, client=None, outcome=outcome,
                                    page=page, page_size=page_size, exact_case=case.case_id)  # fmt: skip


@router.delete("/{case_id}/documents/{upload_id}")
def delete_document(case: AccessibleCase, db: Db, actor: CurrentActor, tasks: BackgroundTasks, upload_id: str,
                    reason: Annotated[str, Query(max_length=500)] = "") -> dict[str, str]:  # fmt: skip
    """Delete an uploaded file, with a reason. Only the OPS user or legal reviewer assigned to the case may. The file leaves
    every view and the facts are rebuilt without it, and the ledger keeps who deleted it and why."""
    with transaction(db):
        reopened = upload_delete.delete_upload(db, actor, case, upload_id, reason)
    engine.recompute(db, case.case_id)
    if reopened:
        ingest.ensure_case_read(db, tasks, actor, case.case_id)
    return {"upload_id": upload_id, "case_id": case.case_id, "status": "DELETED"}


@router.post("/{case_id}/import")
def import_data(case: AccessibleCase, db: Db, actor: CurrentActor, body: importer.ImportIn) -> importer.ImportResult:
    """New mock data for this case: an event, a Zoom note or a client message. Stored once however often it is sent, audited,
    and the field states, conflicts and deadline are rebuilt from it. Nothing becomes a fact and no decision is overwritten."""
    return importer.import_record(db, actor, case, body)


@router.get("/{case_id}/communications")
def list_communications(case: AccessibleCase, db: Db) -> list[communications.Communication]:
    """Zoom notes and messages of one case, oldest first. Every item is a claim."""
    return communications.list_communications(db, case.case_id)


@router.get("/{case_id}/name-candidates")
def get_name_candidates(case: AccessibleCase, db: Db) -> draft.Candidates:
    return draft.name_candidates(db, case.case_id)


@router.post("/{case_id}/submit")
def submit_case(case: AccessibleCase, db: Db, actor: CurrentActor, body: draft.SubmitIn):
    """Name the client and open a draft case. Similar client names answer 409 until confirm_new is true."""
    result = draft.submit(db, actor, case.case_id, body)
    return _matches_409(result) if isinstance(result, list) else result


@router.delete("/{case_id}/draft")
def discard_draft(case: AccessibleCase, db: Db, actor: CurrentActor) -> dict[str, str]:
    draft.discard(db, actor, case.case_id)
    return {"case_id": case.case_id, "status": "DISCARDED"}
