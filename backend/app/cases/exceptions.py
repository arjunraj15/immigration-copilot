"""Exception items for the Exceptions page and the home page reasons. One list of defects, built from real rows only.

Document defects come from the outcome and reason code saved on each upload. Conflicts come from the facts tables
without calling a model. Deadlines come from validation.deadlines.build_due. Nothing here reads another user's case, and a file that
belongs to another client is described only as belonging to a different client.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, computed_field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import home, repository
from app.cases.service import humanize
from app.core.contracts import ActorRole, ProposalStatus
from app.core.security import Actor
from app.facts import engine
from app.ingest import service as ingest
from app.validation import deadlines
from app.validation.reasons import MESSAGES, Reason

Severity = Literal["HIGH", "MEDIUM", "LOW"]
SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

SUSPICIOUS_TEXT, WRONG_CLIENT, MIXED_CLIENTS = "SUSPICIOUS_TEXT", "WRONG_CLIENT", "MIXED_CLIENTS"
UNREADABLE, EXPIRED, STALE = "UNREADABLE", "EXPIRED", "STALE"
NEEDS_TRANSLATION, DUPLICATE, SUPERSEDED = "NEEDS_TRANSLATION", "DUPLICATE", "SUPERSEDED"
MISSING_DOCUMENT, HUMAN_REVIEW = "MISSING_DOCUMENT", "HUMAN_REVIEW"
FACT_CONFLICT, DEADLINE_CONFLICT, OVERDUE = "FACT_CONFLICT", "DEADLINE_CONFLICT", "OVERDUE"
PROPOSAL_REJECTED, PROPOSAL_PENDING = "PROPOSAL_REJECTED", "PROPOSAL_PENDING"
# A gap the client has to fill. It goes to legal marked as a gap, the form row stays not available and nothing is guessed.
GAP_TYPES = (NEEDS_TRANSLATION, MISSING_DOCUMENT)

# The order a document defect wins as the reason on the home page.
DOCUMENT_PRECEDENCE = (
    SUSPICIOUS_TEXT, WRONG_CLIENT, MIXED_CLIENTS, UNREADABLE, EXPIRED, STALE, NEEDS_TRANSLATION, DUPLICATE,
    MISSING_DOCUMENT, HUMAN_REVIEW,
)  # fmt: skip
OPEN_DOCUMENTS, REVIEW_CONFLICT, OPEN_CASE, REWORK = "Open documents", "Review conflict", "Open case", "Rework proposal"
# Reason code on the upload: (type, title, severity).
BY_CODE: dict[str, tuple[str, str, Severity]] = {
    "DUPLICATE": (DUPLICATE, "Duplicate file", "LOW"),
    "WRONG_CLIENT": (WRONG_CLIENT, "Wrong client", "HIGH"),
    "MIXED_CLIENTS": (MIXED_CLIENTS, "Mixed clients", "HIGH"),
    "UNREADABLE": (UNREADABLE, "Unreadable file", "MEDIUM"),
    "BLANK": (UNREADABLE, "Blank file", "MEDIUM"),
    "ROTATED": (UNREADABLE, "Rotated scan", "MEDIUM"),
    "SUPERSEDED": (SUPERSEDED, "Older version", "LOW"),
    "EXPIRED": (EXPIRED, "Expired passport", "MEDIUM"),
    "STALE": (STALE, "Stale employer letter", "MEDIUM"),
    "NEEDS_TRANSLATION": (NEEDS_TRANSLATION, "Needs translation", "MEDIUM"),
    "PAY_PERIOD": (HUMAN_REVIEW, "Wrong pay period", "MEDIUM"),
    "NO_REFERENCE": (HUMAN_REVIEW, "Prior notice has no reference number", "MEDIUM"),
    "SCANNED_PAGE": (HUMAN_REVIEW, "Scanned page needs a check", "LOW"),
    Reason.INVALID_DATE: (HUMAN_REVIEW, "A date is not a real date", "MEDIUM"),
    Reason.AMBIGUOUS_DATE: (HUMAN_REVIEW, "A date is ambiguous", "MEDIUM"),
    Reason.BIRTH_NOT_PAST: (HUMAN_REVIEW, "Birth date is not in the past", "MEDIUM"),
    Reason.EXPIRY_BEFORE_BIRTH: (HUMAN_REVIEW, "Passport expiry is before the birth date", "MEDIUM"),
    Reason.START_IN_FUTURE: (HUMAN_REVIEW, "Employment start is in the future", "MEDIUM"),
    Reason.ENTRY_IN_FUTURE: (HUMAN_REVIEW, "Last entry date is in the future", "MEDIUM"),
    Reason.BAD_REFERENCE: (HUMAN_REVIEW, "Reference number has the wrong format", "MEDIUM"),
    Reason.NAME_INCONSISTENT: (HUMAN_REVIEW, "Applicant name differs between pages", "MEDIUM"),
    Reason.CLIENT_NAME_MISMATCH: (HUMAN_REVIEW, "Applicant name does not match the client", "MEDIUM"),
    Reason.VALUE_MISMATCH: (HUMAN_REVIEW, "AI value differs from the page", "MEDIUM"),
}
FALLBACK = (HUMAN_REVIEW, "Human review needed", "MEDIUM")
# Quarantine text never carries anything from the file itself, only that it belongs to someone else.
HIDDEN = "to a different client. Its details are hidden."


class ExceptionItem(BaseModel):
    case_id: str
    client_name: str
    type: str
    severity: Severity
    title: str
    reason: str
    source_ids: list[str]
    next_action: str
    owner_role: ActorRole

    @computed_field  # type: ignore[prop-decorator]
    @property
    def blocks_send(self) -> bool:
        """An open exception stops the form draft going to legal. An older version or a duplicate file (low severity) does not
        stop it, neither does the state of a proposal that was already sent, and neither does a gap only the client can fill, a
        missing document or a missing translation. Legal sees that gap on the form and the packet."""
        return self.type not in (PROPOSAL_PENDING, PROPOSAL_REJECTED, *GAP_TYPES) and self.severity != "LOW"


class ExceptionList(BaseModel):
    items: list[ExceptionItem]
    counts: dict[str, int]
    total: int


def _item(case_id: str, name: str, kind: str, severity: Severity, title: str, reason: str, ids: list[str],
          action: str = OPEN_DOCUMENTS, owner: ActorRole = ActorRole.OPS) -> ExceptionItem:  # fmt: skip
    return ExceptionItem(case_id=case_id, client_name=name, type=kind, severity=severity, title=title, reason=reason,
                         source_ids=ids, next_action=action, owner_role=owner)  # fmt: skip


def _quarantine_reason(code: str, flags: dict[str, Any]) -> str:
    if code != MIXED_CLIENTS:
        return f"This file belongs {HIDDEN}"
    found = flags.get("foreign_pages") or []
    pages = ", ".join(str(p) for p in found)
    if len(found) == 1:
        return f"Page {pages} belongs {HIDDEN}"
    return f"Pages {pages} belong {HIDDEN}" if pages else f"Some pages belong {HIDDEN}"


def upload_items(row: Any, name: str) -> list[ExceptionItem]:
    """The defects of one upload row, from its saved outcome, reason code and injection flags."""
    flags = row.flags or {}
    items: list[ExceptionItem] = []
    if flags.get("injection") or row.injection:
        reason = "Text inside this file tried to give instructions. It was flagged and not followed."
        items.append(_item(row.case_id, name, SUSPICIOUS_TEXT, "HIGH", "Suspicious text in file", reason, [row.upload_id]))
    if row.outcome in ("USABLE", "CLAIM_SOURCE", "PENDING", "READING"):
        return items
    code = row.reason_code or ""
    kind, title, severity = BY_CODE.get(code, FALLBACK)
    ids = [row.upload_id]
    if kind == DUPLICATE and row.duplicate_of_upload_id:
        ids.append(row.duplicate_of_upload_id)
    if kind in (WRONG_CLIENT, MIXED_CLIENTS):
        reason = _quarantine_reason(kind, flags)
    else:
        reason = row.outcome_reason or MESSAGES.get(code, title)
    items.append(_item(row.case_id, name, kind, severity, title, reason, ids))
    return items


def _load_uploads(db: Session, ids: list[str]) -> dict[str, list[Any]]:
    rows = db.execute(
        text(
            "SELECT u.upload_id, u.case_id, u.outcome, u.reason_code, u.outcome_reason, u.duplicate_of_upload_id, u.flags, "
            "EXISTS (SELECT 1 FROM document_reads r WHERE r.upload_id = u.upload_id AND r.injection_flag) AS injection "
            "FROM uploads u WHERE u.case_id = ANY(:ids) AND u.deleted_at IS NULL ORDER BY u.uploaded_at, u.upload_id"
        ),
        {"ids": ids},
    ).all()
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(row.case_id, []).append(row)
    return grouped


def missing_items(db: Session, case_id: str, name: str, uploads: list[Any]) -> list[ExceptionItem]:
    """Required categories with no upload at all. A case with no files at all misses every one. Not while a file is still being read."""
    if any(u.outcome in ("PENDING", "READING") for u in uploads):
        return []
    return [
        _item(case_id, name, MISSING_DOCUMENT, "HIGH", f"Missing {c.label[:1].lower() + c.label[1:]}",  # a required document, so high
              f"No {c.label[:1].lower() + c.label[1:]} has been uploaded.", [])
        for c in ingest.checklist(db, case_id)
        if c.status == "MISSING"
    ]  # fmt: skip


def document_items(db: Session, records: list[repository.CaseRecord]) -> dict[str, list[ExceptionItem]]:
    """Document defects, injection flags and missing categories for each case."""
    uploads = _load_uploads(db, [r.case_id for r in records])
    result: dict[str, list[ExceptionItem]] = {}
    for record in records:
        rows = uploads.get(record.case_id, [])
        items = [i for row in rows for i in upload_items(row, record.display_name)]
        result[record.case_id] = items + reference_items(rows, record.case_id, record.display_name) + missing_items(db, record.case_id, record.display_name, rows)
    return result


def reference_items(rows: list[Any], case_id: str, name: str) -> list[ExceptionItem]:
    """The reference numbers on the usable documents of one case, such as the travel ID next to the passport and receipt numbers,
    belong to one set. Two sets in one case mean a document may not be this person's, so a person looks. Nothing is quarantined."""
    serials = {r.upload_id: set((r.flags or {}).get("ref_serials") or []) for r in rows if r.outcome in ("USABLE", "NEEDS_HUMAN_REVIEW")}
    distinct = sorted(set().union(*serials.values())) if serials else []
    if len(distinct) < 2:
        return []
    ids = sorted(u for u, s in serials.items() if s)
    reason = f"The reference numbers on {', '.join(ids)} come from different sets ({', '.join(distinct)}). One of them may not belong to this client."
    return [_item(case_id, name, HUMAN_REVIEW, "MEDIUM", "Reference numbers differ between documents", reason, ids)]


def top_document_item(items: list[ExceptionItem]) -> ExceptionItem | None:
    """The defect that wins on the home page. SUPERSEDED and the non document types never do."""
    ranked = [i for i in items if i.type in DOCUMENT_PRECEDENCE]
    return min(ranked, key=lambda i: DOCUMENT_PRECEDENCE.index(i.type), default=None)


def _date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def _conflict_items(case_id: str, name: str, conflicts: list[engine.FieldState]) -> list[ExceptionItem]:
    return [
        _item(case_id, name, FACT_CONFLICT, "HIGH" if c.severity == "high" else "MEDIUM", f"{c.label} conflict",
              f"Sources disagree on {c.label.lower()}. " + ("An attorney must decide." if c.severity == "high" else "Operations or an attorney can decide."), [s.source_id for s in c.sources],
              "Review conflict" if c.severity == "high" else "Resolve conflict",
              ActorRole.LEGAL if c.severity == "high" else ActorRole.OPS)
        for c in conflicts
    ]  # fmt: skip


def _due_items(case_id: str, name: str, due: deadlines.Due | None) -> list[ExceptionItem]:
    if due is None:
        return []
    items = []
    if due.calendar_date is not None and due.calendar_event_id:
        reason = (f"The portal request on {_date(due.request_date)} gives {_date(due.date)}. "
                  f"A calendar entry says {_date(due.calendar_date)}. The calendar is not evidence.")  # fmt: skip
        items.append(_item(case_id, name, DEADLINE_CONFLICT, "HIGH", "Deadline conflict", reason,
                           [due.request_event_id, due.calendar_event_id], REVIEW_CONFLICT, ActorRole.LEGAL))  # fmt: skip
    if due.days_left < 0:
        reason = f"The deadline of {_date(due.date)} has passed."
        items.append(_item(case_id, name, OVERDUE, "HIGH", "Deadline overdue", reason, [due.request_event_id], OPEN_CASE))
    return items


def _proposal_items(case_id: str, name: str, proposals: list[dict[str, Any]]) -> list[ExceptionItem]:
    items = []
    for p in proposals:
        label = humanize(p["kind"])
        if p["status"] == ProposalStatus.REJECTED.value:
            why = f" Reason: {p['review_reason']}" if p["review_reason"] else ""
            items.append(_item(case_id, name, PROPOSAL_REJECTED, "HIGH", f"{label} rejected", f"{label} was rejected.{why}",
                               [p["proposal_id"]], REWORK))  # fmt: skip
        if p["status"] == ProposalStatus.PENDING_LEGAL_REVIEW.value:
            items.append(_item(case_id, name, PROPOSAL_PENDING, "LOW", f"{label} waiting for legal",
                               f"{label} is waiting for a legal decision.", [p["proposal_id"]], OPEN_CASE, ActorRole.LEGAL))  # fmt: skip
    return items


def build_items(db: Session, actor: Actor) -> list[ExceptionItem]:
    """Every exception on the actor's own cases, drafts excluded, most severe first."""
    as_of = repository.get_as_of(db)
    records = repository.list_cases_for_actor(db, actor=actor.label, role=actor.role, term=None, as_of=as_of)
    if not records:
        return []
    ids = [r.case_id for r in records]
    rule = home.load_rule(db)
    events, proposals = home.load_events(db, ids, rule), home.load_proposals(db, ids)
    documents = document_items(db, records)
    items: list[ExceptionItem] = []
    for r in records:
        due = deadlines.build_due(events.get(r.case_id, []), rule, False, as_of)
        conflicts = [s for s in engine.compute_states(db, r.case_id) if s.state == engine.CONFLICT]
        items += documents[r.case_id] + _conflict_items(r.case_id, r.display_name, conflicts)
        items += _due_items(r.case_id, r.display_name, due) + _proposal_items(r.case_id, r.display_name, proposals.get(r.case_id, []))
    return sorted(items, key=lambda i: (SEVERITY_ORDER[i.severity], i.case_id))


def blocking_items(db: Session, actor: Actor, case_id: str) -> list[ExceptionItem]:
    """The exceptions of one case that stop the form draft going to legal."""
    return [i for i in build_items(db, actor) if i.case_id == case_id and i.blocks_send]


def build_list(db: Session, actor: Actor, kind: str | None = None, q: str | None = None) -> ExceptionList:
    """Items with a case id or client name filter, then counts per type, then the optional type filter."""
    items = build_items(db, actor)
    term = (q or "").strip().lower()
    if term:
        items = [i for i in items if term in i.case_id.lower() or term in i.client_name.lower()]
    counts: dict[str, int] = {}
    for item in items:
        counts[item.type] = counts.get(item.type, 0) + 1
    if kind:
        items = [i for i in items if i.type == kind]
    return ExceptionList(items=items, counts=counts, total=len(items))
