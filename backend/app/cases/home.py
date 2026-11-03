"""Rows for the home page. Reasons and due dates are worked out here from data that exists in the database.

The rules are pure functions. The loader reads only the acting user's cases, so nothing crosses users."""

from collections.abc import Callable
import time
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cases import repository
from app.cases.repository import CaseRecord
from app.cases.service import Tone, humanize
from app.core.audit import AuditEntry
from app.core.audit_display import describe
from app.core.config import get_settings
from app.core.contracts import ActorRole, AuditAction, ProposalKind, ProposalStatus
from app.core.security import Actor
from app.facts import engine
from app.facts.engine import FieldState
from app.validation.deadlines import CALENDAR_DEADLINE, Due, DueState, Rule, build_due, read_rule  # noqa: F401

if TYPE_CHECKING:
    from app.cases.exceptions import ExceptionItem

DEADLINE_RULE_KEY = "deadline_rules"
WINDOW_DAYS = 14
ACTIVITY_LIMIT = 20
PAGE_SIZE = 10  # the most rows one page of the queue ever carries
SOON_DAYS = 3
KPI_KEYS = ("attention", "soon", "overdue", "legal", "quarantined")
# Opening a case writes this line, so it would fill the feed with the user's own clicks.
QUIET_ACTIONS = (AuditAction.CASE_ACCESS.value,)


class Reason(BaseModel):
    key: str
    label: str
    tone: Tone
    text: str


class HomeRow(BaseModel):
    case_id: str
    name: str
    stage: str
    ops_user: str
    legal_reviewer: str
    priority: str
    workflow_status: str
    reason: Reason
    due: Due | None
    next_action: str
    attention: bool
    legal_review: bool
    refs: list[str]


class Deadline(BaseModel):
    case_id: str
    name: str
    date: date
    state: DueState
    days_left: int


class Activity(BaseModel):
    case_id: str | None
    name: str | None
    occurred_at: datetime
    actor: str
    action: AuditAction
    label: str
    tone: Tone
    title: str
    note: str


class Option(BaseModel):
    value: str
    label: str
    count: int
    tone: Tone | None = None  # the colour of a reason tile


class Filters(BaseModel):
    kpi: str | None = None
    stage: str | None = None
    reason: str | None = None
    term: str | None = None
    just_me: bool = True
    case_id: str | None = None


class Home(BaseModel):
    as_of: date
    rows: list[HomeRow]  # one page of the filtered queue, in urgency order
    page: int = 1
    page_size: int = PAGE_SIZE
    total: int = 0  # rows that pass every filter
    assigned: int = 0  # all of the acting user's cases, filters ignored
    kpi_total: int = 0  # rows that pass every filter except the tile filter
    kpi_counts: dict[str, int] = {}
    stages: list[Option] = []
    reasons: list[Option] = []
    deadlines: list[Deadline]
    activity: list[Activity]


# Reason key: (label, tone, next action). The list order is the urgency order of the table.
REASONS: dict[str, tuple[str, Tone, str]] = {
    "suspicious_text": ("Suspicious text", "bad", "Open documents"),
    "wrong_client": ("Wrong client", "bad", "Open documents"),
    "mixed_clients": ("Mixed clients", "bad", "Open documents"),
    "unreadable": ("Unreadable file", "bad", "Open documents"),
    "expired": ("Expired passport", "bad", "Open documents"),
    "stale": ("Stale letter", "warn", "Open documents"),
    "needs_translation": ("Needs translation", "warn", "Open documents"),
    "duplicate": ("Duplicate file", "warn", "Open documents"),
    "rejected": ("Proposal rejected", "bad", "Rework proposal"),
    "info_requested": ("Info requested", "warn", "Answer attorney"),
    "deadline_conflict": ("Deadline conflict", "bad", "Review conflict"),
    "identity_mismatch": ("Identity mismatch", "bad", "Review conflict"),
    "facts_conflict": ("Facts conflict", "warn", "Resolve conflict"),
    "missing_document": ("Missing document", "warn", "Open documents"),
    "human_review": ("Human review", "warn", "Open documents"),
    "approved": ("Approved", "ok", "Apply change"),
    "waiting_legal": ("Waiting on legal", "ai", "Open case"),
    "waiting_portal": ("Waiting on portal", "muted", "Open case"),
    "working": ("No open issue", "muted", "Open case"),
}
FACT_REASONS = {"identity_mismatch", "facts_conflict"}
RANK = {key: index for index, key in enumerate(REASONS)}
# These two document reasons rank below the attorney facing ones, so a conflict or a decision is never hidden by them.
SOFT_DOCUMENT_REASONS = {"missing_document", "human_review"}
HARD_DOCUMENT_REASONS = set(list(REASONS)[:8])
ATTENTION = HARD_DOCUMENT_REASONS | SOFT_DOCUMENT_REASONS | {"rejected", "info_requested", "deadline_conflict", "identity_mismatch", "facts_conflict", "approved"}


def _proposal_reason(case_proposals: list[dict[str, Any]]) -> Reason | None:
    rejected = next((p for p in case_proposals if p["status"] == ProposalStatus.REJECTED.value), None)
    if rejected:
        why = f" Reason: {rejected['review_reason']}" if rejected["review_reason"] else ""
        return _reason("rejected", f"{humanize(rejected['kind'])} was rejected.{why}")
    pending = next((p for p in case_proposals if p["status"] == ProposalStatus.PENDING_LEGAL_REVIEW.value), None)
    if pending:
        return _reason("waiting_legal", f"{humanize(pending['kind'])} is waiting for a legal decision.")
    return None


def _reason(key: str, detail: str) -> Reason:
    label, tone, _ = REASONS[key]
    return Reason(key=key, label=label, tone=tone, text=detail)


def _facts_reason(conflicts: list[FieldState]) -> Reason | None:
    """A conflict between sources. A name, date of birth or identifier is an identity mismatch, the rest a facts conflict."""
    if not conflicts:
        return None
    high = [c for c in conflicts if c.severity == "high"]
    names = ", ".join(c.label.lower() for c in (high or conflicts))
    if high:
        return _reason("identity_mismatch", f"Sources disagree on {names}. An attorney must decide.")
    return _reason("facts_conflict", f"Sources disagree on {names}. Operations or an attorney can decide.")


def build_reason(
    record: CaseRecord, case_proposals: list[dict[str, Any]], due: Due | None, conflicts: list[FieldState] | None = None,
    defect: "ExceptionItem | None" = None,
) -> Reason:
    """One reason per case, the most urgent one. A hard document defect wins, then the attorney facing reasons, the conflicts, the soft document reasons and the rest."""
    if defect is not None and defect.type.lower() in HARD_DOCUMENT_REASONS:
        return _reason(defect.type.lower(), defect.reason)
    status = record.status
    from_proposal = _proposal_reason(case_proposals)
    rejected = from_proposal if from_proposal and from_proposal.key == "rejected" else None
    if rejected or status == "REJECTED":
        return rejected or _reason("rejected", "The attorney rejected this case and it needs rework.")
    if status == "INFO_REQUESTED":
        return _reason("info_requested", "The attorney asked for more information.")
    if due is not None and due.calendar_date is not None:
        return _reason("deadline_conflict", "A calendar entry has a different date than the portal evidence gives.")
    if from_facts := _facts_reason(conflicts or []):
        return from_facts
    if defect is not None:
        return _reason(defect.type.lower(), defect.reason)
    if status == "APPROVED":
        return _reason("approved", "The attorney approved. Ready to apply.")
    if status == "WITH_ATTORNEY":
        return _reason("waiting_legal", f"Waiting for {record.assigned_legal_reviewer} to decide.")
    if from_proposal:
        return from_proposal
    if record.operational_stage == "WAITING_FOR_PORTAL_EVENT":
        return _reason("waiting_portal", "Waiting for the portal to send an event.")
    return _reason("working", f"{humanize(record.operational_stage)}. Nothing is waiting on a person.")


def build_row(
    record: CaseRecord, priority: str, events: list[dict[str, Any]], case_proposals: list[dict[str, Any]],
    rule: Rule | None, as_of: date, conflicts: list[FieldState] | None = None, defect: "ExceptionItem | None" = None,
) -> HomeRow:  # fmt: skip
    approved = any(
        p["kind"] == ProposalKind.DEADLINE_ACTIVATE.value
        and p["status"] in (ProposalStatus.APPROVED.value, ProposalStatus.COMMITTED.value)
        for p in case_proposals
    )
    due = build_due(events, rule, approved, as_of)
    reason = build_reason(record, case_proposals, due, conflicts, defect)
    # Only a pending legal proposal, a case with the attorney or an identity conflict is a legal review item. A medium conflict is not.
    legal_review = (
        record.status == "WITH_ATTORNEY"
        or any(p["status"] == ProposalStatus.PENDING_LEGAL_REVIEW.value for p in case_proposals)
        or any(c.severity == "high" for c in conflicts or [])
    )
    refs = [due.request_event_id] if due else []
    refs += [due.calendar_event_id] if due and due.calendar_event_id else []
    refs += [p["proposal_id"] for p in case_proposals]
    refs += defect.source_ids if defect else []
    return HomeRow(
        case_id=record.case_id, name=record.display_name, stage=humanize(record.operational_stage),
        ops_user=record.assigned_ops_user, legal_reviewer=record.assigned_legal_reviewer, priority=priority,
        workflow_status=record.status, reason=reason, due=due, next_action=REASONS[reason.key][2],
        attention=reason.key in ATTENTION or (due is not None and due.state == "OVERDUE"), legal_review=legal_review,
        refs=refs,
    )  # fmt: skip


def sort_rows(rows: list[HomeRow]) -> list[HomeRow]:
    """Most urgent reason first, then the soonest due date, cases without a due date last."""
    far = date.max
    return sorted(rows, key=lambda r: (RANK[r.reason.key], r.due.date if r.due else far, r.case_id))


def matches_kpi(row: HomeRow, kpi: str) -> bool:
    if kpi == "attention":
        return row.attention
    if kpi == "soon":
        return row.due is not None and 0 <= row.due.days_left <= SOON_DAYS
    if kpi == "overdue":
        return row.due is not None and row.due.state == "OVERDUE"
    if kpi == "legal":
        return row.legal_review
    return row.reason.key in ("wrong_client", "mixed_clients")  # quarantined


def filter_rows(rows: list[HomeRow], filters: Filters, actor: str, skip: str | None = None) -> list[HomeRow]:
    """Rows that pass the filters. A skipped filter is ignored, which gives the counts shown beside each dropdown option and tile."""
    term = (filters.term or "").strip().lower()

    def keep(row: HomeRow) -> bool:
        if filters.case_id and row.case_id != filters.case_id:
            return False
        if skip != "just_me" and filters.just_me and actor not in (row.ops_user, row.legal_reviewer):
            return False
        if term and term not in f"{row.case_id} {row.name}".lower():
            return False
        if skip != "kpi" and filters.kpi and not matches_kpi(row, filters.kpi):
            return False
        if skip != "stage" and filters.stage and row.stage != filters.stage:
            return False
        return skip == "reason" or not filters.reason or row.reason.key == filters.reason

    return [row for row in rows if keep(row)]


def build_options(all_rows: list[HomeRow], counted: list[HomeRow], pick: Callable[[HomeRow], tuple[str, str]]) -> list[Option]:
    """Every value that exists in the data, in the order it first appears, with its count in the counted rows."""
    found: dict[str, Option] = {}
    for row in all_rows:
        value, label = pick(row)
        found[value] = Option(value=value, label=label, count=0)
    for row in counted:
        found[pick(row)[0]].count += 1
    return list(found.values())


def paginate(rows: list[HomeRow], page: int, page_size: int) -> tuple[list[HomeRow], int]:
    """One page of rows and the page number actually served. A page past the end serves the last page."""
    last = max(1, -(-len(rows) // page_size))
    served = min(max(page, 1), last)
    start = (served - 1) * page_size
    return rows[start : start + page_size], served


def build_deadlines(rows: list[HomeRow]) -> list[Deadline]:
    """Overdue and due within the window, soonest first."""
    items = [
        Deadline(case_id=r.case_id, name=r.name, date=r.due.date, state=r.due.state, days_left=r.due.days_left)
        for r in rows
        if r.due is not None and r.due.days_left < WINDOW_DAYS
    ]  # fmt: skip
    return sorted(items, key=lambda d: (d.date, d.case_id))


# ---------------------------------------------------------------- loading, limited to the acting user's cases


def _by_case(rows: Any) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row.case_id, []).append(dict(row._mapping))
    return grouped


def load_rule(db: Session) -> Rule | None:
    return read_rule(repository.get_rule_body(db, DEADLINE_RULE_KEY))


def load_events(db: Session, ids: list[str], rule: Rule | None) -> dict[str, list[dict[str, Any]]]:
    return _by_case(
        db.execute(
            text(
                "SELECT case_id, event_id, event_date, event_type, event_source, source_verified FROM case_events "
                "WHERE case_id = ANY(:ids) AND event_type = ANY(:types)"
            ),
            {"ids": ids, "types": [CALENDAR_DEADLINE, rule.event_type if rule else ""]},
        )
    )


def load_proposals(db: Session, ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    return _by_case(
        db.execute(
            text(
                "SELECT case_id, proposal_id, kind, status, review_reason FROM proposals "
                "WHERE case_id = ANY(:ids) ORDER BY id"
            ),
            {"ids": ids},
        )
    )


def load_activity(db: Session, names: dict[str, str]) -> list[Activity]:
    rows = db.execute(
        text(
            "SELECT * FROM audit_log WHERE case_id = ANY(:ids) AND NOT (action = ANY(:quiet)) "
            "ORDER BY occurred_at DESC, id DESC LIMIT :limit"
        ),
        {"ids": list(names), "quiet": list(QUIET_ACTIONS), "limit": ACTIVITY_LIMIT},
    ).all()
    items: list[Activity] = []
    for row in rows:
        entry = AuditEntry.model_validate(row._mapping)
        shown = describe(entry)
        items.append(
            Activity(
                case_id=entry.case_id, name=names.get(entry.case_id or ""), occurred_at=entry.occurred_at,
                actor=entry.actor, action=entry.action, label=shown.label, tone=shown.tone, title=shown.title,
                note=shown.note,
            )  # fmt: skip
        )
    return items


def _open_conflicts(db: Session, case_id: str) -> list[FieldState]:
    """Conflicts that no attorney has decided yet. Read only, so the home page never calls a model."""
    return [s for s in engine.compute_states(db, case_id) if s.state == engine.CONFLICT]


def _show_sent_conflicts(db: Session, rows: list[HomeRow], conflicts: dict[str, list[FieldState]]) -> None:
    """A conflict that operations sent to legal is the legal reviewer's first reason, ahead of a document defect on the same case."""
    sent = {
        (r.case_id, r.field): r
        for r in db.execute(
            text("SELECT DISTINCT ON (case_id, field) case_id, field, actor, leave_to_attorney, reason FROM conflict_suggestions "
                 "WHERE case_id = ANY(:ids) ORDER BY case_id, field, id DESC"),
            {"ids": [r.case_id for r in rows]},
        )
    }  # fmt: skip
    for row in rows:
        open_ones = [c for c in conflicts.get(row.case_id, []) if (row.case_id, c.field) in sent]
        if not open_ones:
            continue
        first = next((c for c in open_ones if c.severity == "high"), open_ones[0])
        note = sent[(row.case_id, first.field)]
        what = "left" if note.leave_to_attorney else "suggested a value for"
        row.reason = _reason("identity_mismatch" if first.severity == "high" else "facts_conflict",
                             f"{note.actor} {what} {first.label.lower()} for you to decide. {note.reason}")  # fmt: skip
        row.attention = True
        row.legal_review = True


class Computed(BaseModel):
    """Every row of one user's queue with the side rail, before filters and paging."""

    as_of: date
    rows: list[HomeRow]
    deadlines: list[Deadline]
    activity: list[Activity]


# Per user, for a few seconds. Urgency needs a check of every case, so page turns and filter changes reuse the last result.
# Cleared by any write request (see main.py). Background work can land after that, so the time limit bounds the staleness.
_cache: dict[str, tuple[float, Computed]] = {}


def clear_cache() -> None:
    _cache.clear()


def compute_home(db: Session, actor: Actor) -> Computed:
    ttl = get_settings().home_cache_seconds
    hit = _cache.get(actor.label)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    computed = _compute(db, actor)
    if ttl > 0:
        _cache[actor.label] = (time.monotonic(), computed)
    return computed


def _compute(db: Session, actor: Actor) -> Computed:
    from app.cases import exceptions  # imported here because exceptions uses this module too

    as_of = repository.get_as_of(db)
    records = repository.list_cases_for_actor(db, actor=actor.label, role=actor.role, term=None, as_of=as_of)
    ids = [r.case_id for r in records]
    if not ids:
        return Computed(as_of=as_of, rows=[], deadlines=[], activity=[])
    rule = load_rule(db)
    priorities = {
        row.case_id: row.priority
        for row in db.execute(text("SELECT case_id, priority FROM cases WHERE case_id = ANY(:ids)"), {"ids": ids})
    }
    events = load_events(db, ids, rule)
    proposals = load_proposals(db, ids)
    conflicts = {r.case_id: _open_conflicts(db, r.case_id) for r in records}
    defects = {k: exceptions.top_document_item(v) for k, v in exceptions.document_items(db, records).items()}
    built = [
        build_row(r, priorities[r.case_id], events.get(r.case_id, []), proposals.get(r.case_id, []), rule, as_of,
                  conflicts[r.case_id], defects[r.case_id])
        for r in records
    ]  # fmt: skip
    if actor.role == ActorRole.LEGAL:
        _show_sent_conflicts(db, built, conflicts)
    rows = sort_rows(built)
    if actor.role == ActorRole.LEGAL:
        for row in rows:
            if row.reason.key in FACT_REASONS:
                row.next_action = "Resolve conflict"
    names = {r.case_id: r.name for r in rows}
    return Computed(as_of=as_of, rows=rows, deadlines=build_deadlines(rows), activity=load_activity(db, names))


def build_home(db: Session, actor: Actor, filters: Filters | None = None, page: int = 1, page_size: int = PAGE_SIZE) -> Home:
    computed = compute_home(db, actor)
    rows, filters = computed.rows, filters or Filters()
    shown = filter_rows(rows, filters, actor.label)
    kpi_rows = filter_rows(rows, filters, actor.label, "kpi")
    page_rows, served = paginate(shown, page, min(page_size, PAGE_SIZE))
    return Home(
        as_of=computed.as_of, rows=page_rows, page=served, page_size=min(page_size, PAGE_SIZE), total=len(shown),
        assigned=len(rows), kpi_total=len(kpi_rows),
        kpi_counts={key: sum(matches_kpi(r, key) for r in kpi_rows) for key in KPI_KEYS},
        stages=build_options(rows, filter_rows(rows, filters, actor.label, "stage"), lambda r: (r.stage, r.stage)),
        reasons=[o.model_copy(update={"tone": REASONS[o.value][1]}) for o in build_options(rows, filter_rows(rows, filters, actor.label, "reason"), lambda r: (r.reason.key, r.reason.label))],
        deadlines=computed.deadlines, activity=computed.activity,
    )  # fmt: skip
