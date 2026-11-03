"""Reason codes with one plain message each. Shared by upload outcomes, the Exceptions page and the deadline screens.

A code that already existed keeps its name. A check that needs a detail in its text builds the message itself
and uses the table text as the plain default.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.core.dates import us


class Reason(StrEnum):
    OK = "OK"
    # File level
    UNREADABLE = "UNREADABLE"
    BLANK = "BLANK"
    ROTATED = "ROTATED"
    FILE_MISSING = "FILE_MISSING"
    UNCLASSIFIED = "UNCLASSIFIED"
    DUPLICATE = "DUPLICATE"
    WRONG_CLIENT = "WRONG_CLIENT"
    MIXED_CLIENTS = "MIXED_CLIENTS"
    SUPERSEDED = "SUPERSEDED"
    OWNER_MISMATCH = "OWNER_MISMATCH"
    # Document rules
    EXPIRED = "EXPIRED"
    STALE = "STALE"
    PAY_PERIOD = "PAY_PERIOD"
    NO_REFERENCE = "NO_REFERENCE"
    NEEDS_TRANSLATION = "NEEDS_TRANSLATION"
    ORPHAN_TRANSLATION = "ORPHAN_TRANSLATION"
    SCANNED_PAGE = "SCANNED_PAGE"
    CLAIM_SOURCE = "CLAIM_SOURCE"
    MISSING_FIELD = "MISSING_FIELD"
    UNVERIFIED_VALUE = "UNVERIFIED_VALUE"
    # Value checks and the cross check
    INVALID_DATE = "INVALID_DATE"
    AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
    BIRTH_NOT_PAST = "BIRTH_NOT_PAST"
    EXPIRY_BEFORE_BIRTH = "EXPIRY_BEFORE_BIRTH"
    START_IN_FUTURE = "START_IN_FUTURE"
    ENTRY_IN_FUTURE = "ENTRY_IN_FUTURE"
    BAD_REFERENCE = "BAD_REFERENCE"
    NAME_INCONSISTENT = "NAME_INCONSISTENT"
    CLIENT_NAME_MISMATCH = "CLIENT_NAME_MISMATCH"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    # Deadlines
    DEADLINE_CONFLICT = "DEADLINE_CONFLICT"
    OVERDUE = "OVERDUE"
    UNVERIFIED_STATUS = "UNVERIFIED_STATUS"
    DEADLINE_MISMATCH = "DEADLINE_MISMATCH"
    NO_DEADLINE = "NO_DEADLINE"


MESSAGES: dict[Reason, str] = {
    Reason.OK: "All document checks passed",
    Reason.UNREADABLE: "The type or content could not be confirmed",
    Reason.BLANK: "A page is blank",
    Reason.ROTATED: "A page is rotated and cannot be read upright",
    Reason.FILE_MISSING: "The stored file could not be found",
    Reason.UNCLASSIFIED: "The type or content could not be confirmed",
    Reason.DUPLICATE: "Same file as an earlier upload",
    Reason.WRONG_CLIENT: "This file belongs to another client",
    Reason.MIXED_CLIENTS: "Some pages belong to another client",
    Reason.SUPERSEDED: "A later version replaces this file",
    Reason.OWNER_MISMATCH: "The name on a scanned page does not match this client",
    Reason.EXPIRED: "The passport expired before the review date",
    Reason.STALE: "The letter is dated before the date the rules ask for",
    Reason.PAY_PERIOD: "The pay period is not one the rules ask for",
    Reason.NO_REFERENCE: "The notice has no reference number",
    Reason.NEEDS_TRANSLATION: "A certified English translation is needed",
    Reason.ORPHAN_TRANSLATION: "The translated document is not in this case",
    Reason.SCANNED_PAGE: "Read from a scanned page, a person must check it",
    Reason.CLAIM_SOURCE: "Read as a claim from a call or message, not as evidence",
    Reason.MISSING_FIELD: "A value could not be read",
    Reason.UNVERIFIED_VALUE: "A value was not found in the document text",
    Reason.INVALID_DATE: "A date is not a real date",
    Reason.AMBIGUOUS_DATE: "A date could be read two ways, a person must check it",
    Reason.BIRTH_NOT_PAST: "The date of birth is not before the review date",
    Reason.EXPIRY_BEFORE_BIRTH: "The passport expiry is not after the date of birth",
    Reason.START_IN_FUTURE: "The employment start is after the review date",
    Reason.ENTRY_IN_FUTURE: "The last entry date is after the review date",
    Reason.BAD_REFERENCE: "A reference number does not match the pattern in the rules",
    Reason.NAME_INCONSISTENT: "The applicant name differs between pages of this document",
    Reason.CLIENT_NAME_MISMATCH: "The applicant name does not match the client of this case",
    Reason.VALUE_MISMATCH: "The value read by the AI differs from the labeled line on the page",
    Reason.DEADLINE_CONFLICT: "A calendar entry has a different date than the portal evidence gives",
    Reason.OVERDUE: "The deadline has passed",
    Reason.UNVERIFIED_STATUS: "A calendar note claims a status that the portal does not confirm",
    Reason.DEADLINE_MISMATCH: "The proposed deadline differs from the date worked out by code",
    Reason.NO_DEADLINE: "No verified portal request exists, so no deadline can be proposed",
}


@dataclass(frozen=True)
class Finding:
    """A failed check. The code is a Reason value and the message is plain text for people."""

    code: Reason
    message: str


def finding(code: Reason, detail: str | None = None) -> Finding:
    """A finding with the table message, or with a message that carries the detail."""
    return Finding(code, detail or MESSAGES[code])


def us_date(value: date) -> str:
    """A US style date for messages, for example 10/23/2026."""
    return us(value)
