"""Read uploads with the AI, run a whole case in the background and show the checklist. Rules live in app.ingest."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases.access import AccessibleCase
from app.cases.uploads import require_upload_access
from app.core import audit
from app.core.contracts import AuditAction
from app.core.errors import AppError
from app.core.security import Actor, get_actor
from app.db.session import get_db, transaction
from app.ingest import jobs, service

router = APIRouter(prefix="/api", tags=["ingest"])

Db = Annotated[Session, Depends(get_db)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
ANALYSE_OUTCOMES = ("PENDING", "NEEDS_HUMAN_REVIEW")


class JobOut(BaseModel):
    job_id: str
    case_id: str
    status: str
    total: int
    done: int
    events: list[dict]
    reason: str | None = None


def _job_out(row: dict) -> JobOut:
    return JobOut(job_id=row["id"], case_id=row["case_id"], status=row["status"], total=row["total"], done=row["done"],
                  events=row["events"], reason=row["reason"])  # fmt: skip


@router.post("/uploads/{upload_id}/read")
def read_upload(upload_id: str, db: Db, actor: CurrentActor, force: bool = False) -> service.UploadResult:
    """Read one upload. A settled upload is returned as it is. force=true sends it to the AI again."""
    case_id = db.scalar(text("SELECT case_id FROM uploads WHERE upload_id = :u"), {"u": upload_id})
    if case_id is None:
        raise AppError("UPLOAD_NOT_FOUND", f"No upload {upload_id}", 404)
    require_upload_access(db, actor, case_id, upload_id)
    return service.read_upload(db, actor, upload_id, force=force)


@router.post("/cases/{case_id}/analyse")
def analyse_case(case: AccessibleCase, db: Db, actor: CurrentActor, tasks: BackgroundTasks) -> JobOut:
    """Read every pending or Human review upload of the case in the background. Poll GET /api/jobs/{id}."""
    with transaction(db):
        job_id = service.start_case_job(db, tasks, actor, case.case_id, ANALYSE_OUTCOMES)
        job = jobs.get(db, job_id) if job_id else None
        job = job or {"id": "none", "case_id": case.case_id, "status": "SUCCEEDED", "total": 0, "done": 0, "events": [], "reason": None}
        audit.record(db, actor=actor, action=AuditAction.ANALYSIS_RUN, case_id=case.case_id, target_type="case",
                     target_id=case.case_id, details={"job_id": job["id"], "uploads": job["total"]})  # fmt: skip
    return _job_out(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Db, actor: CurrentActor) -> JobOut:
    job = jobs.get(db, job_id)
    if job is None:
        raise AppError("JOB_NOT_FOUND", f"No job {job_id}", 404)
    require_upload_access(db, actor, job["case_id"], job_id)
    return _job_out(job)


@router.get("/cases/{case_id}/checklist")
def get_checklist(case: AccessibleCase, db: Db) -> list[service.ChecklistItem]:
    return service.checklist(db, case.case_id)
