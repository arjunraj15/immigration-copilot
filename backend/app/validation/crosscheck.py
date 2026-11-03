"""Compare a clean Label: value line on a text page with the value the AI returned for the same field.

A disagreement is a finding and code never picks a side. A page image or a page without the label is skipped.
The page labels are parsed by the caller with the document loader, so no model call is made here.
"""

from collections.abc import Mapping

from app.core.contracts import DocumentRead
from app.validation.reasons import Finding, Reason, finding
from app.validation.values import DATE_ROLES, OK, field_value, parse_date, suffix


def _same(page_value: str, ai_value: str, is_date: bool) -> bool | None:
    """True or False when the two can be compared, None when a date is ambiguous or unreadable."""
    if is_date:
        left, right = parse_date(page_value)[0], parse_date(ai_value)[0]
        return None if left is None or right is None else left == right
    return " ".join(page_value.lower().split()) == " ".join(ai_value.lower().split())


def check_cross(reads: list[DocumentRead], page_labels: Mapping[int, Mapping[str, str]]) -> Finding | None:
    """page_labels holds the Label: value lines of each text page by page number, keys in lower case."""
    for read in reads:
        for key, item in read.fields.items():
            value, state = field_value(read, key)
            labels = page_labels.get(item.page)
            if state != OK or value is None or labels is None or suffix(key) not in labels:
                continue
            seen = labels[suffix(key)]
            if _same(seen, value, suffix(key) in DATE_ROLES) is False:
                return finding(Reason.VALUE_MISMATCH,
                               f"Page {item.page} shows {seen} for {suffix(key)} and the AI read {value}")  # fmt: skip
    return None
