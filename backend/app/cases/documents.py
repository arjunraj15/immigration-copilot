"""Uploaded documents across the acting user's own cases, one page at a time. Never reads another user's case."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases.repository import NAME_FIELD, _like
from app.core.contracts import ActorRole

MAX_PAGE_SIZE = 100

# Same display name rule as the case list: the latest human decision, else the verified profile value.
_CLIENT_NAME = f"""COALESCE(
    (SELECT d.corrected_value FROM review_decisions d
      WHERE d.case_id = c.case_id AND d.field_name = '{NAME_FIELD}' AND d.corrected_value IS NOT NULL
      ORDER BY d.recorded_at DESC, d.id DESC LIMIT 1),
    (SELECT p.verified_value FROM profile_fields p WHERE p.case_id = c.case_id AND p.field_name = '{NAME_FIELD}'),
    c.case_id)"""


# The document type name an admin sets on the read prompt for that category.
CATEGORY_TITLE = "(SELECT p.title FROM prompts p WHERE p.step = 'read' AND p.category = u.category AND p.deleted_at IS NULL LIMIT 1)"


def category_label(category: str | None, title: str | None) -> str | None:
    """The prompt title, else the raw category as plain words. None stays None, UNKNOWN falls back to the raw words."""
    if category is None:
        return None
    return title or category.replace("_", " ").capitalize()


def owner_column(role: ActorRole) -> str:
    return "c.assigned_ops_user" if role == ActorRole.OPS else "c.assigned_legal_reviewer"


class PageSource(BaseModel):
    page: int
    text_source: str
    reason: str | None


class DocumentRow(BaseModel):
    upload_id: str
    case_id: str
    client_name: str
    original_filename: str
    category: str | None
    category_label: str | None
    outcome: str
    outcome_reason: str | None
    file_size_bytes: int
    uploaded_at: datetime
    uploader_role: str
    reason_code: str | None = None
    duplicate_of: str | None = None
    injection: bool = False
    foreign_pages: list[int] = []
    pages: list[PageSource] = []


class DocumentPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[DocumentRow]
    # Files per outcome across the whole case, whatever the outcome filter and page. Only set for one case.
    counts: dict[str, int] = {}


def _pages(db: Session, upload_ids: list[str]) -> dict[str, list[PageSource]]:
    """Where each page of a file was read from. Never returned for a file of another client."""
    found = db.execute(
        text(
            "SELECT p.upload_id, p.page_number, p.text_source, p.reason FROM document_pages p JOIN uploads u "
            "ON u.upload_id = p.upload_id WHERE p.upload_id = ANY(:ids) AND u.deleted_at IS NULL AND u.outcome <> 'QUARANTINED' "
            "ORDER BY p.upload_id, p.page_number"
        ),
        {"ids": upload_ids},
    ).all()
    grouped: dict[str, list[PageSource]] = {}
    for p in found:
        grouped.setdefault(p.upload_id, []).append(PageSource(page=p.page_number, text_source=p.text_source, reason=p.reason))
    return grouped


def _row(r: Any, pages: list[PageSource]) -> DocumentRow:
    flags = r.flags or {}
    skip = {"category_title", "flags", "read_injection"}
    return DocumentRow(
        **{k: v for k, v in r._mapping.items() if k not in skip}, category_label=category_label(r.category, r.category_title),
        injection=bool(flags.get("injection") or r.read_injection), foreign_pages=flags.get("foreign_pages") or [], pages=pages,
    )  # fmt: skip


def _outcome_counts(db: Session, clause: str, params: dict[str, Any]) -> dict[str, int]:
    """Files per outcome for the same owner and case, before any outcome filter."""
    keep = {k: v for k, v in params.items() if k in ("actor", "exact")}
    rows = db.execute(
        text(f"SELECT u.outcome, count(*) FROM uploads u JOIN cases c ON c.case_id = u.case_id WHERE {clause} GROUP BY u.outcome"),
        keep,
    ).all()
    return {outcome: n for outcome, n in rows}


def list_documents(
    db: Session, *, actor: str, role: ActorRole, case: str | None, client: str | None, outcome: str | None,
    page: int, page_size: int, exact_case: str | None = None,
) -> DocumentPage:  # fmt: skip
    where = [f"{owner_column(role)} = :actor", "u.deleted_at IS NULL"]
    params: dict[str, Any] = {"actor": actor}
    if exact_case:
        # One case by id, a draft included. The lists across cases never show a draft.
        where.append("u.case_id = :exact")
        params["exact"] = exact_case
    else:
        where.append("c.case_id NOT IN (SELECT case_id FROM case_workflows WHERE status IN ('DRAFT', 'DELETED'))")
    if case:
        where.append("lower(u.case_id) LIKE :case ESCAPE '\\'")
        params["case"] = _like(case.strip())
    if client:
        where.append(f"lower({_CLIENT_NAME}) LIKE :client ESCAPE '\\'")
        params["client"] = _like(client.strip())
    counted = " AND ".join(where)
    if outcome:
        # Several outcomes may be given, separated by commas.
        where.append("u.outcome = ANY(:outcomes)")
        params["outcomes"] = [o.strip() for o in outcome.split(",") if o.strip()]
    clause = " AND ".join(where)
    source = f"FROM uploads u JOIN cases c ON c.case_id = u.case_id WHERE {clause}"
    total = db.execute(text(f"SELECT count(*) {source}"), params).scalar_one()
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    params.update(limit=size, offset=(max(1, page) - 1) * size)
    rows = db.execute(
        text(
            f"SELECT u.upload_id, u.case_id, {_CLIENT_NAME} AS client_name, u.original_filename, u.category, {CATEGORY_TITLE} AS category_title, u.outcome, "
            f"u.outcome_reason, u.file_size_bytes, u.uploaded_at, u.uploader_role, u.reason_code, "
            "u.duplicate_of_upload_id AS duplicate_of, u.flags, "
            f"EXISTS (SELECT 1 FROM document_reads r WHERE r.upload_id = u.upload_id AND r.injection_flag) AS read_injection {source} "
            "ORDER BY u.uploaded_at DESC, u.upload_id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).all()
    pages = _pages(db, [r.upload_id for r in rows]) if exact_case else {}
    items = [_row(r, pages.get(r.upload_id, [])) for r in rows]
    counts = _outcome_counts(db, counted, params) if exact_case else {}
    return DocumentPage(total=total, page=max(1, page), page_size=size, items=items, counts=counts)
