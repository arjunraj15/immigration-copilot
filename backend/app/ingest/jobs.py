"""Background read jobs stored in the jobs table, so a restart never loses them.

While a job runs the case workflow shows ANALYSING. The status before is kept on the job and put back when
the job ends. A case that moved on to review or a decision in the meantime is never overwritten.
"""

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

STUCK_JOB_MINUTES = 30
STUCK_REASON = "The job stopped before it finished, probably because the server restarted"
# Workflow statuses a read must never replace.
PROTECTED = ("DRAFT", "WITH_ATTORNEY", "APPROVED", "REJECTED", "APPLIED")

_RESTORE = (
    "UPDATE case_workflows w SET status = j.workflow_before, updated_at = now() FROM jobs j "
    "WHERE j.id = :j AND j.workflow_before IS NOT NULL AND w.case_id = j.case_id AND w.status = 'ANALYSING'"
)


def _begin_analysing(db: Session, case_id: str) -> str | None:
    """Set ANALYSING and return the status it replaced. None when the case must keep its status."""
    return db.scalar(
        text(
            "UPDATE case_workflows w SET status = 'ANALYSING', updated_at = now() "
            "FROM (SELECT status FROM case_workflows WHERE case_id = :c FOR UPDATE) o "
            "WHERE w.case_id = :c AND o.status <> 'ANALYSING' AND NOT (o.status = ANY(:p)) RETURNING o.status"
        ),
        {"c": case_id, "p": list(PROTECTED)},
    )


def create(db: Session, kind: str, case_id: str, actor: str, total: int) -> str:
    job_id = uuid.uuid4().hex[:12]
    db.execute(
        text(
            "INSERT INTO jobs (id, kind, case_id, actor, total, workflow_before) "
            "VALUES (:i, :k, :c, :a, :t, :b)"
        ),
        {"i": job_id, "k": kind, "c": case_id, "a": actor, "t": total, "b": _begin_analysing(db, case_id)},
    )
    db.commit()
    return job_id


def add_event(db: Session, job_id: str, event: dict[str, Any]) -> None:
    db.execute(
        text("UPDATE jobs SET done = done + 1, events = events || CAST(:e AS jsonb), updated_at = now() WHERE id = :j"),
        {"e": json.dumps([event]), "j": job_id},
    )
    db.commit()


def finish(db: Session, job_id: str, status: str, reason: str | None = None) -> None:
    db.execute(
        text(
            "UPDATE jobs SET status = :s, reason = :r, finished_at = now(), updated_at = now() "
            "WHERE id = :j AND status = 'RUNNING'"
        ),
        {"s": status, "r": reason, "j": job_id},
    )
    db.execute(text(_RESTORE), {"j": job_id})
    db.commit()


def get(db: Session, job_id: str) -> dict[str, Any] | None:
    """The job as stored. A RUNNING job with no progress for too long is marked FAILED first."""
    stuck = db.scalar(
        text("SELECT status = 'RUNNING' AND updated_at < now() - make_interval(mins => :m) FROM jobs WHERE id = :j"),
        {"j": job_id, "m": STUCK_JOB_MINUTES},
    )
    if stuck:
        finish(db, job_id, "FAILED", STUCK_REASON)
    row = db.execute(
        text("SELECT id, case_id, status, total, done, events, reason FROM jobs WHERE id = :j"), {"j": job_id}
    ).mappings().first()  # fmt: skip
    return dict(row) if row else None
