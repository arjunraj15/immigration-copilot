"""Create a case and receive uploaded files. Reading starts afterwards through ensure_case_read.

Rules: only OPS opens a case, a similar client name needs confirmation, every file passes the loader check,
an exact copy of a file already in the case is marked DUPLICATE and every accepted file is stored as PENDING.
"""

import hashlib
import mimetypes
import re
from difflib import SequenceMatcher
from typing import BinaryIO, NamedTuple

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import repository, stage
from app.cases.uploads import storage_roots
from app.core import audit
from app.core.contracts import ActorRole, AuditAction, UploadOutcome
from app.core.errors import AppError
from app.core.security import Actor
from app.ingest import loader
from app.ingest.loader import MAX_BYTES, RejectedFile

MAX_FILES = 200
SIMILAR_NAME = 0.85
_CASE_LOCK, _UPLOAD_LOCK = 70101, 70102


class Incoming(NamedTuple):
    filename: str
    stream: BinaryIO


class FileResult(BaseModel):
    upload_id: str | None = None
    original_filename: str
    status: str
    outcome: str | None = None
    reason: str | None = None


class Match(BaseModel):
    case_id: str
    name: str


def _normal(name: str) -> str:
    return " ".join(sorted(re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()))


def similar_cases(db: Session, actor: Actor, name: str) -> list[Match]:
    """Cases the actor may see whose client name is the same or very close. Only ids and names leave here."""
    want = _normal(name)
    records = repository.list_cases_for_actor(db, actor=actor.label, role=actor.role, term=None, as_of=repository.get_as_of(db))
    return [Match(case_id=r.case_id, name=r.display_name) for r in records
            if SequenceMatcher(None, want, _normal(r.display_name)).ratio() >= SIMILAR_NAME]  # fmt: skip


def _next_number(db: Session, lock: int, sql: str) -> int:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock})
    return db.scalar(text(sql))  # type: ignore[return-value]


def create_case(db: Session, actor: Actor, name: str, draft: bool = False) -> str:
    """Insert the case, its workflow and the client name. The assigned OPS is the actor. A draft starts as DRAFT."""
    number = _next_number(db, _CASE_LOCK, "SELECT COALESCE(max(substring(case_id from 6)::int), 0) + 1 FROM cases WHERE case_id ~ '^CASE-[0-9]+$'")
    case_id = f"CASE-{number:04d}"
    legal_users = [a for a in repository.list_actors(db) if a["role"] == "LEGAL"]
    legal = min(legal_users, key=lambda a: (a["case_count"], a["label"]))["label"] if legal_users else None
    if legal is None:
        raise AppError("NO_LEGAL_REVIEWER", "No legal reviewer is available", 503)
    db.execute(
        text(
            "INSERT INTO cases (case_id, web_record_id, client_ref, case_archetype, operational_stage, assigned_ops_user, "
            "assigned_legal_reviewer, opened_at, matter_visibility, priority) VALUES (:c, :w, :r, 'NEW_INTAKE', "
            "'INTAKE_REVIEW', :ops, :legal, :at, 'RESTRICTED', 'NORMAL')"
        ),
        {"c": case_id, "w": f"WEB-{number:05d}", "r": f"CLIENT-{number:04d}", "ops": actor.label, "legal": legal,
         "at": repository.get_as_of(db)},
    )  # fmt: skip
    status = "DRAFT" if draft else "NEW"
    db.execute(text("INSERT INTO case_workflows (case_id, status) VALUES (:c, :s)"), {"c": case_id, "s": status})
    db.execute(
        text(
            "INSERT INTO profile_fields (source_id, case_id, field_name, verified_value, verification_state, verified_at, "
            "verified_by) VALUES (:s, :c, :f, :n, :st, now(), :a)"
        ),
        {"s": f"PROFILE-{case_id}-{repository.NAME_FIELD}", "c": case_id, "f": repository.NAME_FIELD, "n": name, "a": actor.label,
         "st": "DRAFT_PLACEHOLDER" if draft else "HUMAN_VERIFIED"},
    )
    action = AuditAction.CASE_DRAFT_CREATED if draft else AuditAction.CASE_CREATED
    audit.record(db, actor=actor, action=action, case_id=case_id, target_type="case", target_id=case_id,
                 after_state={"status": status, "ops": actor.label, "legal": legal})  # fmt: skip
    return case_id


def refuse_unless_ops(actor: Actor) -> None:
    if actor.role != ActorRole.OPS:
        reason = f"{actor.label} cannot open a case, only operations users can"
        audit.record_denied(reason=reason, actor=actor, action=AuditAction.CASE_CREATED, target_type="case")
        raise AppError("OPS_ONLY", reason, 403)


def _store(db: Session, actor: Actor, case_id: str, item: Incoming, data: bytes, file_type: str) -> FileResult:
    sha = hashlib.sha256(data).hexdigest()
    number = _next_number(db, _UPLOAD_LOCK, "SELECT COALESCE(max(substring(upload_id from 4)::int), 0) + 1 FROM uploads WHERE upload_id ~ '^UP-[0-9]+$'")
    upload_id = f"UP-{number:06d}"
    path = f"{case_id}/{upload_id}.{file_type}"
    target = storage_roots()["APP_STORAGE"] / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    original = db.scalar(
        text("SELECT upload_id FROM uploads WHERE case_id = :c AND sha256 = :h AND deleted_at IS NULL ORDER BY uploaded_at, upload_id LIMIT 1"),
        {"c": case_id, "h": sha},
    )
    outcome = UploadOutcome.DUPLICATE if original else UploadOutcome.PENDING
    reason = f"Same file as {original}" if original else None
    db.execute(
        text(
            "INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, "
            "file_size_bytes, sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, "
            "outcome, outcome_reason, reason_code, duplicate_of_upload_id) VALUES (:u, :c, 'APP_STORAGE', :p, :n, :m, :s, "
            ":h, now(), :role, 'WEB_UPLOAD', 'UNSPECIFIED', 'unknown', :o, :r, :rc, :d)"
        ),
        {"u": upload_id, "c": case_id, "p": path, "n": item.filename, "m": mimetypes.guess_type(path)[0] or "application/octet-stream",
         "s": len(data), "h": sha, "role": actor.role.value, "o": outcome.value, "r": reason,
         "rc": "DUPLICATE" if original else None, "d": original},
    )  # fmt: skip
    audit.record(db, actor=actor, action=AuditAction.UPLOAD_RECEIVED, case_id=case_id, target_type="upload",
                 target_id=upload_id, details={"sha256": sha})  # fmt: skip
    if original:
        audit.record(db, actor=actor, action=AuditAction.DUPLICATE_DETECTED, case_id=case_id, target_type="upload",
                     target_id=upload_id, details={"reason_code": "DUPLICATE", "duplicate_of": original})  # fmt: skip
    stage.sync_documents(db, actor, case_id)
    return FileResult(upload_id=upload_id, original_filename=item.filename, status="accepted", outcome=outcome.value, reason=reason)


def receive_files(db: Session, actor: Actor, case_id: str, files: list[Incoming]) -> list[FileResult]:
    """Check and store each file. A refused file gets a reason and no upload row. The caller commits."""
    if len(files) > MAX_FILES:
        raise AppError("TOO_MANY_FILES", f"Send at most {MAX_FILES} files at a time", 400)
    results = []
    for item in files:
        data = item.stream.read(MAX_BYTES + 1)
        try:
            file_type = loader.check_file(data, item.filename)
        except RejectedFile as exc:
            results.append(FileResult(original_filename=item.filename, status="refused", reason=exc.message))
            continue
        results.append(_store(db, actor, case_id, item, data, file_type))
    return results
