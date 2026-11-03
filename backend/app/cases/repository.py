"""Case data access. Every function that returns case-owned data takes a case_id, so no caller can read
across cases by accident. Only the queue and actor lists span cases, and they are limited to one actor."""

from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.contracts import ActorRole
from app.core.errors import AppError
from app.validation.context import RuleContext, build_context

NAME_FIELD = "full_name"
RECEIPT_FIELD = "prior_receipt_number"


class CaseRecord(BaseModel):
    case_id: str
    client_ref: str
    case_archetype: str
    operational_stage: str
    assigned_ops_user: str
    assigned_legal_reviewer: str
    display_name: str
    status: str
    wizard_step: int
    decided_recently: bool
    upload_count: int
    last_upload_at: Any | None


# The display name is the latest human decision on the name, else the verified profile value.
_CASE_SELECT = f"""
SELECT c.case_id, c.client_ref, c.case_archetype, c.operational_stage, c.assigned_ops_user,
    c.assigned_legal_reviewer,
    COALESCE(
        (SELECT d.corrected_value FROM review_decisions d
          WHERE d.case_id = c.case_id AND d.field_name = '{NAME_FIELD}' AND d.corrected_value IS NOT NULL
          ORDER BY d.recorded_at DESC, d.id DESC LIMIT 1),
        (SELECT p.verified_value FROM profile_fields p WHERE p.case_id = c.case_id AND p.field_name = '{NAME_FIELD}'),
        c.case_id) AS display_name,
    w.status, w.wizard_step,
    COALESCE(w.decided_at::date >= CAST(:as_of AS date) - 7, false) AS decided_recently,
    (SELECT count(*) FROM uploads u WHERE u.case_id = c.case_id AND u.deleted_at IS NULL) AS upload_count,
    (SELECT max(u.uploaded_at) FROM uploads u WHERE u.case_id = c.case_id AND u.deleted_at IS NULL) AS last_upload_at
FROM cases c JOIN case_workflows w ON w.case_id = c.case_id
"""


def _like(term: str) -> str:
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def get_as_of(db: Session) -> date:
    """The review date from the rules file. Never the system clock."""
    row = db.execute(
        text(
            "SELECT COALESCE(body->>'as_of', body->>'review_as_of') AS as_of FROM rule_sets "
            "WHERE key IN ('deadline_rules', 'document_rules') AND COALESCE(body->>'as_of', body->>'review_as_of') "
            "IS NOT NULL ORDER BY (key = 'deadline_rules') DESC, version DESC LIMIT 1"
        )
    ).first()
    if row is None:
        raise AppError("RULES_NOT_LOADED", "The starter kit is not loaded. Run make seed.", 503)
    return date.fromisoformat(row.as_of)


def get_rule_body(db: Session, key: str) -> dict[str, Any] | None:
    """The newest version of a rule set."""
    return db.execute(text("SELECT body FROM rule_sets WHERE key = :key ORDER BY version DESC LIMIT 1"), {"key": key}).scalar()


def load_context(db: Session) -> RuleContext:
    """The review date and the parsed document and deadline rules, built once for the validation layer."""
    return build_context(get_rule_body(db, "document_rules"), get_rule_body(db, "deadline_rules"), get_as_of(db))


def get_case(db: Session, case_id: str, as_of: date) -> CaseRecord | None:
    row = db.execute(text(f"{_CASE_SELECT} WHERE c.case_id = :case_id"), {"case_id": case_id, "as_of": as_of}).first()
    return CaseRecord.model_validate(row._mapping) if row else None


def list_cases_for_actor(
    db: Session, *, actor: str, role: ActorRole, term: str | None, as_of: date
) -> list[CaseRecord]:
    owner = "c.assigned_ops_user" if role == ActorRole.OPS else "c.assigned_legal_reviewer"
    where = f"WHERE {owner} = :actor AND w.status NOT IN ('DRAFT', 'DELETED')"
    params: dict[str, Any] = {"actor": actor, "as_of": as_of}
    if term:
        params["pattern"] = _like(term)
        where += f"""
            AND (lower(c.case_id) LIKE :pattern ESCAPE '\\' OR lower(c.client_ref) LIKE :pattern ESCAPE '\\'
              OR lower(COALESCE(
                    (SELECT d.corrected_value FROM review_decisions d
                      WHERE d.case_id = c.case_id AND d.field_name = '{NAME_FIELD}' AND d.corrected_value IS NOT NULL
                      ORDER BY d.recorded_at DESC, d.id DESC LIMIT 1),
                    (SELECT p.verified_value FROM profile_fields p
                      WHERE p.case_id = c.case_id AND p.field_name = '{NAME_FIELD}'), '')) LIKE :pattern ESCAPE '\\'
              OR EXISTS (SELECT 1 FROM profile_fields p WHERE p.case_id = c.case_id AND p.field_name = '{RECEIPT_FIELD}'
                    AND lower(p.verified_value) LIKE :pattern ESCAPE '\\')
              OR EXISTS (SELECT 1 FROM case_events e WHERE e.case_id = c.case_id
                    AND lower(e.source_reference) LIKE :pattern ESCAPE '\\'))
        """
    rows = db.execute(text(f"{_CASE_SELECT} {where} ORDER BY c.case_id"), params).all()
    return [CaseRecord.model_validate(row._mapping) for row in rows]


def list_actors(db: Session) -> list[dict[str, Any]]:
    """Every OPS and LEGAL user with how many cases they hold. The actors table keeps a user when their cases are gone."""
    rows = db.execute(
        text(
            """
            SELECT a.label, a.role, count(c.case_id) AS case_count FROM (
                SELECT label, role FROM actors
                UNION SELECT assigned_ops_user, 'OPS' FROM cases
                UNION SELECT assigned_legal_reviewer, 'LEGAL' FROM cases) a
            LEFT JOIN cases c ON c.case_id NOT IN (SELECT case_id FROM case_workflows WHERE status IN ('DRAFT', 'DELETED'))
                AND ((a.role = 'OPS' AND c.assigned_ops_user = a.label)
                     OR (a.role = 'LEGAL' AND c.assigned_legal_reviewer = a.label))
            GROUP BY a.label, a.role ORDER BY a.role DESC, a.label
            """
        )
    ).all()
    return [dict(row._mapping) for row in rows]


def count_cases_for_actor(db: Session, *, actor: str, role: ActorRole) -> int:
    column = "assigned_ops_user" if role == ActorRole.OPS else "assigned_legal_reviewer"
    draft = "case_id NOT IN (SELECT case_id FROM case_workflows WHERE status IN ('DRAFT', 'DELETED'))"
    return db.execute(text(f"SELECT count(*) FROM cases WHERE {column} = :actor AND {draft}"), {"actor": actor}).scalar_one()


def get_portal_status(db: Session, case_id: str) -> dict[str, Any] | None:
    """The newest verified status snapshot from the portal."""
    row = db.execute(
        text(
            "SELECT event_id, event_date, details FROM case_events WHERE case_id = :case_id "
            "AND event_source = 'MOCK_PORTAL' AND source_verified AND event_type = 'STATUS_SNAPSHOT' "
            "ORDER BY event_date DESC, id DESC LIMIT 1"
        ),
        {"case_id": case_id},
    ).first()
    return dict(row._mapping) if row else None


def list_events(db: Session, case_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT event_id, event_date, event_type, event_source, source_reference, details, source_verified, "
            "import_batch FROM case_events WHERE case_id = :case_id ORDER BY event_date, id"
        ),
        {"case_id": case_id},
    ).all()
    return [dict(row._mapping) for row in rows]


def add_calendar_event(
    db: Session, case_id: str, *, event_date: date, event_type: str, details: str, event_id: str, reference: str
) -> bool:
    """Store one hand-typed calendar entry. It is always unverified. False when the same entry already exists."""
    row = db.execute(
        text(
            "INSERT INTO case_events (event_id, case_id, event_date, event_type, event_source, source_reference, "
            "details, source_verified, import_batch) VALUES (:event_id, :case_id, :event_date, :event_type, "
            "'GOOGLE_CALENDAR_MOCK', :reference, :details, FALSE, 'DEMO-MANUAL') "
            "ON CONFLICT DO NOTHING RETURNING event_id"
        ),
        {"event_id": event_id, "case_id": case_id, "event_date": event_date, "event_type": event_type,
         "reference": reference, "details": details},
    ).first()  # fmt: skip
    return row is not None


def delete_calendar_event(db: Session, case_id: str, event_id: str) -> bool:
    """Remove a demo calendar entry. Seeded events are never deleted, only rows typed in through the form."""
    row = db.execute(
        text("DELETE FROM case_events WHERE case_id = :case_id AND event_id = :event_id AND import_batch = 'DEMO-MANUAL' RETURNING event_id"),
        {"case_id": case_id, "event_id": event_id},
    ).first()
    return row is not None


def list_intake_notes(db: Session, case_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT intake_id, recorded_at, platform, speaker, summary, ai_generated, approved_as_fact "
            "FROM intake_notes WHERE case_id = :case_id ORDER BY recorded_at, id"
        ),
        {"case_id": case_id},
    ).all()
    return [dict(row._mapping) for row in rows]


def list_messages(db: Session, case_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT message_id, thread_id, created_at_source AS created_at, channel, direction, sender_role, subject, "
            "body, attachment_refs, delivery_state FROM messages WHERE case_id = :case_id "
            "ORDER BY created_at_source, id"
        ),
        {"case_id": case_id},
    ).all()
    return [dict(row._mapping) for row in rows]


def list_profile_fields(db: Session, case_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT source_id, field_name, verified_value, verification_state, verified_at, verified_by "
            "FROM profile_fields WHERE case_id = :case_id ORDER BY field_name"
        ),
        {"case_id": case_id},
    ).all()
    return [dict(row._mapping) for row in rows]
