"""Read only date tools the model may call while it reads a document.

Every tool is pure and deterministic. None reads the database, the file system or the system clock, and none writes.
"Today" is the review date from the rules file, passed in when the toolbox is built.
Dates come back as {"us", "iso"} pairs, and a date that does not parse says why instead of guessing.
"""

import calendar
from collections.abc import Mapping
from datetime import date
from typing import Any

from app.investigate import compare
from app.validation import values
from app.validation.reasons import MESSAGES, Reason, us_date

_STR = {"type": "string"}
_DATE_NOTE = "Dates are written YYYY-MM-DD or MM/DD/YYYY."


def _spec(name: str, description: str, **props: dict[str, Any]) -> dict[str, Any]:
    schema = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    return {"name": name, "description": description, "input_schema": schema}


TOOL_SPECS: list[dict[str, Any]] = [
    _spec("get_today", "The review date, to use as today. Fixed by the case rules, not the system clock."),
    _spec("parse_date", f"One exact date from written text, or why it cannot be read. {_DATE_NOTE}", text=_STR),
    _spec("days_between", f"Days, and years, months and days, from start to end. {_DATE_NOTE}", start=_STR, end=_STR),
    _spec("date_in_range", f"Whether a date is inside a start and end window. Empty date means the review date. {_DATE_NOTE}",
          start=_STR, end=_STR, date=_STR),
    _spec("add_days", f"A date plus calendar days. {_DATE_NOTE}", start=_STR, days={"type": "integer"}),
]
ARGS = {s["name"]: set(s["input_schema"]["properties"]) for s in TOOL_SPECS}



def catalog() -> list[dict[str, str]]:
    """Name and one line description of every tool, for the AI page."""
    return [{"name": spec["name"], "description": spec["description"]} for spec in TOOL_SPECS]


def unknown_tools(names: list[str]) -> list[str]:
    return sorted({n for n in names if n not in ARGS})


def _shown(value: date) -> dict[str, str]:
    return {"us": us_date(value), "iso": value.isoformat(), "weekday": value.strftime("%A")}


def _parse(text: str) -> tuple[date | None, dict[str, Any] | None]:
    parsed, reason = values.parse_date(text)
    if parsed is not None and reason is None:
        return parsed, None
    reason = reason or Reason.INVALID_DATE
    return None, {"readable": False, "input": text, "reason_code": reason.value, "reason": MESSAGES[reason]}


def _span(start: date, end: date) -> dict[str, int]:
    """Whole years and months, then the leftover days, from start up to end. Both are in order."""
    months = (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day)
    stepped = _plus_months(start, months)
    return {"years": months // 12, "months": months % 12, "days": (end - stepped).days}


def _plus_months(start: date, months: int) -> date:
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))


class DocTools:
    def __init__(self, as_of: date, names: tuple[str, ...] = tuple(ARGS)) -> None:
        self._as_of = as_of
        self.specs = [spec for spec in TOOL_SPECS if spec["name"] in names]

    @classmethod
    def for_version(cls, version: Mapping[str, Any], as_of: date) -> "DocTools | None":
        """The toolbox this prompt version asks for, or None when it lists no tools."""
        names = tuple(version.get("tools") or ())
        return cls(as_of, names) if names else None

    def call(self, name: str, args: dict[str, Any]) -> tuple[Any, bool]:
        """The result and whether it is an error. A bad call returns a message the model can act on."""
        allowed = ARGS.get(name) if any(spec["name"] == name for spec in self.specs) else None
        if allowed is None or set(args) - allowed:
            return {"error": "Unknown tool or argument."}, True
        try:
            data = getattr(self, f"_{name}")(**args)
        except (TypeError, ValueError, OverflowError) as exc:
            return {"error": f"Bad arguments: {exc}"}, True
        return data, False

    def _get_today(self) -> dict[str, Any]:
        return {"today": _shown(self._as_of), "note": "Fixed review date, not the system clock."}

    def _parse_date(self, text: str) -> dict[str, Any]:
        parsed, bad = _parse(text)
        return bad or {"readable": True, "input": text, "date": _shown(parsed)}  # type: ignore[arg-type]

    def _days_between(self, start: str, end: str) -> dict[str, Any]:
        (left, bad), (right, bad2) = _parse(start), _parse(end)
        if bad or bad2 or left is None or right is None:
            return bad or bad2 or {}
        first, last = sorted((left, right))
        return {"start": _shown(left), "end": _shown(right), "days": (right - left).days, "span": _span(first, last),
                "note": "days is negative when end is before start"}  # fmt: skip

    def _date_in_range(self, start: str, end: str, date: str = "") -> dict[str, Any]:  # noqa: A002
        (left, bad), (right, bad2) = _parse(start), _parse(end)
        probe, bad3 = (self._as_of, None) if not date.strip() else _parse(date)
        if bad or bad2 or bad3 or left is None or right is None or probe is None:
            return bad or bad2 or bad3 or {}
        if right < left:
            return {"error": "The end date is before the start date."}
        where = "BEFORE_START" if probe < left else "AFTER_END" if probe > right else "INSIDE"
        return {"date": _shown(probe), "start": _shown(left), "end": _shown(right), "position": where, "inside": where == "INSIDE",
                "days_since_start": (probe - left).days, "days_until_end": (right - probe).days}  # fmt: skip

    def _add_days(self, start: str, days: int) -> dict[str, Any]:
        return compare.add_days(start, int(days))
