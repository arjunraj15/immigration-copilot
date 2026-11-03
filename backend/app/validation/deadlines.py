"""The deadline rules in one place. The candidate date, the calendar contradiction, days left and the state.

Pure functions. The rule offset and the required source come from the rule data and the review date is passed in.
Home, Exceptions, the timeline and the proposal check all call these functions.
"""

import re
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from app.validation.reasons import Finding, Reason, finding, us_date

SOURCE_PORTAL = "MOCK_PORTAL"
CALENDAR_DEADLINE = "CALENDAR_DEADLINE"
# A calendar note that says APPROVED is an unverified status. It never changes the portal status.
_UNVERIFIED_STATUS = re.compile(r"\bAPPROVED\b", re.IGNORECASE)

DueState = Literal["PROPOSED", "APPROVED", "CONFLICT", "OVERDUE"]


class Rule(BaseModel):
    event_type: str
    source: str
    verified_required: bool
    offset_days: int


class Due(BaseModel):
    date: date
    state: DueState
    days_left: int
    request_date: date
    request_event_id: str
    offset_days: int
    calendar_date: date | None
    calendar_event_id: str | None


def read_rule(body: dict[str, Any] | None, event_type: str | None = None) -> Rule | None:
    """The deadline trigger from the rule set. The offset and the required source are never hardcoded."""
    for trigger in (body or {}).get("triggers", []):
        if event_type is None or trigger.get("event_type") == event_type:
            return Rule(
                event_type=trigger["event_type"], source=trigger["source_required"],
                verified_required=bool(trigger.get("source_verified_required", True)),
                offset_days=int(trigger["offset_calendar_days"]),
            )  # fmt: skip
    return None


def is_evidence_event(event: dict[str, Any]) -> bool:
    """Only a verified portal event is evidence. Calendar entries and unverified events are claims."""
    return event["event_source"] == SOURCE_PORTAL and bool(event["source_verified"])


def request_event(events: list[dict[str, Any]], rule: Rule) -> dict[str, Any] | None:
    """The newest event that is allowed to start a deadline. Calendar entries and unverified events never are."""
    usable = [
        e for e in events
        if e["event_type"] == rule.event_type and e["event_source"] == rule.source
        and (e["source_verified"] or not rule.verified_required)
    ]  # fmt: skip
    return max(usable, key=lambda e: (e["event_date"], e["event_id"]), default=None)


def candidate_date(request: dict[str, Any], rule: Rule) -> date:
    """The request date plus the rule offset in calendar days. No weekend shift."""
    return request["event_date"] + timedelta(days=rule.offset_days)


def calendar_contradiction(events: list[dict[str, Any]], rule: Rule, due_date: date) -> dict[str, Any] | None:
    """The first calendar deadline, by event id, that is not from the portal and gives a different date."""
    return next(
        (e for e in sorted(events, key=lambda e: e["event_id"])
         if e["event_type"] == CALENDAR_DEADLINE and e["event_source"] != rule.source and e["event_date"] != due_date),
        None,
    )  # fmt: skip


def unverified_status_events(events: list[dict[str, Any]], rule: Rule | None = None) -> list[dict[str, Any]]:
    """Calendar entries that are not verified portal events and whose note says APPROVED."""
    source = rule.source if rule else SOURCE_PORTAL
    return [
        e for e in events
        if e["event_source"] != source and not e["source_verified"] and _UNVERIFIED_STATUS.search(e.get("details") or "")
    ]  # fmt: skip


def days_left(due_date: date, as_of: date) -> int:
    return (due_date - as_of).days


def due_state(approved: bool, left: int, contradicted: bool) -> DueState:
    """Overdue wins, then a calendar conflict. Otherwise approved or proposed."""
    if left < 0:
        return "OVERDUE"
    if contradicted:
        return "CONFLICT"
    return "APPROVED" if approved else "PROPOSED"


def build_due(events: list[dict[str, Any]], rule: Rule | None, approved: bool, as_of: date) -> Due | None:
    if rule is None:
        return None
    request = request_event(events, rule)
    if request is None:
        return None
    due_date = candidate_date(request, rule)
    calendar = calendar_contradiction(events, rule, due_date)
    left = days_left(due_date, as_of)
    return Due(
        date=due_date, state=due_state(approved, left, calendar is not None), days_left=left,
        request_date=request["event_date"], request_event_id=request["event_id"], offset_days=rule.offset_days,
        calendar_date=calendar["event_date"] if calendar else None,
        calendar_event_id=calendar["event_id"] if calendar else None,
    )  # fmt: skip


def check_proposed_value(value: dict[str, Any], due: Due | None) -> Finding | None:
    """A proposed deadline must equal the date and the trigger event that code worked out. Otherwise it is refused."""
    if due is None:
        return finding(Reason.NO_DEADLINE)
    if str(value.get("due_date")) != due.date.isoformat() or value.get("trigger_event_id") != due.request_event_id:
        return finding(Reason.DEADLINE_MISMATCH, f"The proposed deadline does not match {us_date(due.date)}, worked out from {due.request_event_id}")
    return None
