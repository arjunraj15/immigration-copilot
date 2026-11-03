"""Pure functions for the case queue, header and timeline. No database access, so each rule is unit tested."""

import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from app.cases.repository import CaseRecord
from app.core.audit_display import describe
from app.core.contracts import ActorRole, AuditAction, AuditOutcome
from app.validation.deadlines import SOURCE_PORTAL, is_evidence_event, unverified_status_events  # noqa: F401

if TYPE_CHECKING:
    from app.cases.communications import Communication
    from app.core.audit import AuditEntry
    from app.validation.deadlines import Due

Tone = Literal["ok", "bad", "warn", "ai", "muted", "info"]
PARALEGAL_STEP_COUNT = 6

# role -> ordered groups of (key, title, workflow statuses). Empty groups are not shown.
GROUPS: dict[ActorRole, list[tuple[str, str, tuple[str, ...]]]] = {
    ActorRole.OPS: [
        ("approved", "Approved, ready to apply", ("APPROVED",)),
        ("working", "Working on now", ("ANALYSING", "IN_PROGRESS")),
        ("sent_back", "Sent back to you", ("INFO_REQUESTED", "REJECTED")),
        ("new", "New, not started", ("NEW",)),
        ("with_attorney", "With attorney", ("WITH_ATTORNEY",)),
        ("finished", "Finished", ("APPLIED",)),
    ],
    ActorRole.LEGAL: [
        ("waiting", "Waiting for your decision", ("WITH_ATTORNEY",)),
        ("decided", "Decided this week", ("APPROVED", "REJECTED", "APPLIED", "INFO_REQUESTED")),
    ],
}


class QueueItem(BaseModel):
    case_id: str
    initials: str
    name: str
    number: str
    note: str
    tone: Tone


class QueueGroup(BaseModel):
    key: str
    title: str
    items: list[QueueItem]


class TimelineItem(BaseModel):
    date: date
    lane: Literal["portal", "calendar", "communication", "activity", "today"]
    kind: Literal["verified", "unverified", "proposed", "wrong", "claim", "activity", "refused", "today"]
    title: str
    note: str = ""
    ref: str | None = None
    why: str = ""
    manual: bool = False  # typed in through the demo form, so it can be removed


def case_number(case_id: str) -> str:
    return case_id.rsplit("-", 1)[-1]


def initials(name: str) -> str:
    return "".join(word[0] for word in name.split()[:2]).upper() or "?"


def humanize(code: str) -> str:
    """SYNTH_WORK_STATUS_RENEWAL becomes Work status renewal. MOCK_ and SYNTH_ prefixes are dropped."""
    words = re.sub(r"^(MOCK|SYNTH)_", "", code).replace("_", " ").lower().strip()
    return words[:1].upper() + words[1:]


def portal_status_label(details: str) -> str | None:
    """Reads 'Mock portal status: Processing; no estimate' as Processing. None when the text has another shape."""
    match = re.search(r"status:\s*([^;.]+)", details, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def short_date(value: datetime | date) -> str:
    return f"{value.day} {value.strftime('%b')}"


def group_key(role: ActorRole, record: CaseRecord) -> str | None:
    for key, _, statuses in GROUPS[role]:
        if record.status not in statuses:
            continue
        if key == "decided" and not record.decided_recently:
            return None
        return key
    return None


def queue_note(role: ActorRole, record: CaseRecord) -> tuple[str, Tone]:
    """One line under the name in the queue. The wording lives here so the UI only shows it."""
    status = record.status
    if role == ActorRole.LEGAL:
        notes: dict[str, tuple[str, Tone]] = {
            "WITH_ATTORNEY": (f"Prepared by {record.assigned_ops_user}", "info"),
            "APPROVED": ("Approved", "ok"),
            "REJECTED": ("Rejected", "bad"),
            "APPLIED": ("Applied", "ok"),
            "INFO_REQUESTED": ("Sent back for more information", "warn"),
        }
        return notes.get(status, (status.title(), "muted"))
    if status == "NEW":
        when = f", {short_date(record.last_upload_at)}" if record.last_upload_at else ""
        return f"Uploaded {record.upload_count} files{when}", "muted"
    notes = {
        "ANALYSING": ("Reading documents", "info"),
        "IN_PROGRESS": (f"Step {record.wizard_step + 1} of {PARALEGAL_STEP_COUNT}", "info"),
        "WITH_ATTORNEY": (f"Waiting for {record.assigned_legal_reviewer}", "info"),
        "INFO_REQUESTED": ("Attorney asked for more information", "warn"),
        "APPROVED": ("Approved, ready to apply", "ok"),
        "REJECTED": ("Attorney rejected, needs rework", "bad"),
        "APPLIED": ("Applied", "ok"),
    }
    return notes.get(status, (status.title(), "muted"))


def build_queue(role: ActorRole, records: list[CaseRecord]) -> list[QueueGroup]:
    items: dict[str, list[QueueItem]] = {key: [] for key, _, _ in GROUPS[role]}
    for record in records:
        key = group_key(role, record)
        if key is None:
            continue
        note, tone = queue_note(role, record)
        items[key].append(
            QueueItem(
                case_id=record.case_id, initials=initials(record.display_name), name=record.display_name,
                number=case_number(record.case_id), note=note, tone=tone,
            )  # fmt: skip
        )
    return [QueueGroup(key=key, title=title, items=items[key]) for key, title, _ in GROUPS[role] if items[key]]


WHY_VERIFIED = "Verified portal event, so it counts as evidence."
WHY_UNVERIFIED_PORTAL = "Portal event that is not verified, so it is a claim and not evidence."
WHY_CALENDAR = "Office calendar entry typed by hand. It is a claim and cannot set a deadline."
WHY_WRONG = "Typed by hand and does not match the date the portal evidence gives. Marked wrong."
WHY_STATUS = "Calendar note that says APPROVED. It is an unverified status and never changes the portal status."
WHY_COMMUNICATION = "Call note or message. It is a claim and never evidence, so it cannot set a deadline."
NOTE_LIMIT = 160
CHANNEL = {"ZOOM": "Zoom", "WHATSAPP": "WhatsApp", "EMAIL": "Email"}
# Ledger lines left off the Case activity lane. They are housekeeping or one line per file read, and the
# Activity tab still shows them.
HIDDEN_ACTIVITY = frozenset({
    AuditAction.DOCUMENT_READ, AuditAction.FACT_WRITTEN, AuditAction.CASE_ACCESS, AuditAction.CHAIN_VERIFIED,
    AuditAction.CHAT_QUESTION, AuditAction.PROMPT_VERSION_CREATED, AuditAction.PROMPT_VERSION_ACTIVATED,
    AuditAction.SEED_LOADED,
})  # fmt: skip
ACTIVITY_ACTIONS = tuple(action for action in AuditAction if action not in HIDDEN_ACTIVITY)
STAFF_ROLES = {ActorRole.OPS: "operations", ActorRole.LEGAL: "legal"}


def _why(event: dict[str, Any], wrong: bool) -> str:
    if wrong:
        return WHY_WRONG
    if unverified_status_events([event]):
        return WHY_STATUS
    if is_evidence_event(event):
        return WHY_VERIFIED
    return WHY_UNVERIFIED_PORTAL if event["event_source"] == SOURCE_PORTAL else WHY_CALENDAR


def _event_item(event: dict[str, Any], wrong_ref: str | None) -> TimelineItem:
    wrong = event["event_id"] == wrong_ref
    kind: Literal["verified", "unverified", "wrong"] = (
        "wrong" if wrong else "verified" if is_evidence_event(event) else "unverified"
    )
    return TimelineItem(
        date=event["event_date"], lane="portal" if event["event_source"] == SOURCE_PORTAL else "calendar",
        kind=kind, title=humanize(event["event_type"]), note=event["details"], ref=event["event_id"],
        why=_why(event, wrong), manual=event.get("import_batch") == "DEMO-MANUAL",
    )  # fmt: skip


def _proposed_item(due: "Due") -> TimelineItem:
    return TimelineItem(
        date=due.date, lane="portal", kind="proposed", title="Evidence deadline (proposed)",
        note=f"{due.request_date.strftime('%b')} {due.request_date.day} plus {due.offset_days} calendar days. Waiting for a legal decision.",
        ref=due.request_event_id,
        why=f"Worked out by code from verified portal event {due.request_event_id} and the firm rule. Not final until a lawyer approves.",
    )  # fmt: skip


def _communication_title(comm: "Communication") -> str:
    if comm.role == "INTAKE_CALL":
        return "Zoom intake call"
    if comm.kind == "ZOOM":
        return "Zoom call note"
    channel = CHANNEL.get(comm.kind, humanize(comm.kind))
    return f"{channel} from the office, not sent" if comm.is_draft else f"{channel} from the client"


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= NOTE_LIMIT else text[:NOTE_LIMIT].rstrip() + "..."


def communication_items(comms: "list[Communication]") -> list[TimelineItem]:
    """Logged Zoom notes and messages as claims on their own lane. A reply drafted in this app is work in
    progress and stays off the timeline. The kit's office emails are logged drafts and are shown as not sent."""
    return [
        TimelineItem(
            date=datetime.fromisoformat(comm.occurred_at).date(), lane="communication", kind="claim",
            title=_communication_title(comm), note=_short(comm.body or comm.subject or ""), ref=comm.source_id,
            why=WHY_COMMUNICATION,
        )  # fmt: skip
        for comm in comms
        if comm.draft_status is None
    ]


def activity_items(entries: "list[AuditEntry]") -> list[TimelineItem]:
    """What the operations and legal users did on the case, from the audit ledger in ledger order.
    The wording comes from the same helper as the Activity tab. A refused attempt is shown as refused."""
    items = []
    for entry in sorted(entries, key=lambda e: e.seq):
        if entry.actor_role not in STAFF_ROLES or entry.action in HIDDEN_ACTIVITY:
            continue
        shown = describe(entry)
        items.append(TimelineItem(
            date=entry.occurred_at.date(), lane="activity",
            kind="refused" if entry.outcome == AuditOutcome.DENIED else "activity",
            title=shown.title, note=shown.note if entry.target_type != "upload" else "",
            ref=entry.target_id if entry.target_type == "upload" else None,
            why=f"Done by {entry.actor}, {STAFF_ROLES[entry.actor_role]}. Recorded in the audit ledger.",
        ))  # fmt: skip
    return items


def build_timeline(
    events: list[dict[str, Any]],
    as_of: date,
    due: "Due | None" = None,
    extra: list[TimelineItem] | None = None,
) -> list[TimelineItem]:
    """Portal and calendar events in date order with a marker for the review date. Only verified portal
    events are evidence. Everything else is shown for comparison. When a due date was worked out from the
    rule, it is added as the proposed deadline and a calendar entry that disagrees is marked wrong.
    Extra items, such as calls, messages and case activity, are added in their own lanes."""
    wrong_ref = due.calendar_event_id if due else None
    items = [_event_item(event, wrong_ref) for event in events] + (extra or [])
    if due is not None:
        items.append(_proposed_item(due))
    items.sort(key=lambda item: item.date)
    today = TimelineItem(date=as_of, lane="today", kind="today", title="Today")
    at = next((index for index, item in enumerate(items) if item.date > as_of), len(items))
    return [*items[:at], today, *items[at:]]
