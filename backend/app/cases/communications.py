"""Calls and messages of one case in date order. Pasted or uploaded text files of a communication type are listed too. Zoom notes, WhatsApp and email are claims and never facts.

Replies written by the office are drafts and are never sent.
"""

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

DRAFT_ONLY = "OUTBOUND_DRAFT_ONLY"

_SELECT = """
SELECT x.*, k.claims, k.asked, md.status AS draft_status FROM (
    SELECT n.intake_id AS source_id, 'ZOOM' AS kind, 'NOTE' AS direction,
        CASE WHEN n.speaker = 'Intake Coordinator' THEN 'INTAKE_COORDINATOR' ELSE 'OPERATIONS' END AS sender_role,
        NULL AS subject, n.summary AS body, NULL AS thread_id, n.recorded_at AS occurred_at
    FROM intake_notes n WHERE n.case_id = :c
    UNION ALL
    SELECT m.message_id, m.channel, m.direction, m.sender_role, m.subject, m.body, m.thread_id, m.created_at_source
    FROM messages m WHERE m.case_id = :c
    UNION ALL
    SELECT u.upload_id, CASE u.category WHEN 'ZOOM_NOTES' THEN 'ZOOM' WHEN 'WHATSAPP_CHAT' THEN 'WHATSAPP' ELSE 'EMAIL' END,
        CASE WHEN u.category = 'ZOOM_NOTES' THEN 'NOTE' ELSE 'INBOUND' END,
        CASE WHEN u.category = 'ZOOM_NOTES' THEN 'OPERATIONS' ELSE 'CLIENT' END,
        u.original_filename, COALESCE(u.note_text, ''), NULL, COALESCE(u.occurred_at, u.uploaded_at)
    FROM uploads u WHERE u.case_id = :c AND u.deleted_at IS NULL AND u.category IN ('ZOOM_NOTES', 'WHATSAPP_CHAT', 'EMAIL_MESSAGE')
    UNION ALL
    SELECT d.draft_id, d.channel, 'OUTBOUND_DRAFT_ONLY', 'OPERATIONS', d.subject, d.body, NULL, d.created_at
    FROM message_drafts d WHERE d.case_id = :c
) x
LEFT JOIN (SELECT source_id AS claim_source, count(*) AS claims, bool_or(field_name = 'client_question') AS asked
           FROM claims WHERE case_id = :c GROUP BY source_id) k ON k.claim_source = x.source_id
LEFT JOIN message_drafts md ON md.draft_id = x.source_id AND md.case_id = :c
ORDER BY x.occurred_at, x.source_id
"""


class ClaimRow(BaseModel):
    field: str
    value: str
    quote: str


class Communication(BaseModel):
    source_id: str
    kind: str
    direction: str
    sender_role: str
    subject: str | None
    body: str
    thread_id: str | None
    occurred_at: str
    is_draft: bool
    claim: bool = True
    client_question: bool
    claims: int
    role: str
    claim_rows: list[ClaimRow] = []
    draft_status: str | None = None  # set for a draft written in this app, never for a kit draft


def is_question(direction: str, body: str, asked: bool | None) -> bool:
    """An inbound client message with a question mark in it, or one the claims table marks as a client question."""
    return direction == "INBOUND" and ("?" in body or bool(asked))


def role_of(row: dict, intake_call: str | None) -> str:
    """The intake call is the earliest Zoom note. A draft reply is an office draft. Everything else is an update."""
    if row["source_id"] == intake_call:
        return "INTAKE_CALL"
    return "OFFICE_DRAFT" if row["direction"] == DRAFT_ONLY else "UPDATE"


def list_communications(db: Session, case_id: str) -> list[Communication]:
    rows = db.execute(text(_SELECT), {"c": case_id}).mappings().all()
    found = db.execute(text("SELECT source_id, field_name, value, quote FROM claims WHERE case_id = :c ORDER BY id"), {"c": case_id}).all()
    by_source: dict[str, list[ClaimRow]] = {}
    for c in found:
        by_source.setdefault(c.source_id, []).append(ClaimRow(field=c.field_name, value=c.value, quote=c.quote))
    intake_call = next((r["source_id"] for r in rows if r["kind"] == "ZOOM"), None)  # rows are in time order
    return [
        Communication(
            source_id=r["source_id"], kind=r["kind"], direction=r["direction"], sender_role=r["sender_role"],
            subject=r["subject"], body=r["body"], thread_id=r["thread_id"], occurred_at=r["occurred_at"].isoformat(),
            is_draft=r["direction"] == DRAFT_ONLY, client_question=is_question(r["direction"], r["body"], r["asked"]),
            claims=r["claims"] or 0, role=role_of(r, intake_call),
            claim_rows=by_source.get(r["source_id"], []), draft_status=r["draft_status"],
        )  # fmt: skip
        for r in rows
    ]


def intake_call_id(db: Session, case_id: str) -> str | None:
    """The source id of the earliest Zoom note of the case, a note or an uploaded Zoom file."""
    return next((c.source_id for c in list_communications(db, case_id) if c.role == "INTAKE_CALL"), None)
