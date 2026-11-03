"""Deterministic comparisons for the investigation agent. Every function calls the validation layer.

A name similarity label only informs a person. It never resolves a conflict.
"""

from datetime import date
from difflib import SequenceMatcher
from typing import Any

from app.facts.normalize import compare_key
from app.validation import deadlines, values
from app.validation.reasons import MESSAGES, Reason, us_date

SAME, SIMILAR, DIFFERENT = "SAME", "SIMILAR", "DIFFERENT"
EQUAL, BEFORE, AFTER, UNREADABLE = "EQUAL", "BEFORE", "AFTER", "UNREADABLE"
SIMILAR_RATIO = 0.85
MAX_DAYS = 3650
NAME_NOTE = "A similarity label only informs a person. It does not resolve anything."


def _shown(value: date) -> dict[str, str]:
    return {"us": us_date(value), "iso": value.isoformat()}


def _bad_date(value: str, reason: Reason) -> dict[str, Any]:
    return {"relation": UNREADABLE, "input": value, "reason_code": reason.value, "reason": MESSAGES[reason]}


def compare_dates(a: str, b: str) -> dict[str, Any]:
    left, left_reason = values.parse_date(a)
    right, right_reason = values.parse_date(b)
    if left is None or left_reason:
        return _bad_date(a, left_reason or Reason.INVALID_DATE)
    if right is None or right_reason:
        return _bad_date(b, right_reason or Reason.INVALID_DATE)
    relation = EQUAL if left == right else BEFORE if left < right else AFTER
    return {"relation": relation, "a": _shown(left), "b": _shown(right), "days_apart": abs((right - left).days)}


def add_days(start: str, days: int) -> dict[str, Any]:
    parsed, reason = values.parse_date(start)
    if parsed is None or reason:
        return _bad_date(start, reason or Reason.INVALID_DATE)
    if abs(days) > MAX_DAYS:
        return {"relation": UNREADABLE, "reason": f"Days must be between -{MAX_DAYS} and {MAX_DAYS}"}
    rule = deadlines.Rule(event_type="", source="", verified_required=False, offset_days=days)
    return {"start": _shown(parsed), "days": days, "result": _shown(deadlines.candidate_date({"event_date": parsed}, rule))}


def is_expired(value: str, as_of: date) -> dict[str, Any]:
    parsed, reason = values.parse_date(value)
    if parsed is None or reason:
        return _bad_date(value, reason or Reason.INVALID_DATE)
    left = deadlines.days_left(parsed, as_of)
    return {"date": _shown(parsed), "review_date": _shown(as_of), "expired": left < 0, "days_left": left}


def compare_names(a: str, b: str) -> dict[str, Any]:
    if values.name_key(a) == values.name_key(b):
        label = SAME
    else:
        ratio = SequenceMatcher(None, values.name_key(a), values.name_key(b)).ratio()
        label = SIMILAR if ratio >= SIMILAR_RATIO else DIFFERENT
    return {"label": label, "a": a, "b": b, "note": NAME_NOTE}


def compare_values(a: str, b: str) -> dict[str, Any]:
    left, right = values.parse_date(a)[0], values.parse_date(b)[0]
    if left is not None and right is not None:
        return {"relation": EQUAL if left == right else DIFFERENT, "kind": "date", "a": _shown(left), "b": _shown(right)}
    return {"relation": EQUAL if compare_key(a) == compare_key(b) else DIFFERENT, "kind": "text", "a": a, "b": b}
