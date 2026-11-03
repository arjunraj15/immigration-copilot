"""Open one uploaded file. Only the OPS user and LEGAL reviewer assigned to the case can read it."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import repository
from app.cases.access import assigned_to
from app.core import audit
from app.core.config import get_settings
from app.core.contracts import AuditAction
from app.core.errors import AppError
from app.core.security import Actor


@dataclass(frozen=True)
class UploadFile:
    path: Path
    filename: str
    mime_type: str


def storage_roots() -> dict[str, Path]:
    settings = get_settings()
    return {"STARTER_KIT": Path(settings.starter_kit_dir), "APP_STORAGE": Path(settings.storage_dir)}


def resolve_path(storage_root: str, storage_path: str) -> Path:
    """The file path under its root. Anything that leaves the root is refused, like an unknown root."""
    root = storage_roots().get(storage_root)
    if root is None:
        raise AppError("UPLOAD_STORAGE_UNKNOWN", "This upload has an unknown storage location", 404)
    base = root.resolve()
    path = (base / storage_path).resolve()
    if not path.is_relative_to(base):
        raise AppError("UPLOAD_PATH_REFUSED", "This upload points outside its storage location", 404)
    if not path.is_file():
        raise AppError("UPLOAD_FILE_MISSING", "The file for this upload is not on disk", 404)
    return path


def require_upload_access(db: Session, actor: Actor, case_id: str, upload_id: str) -> None:
    """The actor must be assigned to the upload's case. A refusal is audited as denied and raises 403."""
    case = repository.get_case(db, case_id, repository.get_as_of(db))
    if case is None or not assigned_to(case, actor):
        reason = f"{actor.label} is not assigned to this case"
        audit.record_denied(reason=reason, actor=actor, action=AuditAction.CASE_ACCESS, case_id=case_id,
                            target_type="upload", target_id=upload_id)  # fmt: skip
        raise AppError("CASE_NOT_ASSIGNED", reason, 403)


def open_upload(db: Session, actor: Actor, upload_id: str) -> UploadFile:
    row = db.execute(
        text(
            "SELECT case_id, storage_root, storage_path, original_filename, mime_type FROM uploads "
            "WHERE upload_id = :upload_id AND deleted_at IS NULL"
        ),
        {"upload_id": upload_id},
    ).mappings().first()  # fmt: skip
    if row is None:
        raise AppError("UPLOAD_NOT_FOUND", f"No upload {upload_id}", 404)
    require_upload_access(db, actor, row["case_id"], upload_id)
    path = resolve_path(row["storage_root"], row["storage_path"])
    return UploadFile(path=path, filename=row["original_filename"], mime_type=row["mime_type"])
