"""Value validators for everything the AI returns. A failed check is a finding, never a silent fix.

Only a value that was read from page text and verified is checked. A value read from a scanned page image is
skipped here and can only lead to a person looking at it. The review date is passed in, never read from the clock.
"""

import re
from collections.abc import Callable, Sequence
from datetime import date

from app.core.contracts import DocumentRead, ReadField
from app.facts import normalize
from app.validation.context import RuleContext
from app.validation.reasons import Finding, Reason, finding, us_date

OK, MISSING, UNVERIFIED, IMAGE = "ok", "missing", "unverified", "image"

_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_US = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_US_SHORT = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2})")
# The end of a field key, lower case, mapped to what the date means.
DATE_ROLES = {
    "date of birth": "birth", "expires": "expiry", "employment start": "start", "last recorded entry": "entry",
    "last entry": "entry", "signed on": "signed",
}


def field_value(read: DocumentRead, key: str) -> tuple[str | None, str]:
    """The value of a field and its state: ok, missing, unverified or image."""
    item: ReadField | None = read.fields.get(key)
    if item is None or not (item.value or "").strip():
        return None, MISSING
    if item.from_image:
        return item.value, IMAGE
    return item.value, OK if item.verified else UNVERIFIED


def suffix(key: str) -> str:
    """CATEGORY.Date of Birth becomes date of birth."""
    return key.split(".", 1)[-1].strip().lower()


def name_key(value: str) -> str:
    """Comparison key for names. It ignores case and extra spaces only."""
    return " ".join(value.lower().split())


def parse_date(value: str | None) -> tuple[date | None, Reason | None]:
    """ISO and US MM/DD/YYYY dates. A date that does not exist is invalid and a two digit year is ambiguous."""
    text = (value or "").strip()
    try:
        if m := _ISO.fullmatch(text):
            return date(int(m[1]), int(m[2]), int(m[3])), None
        if m := _US.fullmatch(text):
            return date(int(m[3]), int(m[1]), int(m[2])), None
    except ValueError:
        return None, Reason.INVALID_DATE
    if _US_SHORT.fullmatch(text):
        return None, Reason.AMBIGUOUS_DATE
    # A date written in words, with dots or year first reads one way only. Turn it into a date instead of refusing it.
    if (written := normalize.parse_date(text)) is not None:
        return written, None
    return None, Reason.INVALID_DATE


def as_date(value: str | None) -> date | None:
    return parse_date(value)[0]


def _checked_fields(read: DocumentRead) -> list[tuple[str, str]]:
    """Key and value of every field read from page text and found in it."""
    pairs = [(k, *field_value(read, k)) for k in read.fields]
    return [(k, v) for k, v, state in pairs if state == OK and v]


def _label(key: str) -> str:
    return suffix(key).capitalize()


def _parsed_dates(read: DocumentRead) -> tuple[dict[str, date], Finding | None]:
    """Dates by role. The first date that does not parse is returned as a finding."""
    found: dict[str, date] = {}
    for key, value in _checked_fields(read):
        role = DATE_ROLES.get(suffix(key))
        if role is None:
            continue
        parsed, reason = parse_date(value)
        if reason is not None:
            return found, finding(reason, f"{_label(key)} {value} {'is ambiguous' if reason == Reason.AMBIGUOUS_DATE else 'is not a real date'}")
        if parsed is not None:
            found[role] = parsed
    return found, None


def _plausible(dates: dict[str, date], as_of: date) -> Finding | None:
    birth, expiry = dates.get("birth"), dates.get("expiry")
    if birth is not None and birth >= as_of:
        return finding(Reason.BIRTH_NOT_PAST, f"The date of birth {us_date(birth)} is not before the review date {us_date(as_of)}")
    if birth is not None and expiry is not None and expiry <= birth:
        return finding(Reason.EXPIRY_BEFORE_BIRTH, f"The passport expiry {us_date(expiry)} is not after the date of birth {us_date(birth)}")
    if (start := dates.get("start")) is not None and start > as_of:
        return finding(Reason.START_IN_FUTURE, f"The employment start {us_date(start)} is after the review date {us_date(as_of)}")
    if (entry := dates.get("entry")) is not None and entry > as_of:
        return finding(Reason.ENTRY_IN_FUTURE, f"The last entry date {us_date(entry)} is after the review date {us_date(as_of)}")
    return None


def _reference(read: DocumentRead, ctx: RuleContext) -> Finding | None:
    for key, value in _checked_fields(read):
        pattern = ctx.reference_patterns.get(key)
        if pattern and not re.fullmatch(pattern, value.strip()):
            return finding(Reason.BAD_REFERENCE, f"{_label(key)} {value} does not match the pattern in the rules")
    return None


def applicant_names(reads: list[DocumentRead]) -> list[str]:
    """Every applicant name read from page text, from the Applicant fields and the per page rows."""
    names: list[str] = []
    for read in reads:
        names += [v.strip() for k, v in _checked_fields(read) if suffix(k) == "applicant"]
        for item in read.fields.get("PASSPORT.Page Applicants", ReadField()).items or []:
            if item.verified and not item.from_image and (item.values.get("Applicant") or "").strip():
                names.append((item.values["Applicant"] or "").strip())
    return names


def _same_by_key(a: str, b: str) -> bool:
    return name_key(a) == name_key(b)


def check_names(reads: list[DocumentRead], known_name: str | Sequence[str],
                same: Callable[[str, str], bool] = _same_by_key) -> Finding | None:  # fmt: skip
    """One name across the pages of a document, then a name the case already has. known_name is the client name or every name
    on file for the case. A document of this case matches at least one of them, so it is the right case even while the
    spelling of the client is still undecided. same says whether two names are one person written differently."""
    known = [known_name] if isinstance(known_name, str) else list(known_name)
    known = [k for k in known if k]
    names = applicant_names(reads)
    first = next(iter(names), None)
    other = next((n for n in names if first and not same(n, first)), None)
    if first and other:
        return finding(Reason.NAME_INCONSISTENT, f"The applicant is {first} on one page and {other} on another")
    wrong = next((n for n in names if known and not any(same(n, k) for k in known)), None)
    if wrong:
        on_file = known[0] if len(known) == 1 else ", ".join(known)
        return finding(Reason.CLIENT_NAME_MISMATCH, f"The applicant on the document is {wrong} and the client of this case is {on_file}" if len(known) == 1
                       else f"The applicant on the document is {wrong}, which matches none of the names on file for this case: {on_file}")
    return None


def check_values(reads: list[DocumentRead], ctx: RuleContext, known_name: str | Sequence[str] = "",
                 same: Callable[[str, str], bool] = _same_by_key) -> Finding | None:  # fmt: skip
    """Date parsing, plausibility, reference pattern and names. The first failing check wins."""
    for read in reads:
        dates, bad = _parsed_dates(read)
        if bad or (bad := _plausible(dates, ctx.as_of)) or (bad := _reference(read, ctx)):
            return bad
    return check_names(reads, known_name, same)
