"""Document status rules in the order of HANDOFF 4.1. Pure functions, first failing check wins.

Rule values come from the document_rules rule set through the RuleContext, never from this file.
The file gates come first, then the value checks and the cross check on what the AI returned, then the content rules.
A value read from a page image is skipped here. It can only lead to NEEDS_HUMAN_REVIEW.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from app.core.contracts import DocumentRead, UploadOutcome
from app.validation import crosscheck, values
from app.validation.context import RuleContext
from app.validation.reasons import MESSAGES, Finding, Reason, us_date
from app.validation.values import IMAGE, MISSING, OK, UNVERIFIED, field_value  # noqa: F401

UNKNOWN_CATEGORIES = ("UNKNOWN", "REVIEW_REQUIRED")
# Calls and messages. Their values are claims, so they never count as evidence for a required category.
COMM_CATEGORIES = ("ZOOM_NOTES", "WHATSAPP_CHAT", "EMAIL_MESSAGE")
SCANNED_REASON = MESSAGES[Reason.SCANNED_PAGE]


@dataclass(frozen=True)
class Verdict:
    outcome: UploadOutcome
    code: str
    reason: str


@dataclass
class Facts:
    """Everything the rules look at for one upload."""

    rules: RuleContext
    client_name: str
    reads: list[DocumentRead]
    problem: Verdict | None = None
    duplicate_of: str | None = None
    foreign_pages: list[int] = field(default_factory=list)
    all_foreign: bool = False
    superseded: bool = False
    docref: str | None = None
    case_docrefs: frozenset[str] = frozenset()
    translations_of: frozenset[str] = frozenset()
    # The client name when the case has one, else empty. Page labels are the Label: value lines of each text page.
    known_name: str = ""
    # Every name on file for the case, so a document is held back only when it matches none of them.
    known_names: tuple[str, ...] = ()
    page_labels: Mapping[int, Mapping[str, str]] = field(default_factory=dict)
    # Says whether two names are one person written differently. The default lets only case and spacing differ.
    same_name: Callable[[str, str], bool] = values._same_by_key


def _verdict(outcome: UploadOutcome, code: Reason, reason: str | None = None) -> Verdict:
    return Verdict(outcome, code.value, reason or MESSAGES[code])


def _review(code: Reason, reason: str | None = None) -> Verdict:
    return _verdict(UploadOutcome.NEEDS_HUMAN_REVIEW, code, reason)


def _invalid(code: Reason, reason: str | None = None) -> Verdict:
    return _verdict(UploadOutcome.INVALID, code, reason)


def from_finding(found: Finding | None) -> Verdict | None:
    """A failed value or cross check sends the upload to Human review with its reason code."""
    return _review(found.code, found.message) if found else None


def _checked(read: DocumentRead, key: str, label: str) -> tuple[str | None, Verdict | None]:
    """The value to test, or a verdict when it is missing or unverified. Image values give neither."""
    value, state = field_value(read, key)
    if state == MISSING:
        return None, _review(Reason.MISSING_FIELD, f"{label} could not be read")
    if state == UNVERIFIED:
        return None, _review(Reason.UNVERIFIED_VALUE, f"{label} was not found in the document text")
    return (value if state == OK else None), None


def _unreadable(f: Facts) -> Verdict | None:
    return f.problem


def _duplicate(f: Facts) -> Verdict | None:
    if f.duplicate_of:
        return _verdict(UploadOutcome.DUPLICATE, Reason.DUPLICATE, f"Same file as {f.duplicate_of}")
    return None


def _wrong_client(f: Facts) -> Verdict | None:
    if f.all_foreign:
        return _verdict(UploadOutcome.QUARANTINED, Reason.WRONG_CLIENT)
    if f.foreign_pages:
        pages = ", ".join(str(p) for p in f.foreign_pages)
        return _verdict(UploadOutcome.QUARANTINED, Reason.MIXED_CLIENTS, f"Pages {pages} belong to another client")
    return None


def _superseded(f: Facts) -> Verdict | None:
    if f.superseded:
        return _verdict(UploadOutcome.SUPERSEDED, Reason.SUPERSEDED)
    return None


def _ai_review(f: Facts) -> Verdict | None:
    for read in f.reads:
        if read.category in UNKNOWN_CATEGORIES or read.status.value == "REVIEW_REQUIRED" or not read.legible:
            return _review(Reason.UNREADABLE if not read.legible else Reason.UNCLASSIFIED)
    return None


def _owner_mismatch(f: Facts) -> Verdict | None:
    if not values.name_key(f.client_name):
        return None
    for read in f.reads:
        for name in read.image_owner_names:
            if not any(f.same_name(name, k) for k in (f.known_names or (f.client_name,))):
                return _review(Reason.OWNER_MISMATCH)
    return None


def _values(f: Facts) -> Verdict | None:
    return from_finding(values.check_values(f.reads, f.rules, f.known_names or f.known_name, f.same_name))


def _cross(f: Facts) -> Verdict | None:
    return from_finding(crosscheck.check_cross(f.reads, f.page_labels))


def _passport(f: Facts, read: DocumentRead) -> Verdict | None:
    value, verdict = _checked(read, "PASSPORT.Expires", "The expiry date")
    expires = values.as_date(value)
    if verdict or expires is None:
        return verdict
    return _invalid(Reason.EXPIRED, "The passport expired before the review date") if expires < f.rules.as_of else None


def _letter(f: Facts, read: DocumentRead) -> Verdict | None:
    value, verdict = _checked(read, "EMPLOYER_LETTER.Signed On", "The signing date")
    signed = values.as_date(value)
    limit = f.rules.letter_not_before
    if verdict or signed is None or limit is None:
        return verdict
    return _invalid(Reason.STALE, f"The letter is dated before {us_date(limit)}") if signed < limit else None


def _pay(f: Facts, read: DocumentRead) -> Verdict | None:
    value, verdict = _checked(read, "PAY_STATEMENT.Pay Period", "The pay period")
    if verdict or value is None or not f.rules.pay_periods:
        return verdict
    if value not in f.rules.pay_periods.values():
        return _review(Reason.PAY_PERIOD)
    return None


def _notice(f: Facts, read: DocumentRead) -> Verdict | None:
    _, state = field_value(read, "PRIOR_NOTICE.Reference Number")
    if state == MISSING:
        return _review(Reason.NO_REFERENCE)
    return _review(Reason.UNVERIFIED_VALUE, "The reference number was not found in the document text") if state == UNVERIFIED else None


def _languages(read: DocumentRead) -> list[str]:
    """The language the letter says it is in and the language the reader found in its text. The wording of a document is not
    trusted on its own, so both count: a letter that says EN but reads as another language still needs a translation."""
    value, state = field_value(read, "EMPLOYER_LETTER.Document Language")
    stated = value.lower() if state == OK and value else ""
    return [lang for lang in (stated, (read.language or "").lower()) if lang] or ["en"]


def _translation(f: Facts, read: DocumentRead) -> Verdict | None:
    if all(lang.startswith("en") for lang in _languages(read)):
        return None
    if f.docref and f.docref in f.translations_of:
        return None
    return _invalid(Reason.NEEDS_TRANSLATION)


def _orphan(f: Facts, read: DocumentRead) -> Verdict | None:
    value, verdict = _checked(read, "CERTIFIED_TRANSLATION.Translation Of", "The translated document reference")
    if verdict or value is None:
        return verdict
    return None if value in f.case_docrefs else _review(Reason.ORPHAN_TRANSLATION)


# Rules 5 to 10 of HANDOFF 4.1, each for the category it applies to.
_PER_READ: tuple[tuple[str, Callable[[Facts, DocumentRead], Verdict | None]], ...] = (
    ("PASSPORT", _passport),
    ("EMPLOYER_LETTER", _letter),
    ("PAY_STATEMENT", _pay),
    ("PRIOR_NOTICE", _notice),
    ("EMPLOYER_LETTER", _translation),
    ("CERTIFIED_TRANSLATION", _orphan),
)


def _scanned(f: Facts) -> Verdict | None:
    if any(r.image_pages or any(x.from_image for x in r.fields.values()) for r in f.reads):
        return _review(Reason.SCANNED_PAGE)
    return None


def decide(f: Facts) -> Verdict:
    """The first failing check wins. Passing all checks is USABLE."""
    for check in (_unreadable, _duplicate, _wrong_client, _superseded, _ai_review, _owner_mismatch, _values, _cross):
        if verdict := check(f):
            return verdict
    if any(r.category in COMM_CATEGORIES for r in f.reads):
        return _verdict(UploadOutcome.CLAIM_SOURCE, Reason.CLAIM_SOURCE)
    for category, rule in _PER_READ:
        for read in (r for r in f.reads if r.category == category):
            if verdict := rule(f, read):
                return verdict
    return _scanned(f) or _verdict(UploadOutcome.USABLE, Reason.OK)
