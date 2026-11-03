"""Plain templates for client message drafts. Pure functions, no model and no database.

Every text starts with a visible DRAFT line and ends with a line that says it was not sent. Nothing here predicts
an outcome, gives legal advice, invents a date or names anyone but the client of the case."""

from dataclasses import dataclass
from datetime import date

DRAFT_LINE = "DRAFT, NOT SENT"
NOT_SENT_LINE = "This message is a draft. It has not been sent to the client."

# Plain reasons for a document that cannot be used. Anything else gets the last sentence.
UNUSABLE = {
    "UNREADABLE": "the file could not be read clearly, please send a clearer copy",
    "BLANK": "a page is blank, please send a complete copy",
    "ROTATED": "a page is rotated, please send an upright copy",
    "SCANNED_PAGE": "a scanned page needs a clearer copy",
    "EXPIRED": "the document has expired, please send a current one",
    "STALE": "the letter is older than we can accept, please send a recent one",
    "SUPERSEDED": "we need the most recent version",
    "NEEDS_TRANSLATION": "a certified English translation is needed",
    "PAY_PERIOD": "it does not cover the pay period we need",
    "NO_REFERENCE": "it does not show a reference number",
    "WRONG_CLIENT": "it does not appear to belong to your case, please send your own copy",
    "MIXED_CLIENTS": "it does not appear to belong to your case, please send your own copy",
    "OWNER_MISMATCH": "it does not appear to belong to your case, please send your own copy",
}
UNUSABLE_DEFAULT = "our team needs to check it and may ask you for a new copy"
NOT_RECEIVED = "we have not received it yet"


@dataclass(frozen=True)
class Portal:
    """The newest verified status snapshot from the mock portal."""

    event_id: str
    status: str
    recorded: date


@dataclass(frozen=True)
class Gap:
    """A required document that is missing or cannot be used."""

    label: str
    reason: str


@dataclass(frozen=True)
class Drafted:
    subject: str | None
    body: str


def us_date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def unusable_reason(codes: list[str | None]) -> str:
    found = sorted({UNUSABLE.get(code or "", UNUSABLE_DEFAULT) for code in codes})
    return " and ".join(found) if found else UNUSABLE_DEFAULT


def _hello(case_id: str, name: str | None) -> str:
    """The client's first name when the case has a name. A case that only has its id gets a plain hello."""
    first = (name or "").split()[0] if name and name != case_id else ""
    return f"Hello {first}," if first else "Hello,"


def _wrap(case_id: str, name: str | None, paragraphs: list[str]) -> str:
    return "\n\n".join([DRAFT_LINE, _hello(case_id, name), *paragraphs, f"Case reference: {case_id}", NOT_SENT_LINE])


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def _portal_line(portal: Portal | None, as_of: date) -> str:
    if portal is None:
        return "We do not have a verified portal status on file for your case yet."
    return (f"As of {us_date(as_of)}, the latest portal status on file for your case is {portal.status}. "
            f"It was recorded on {us_date(portal.recorded)}.")  # fmt: skip


def _gap_lines(gaps: list[Gap]) -> str:
    return "We still need the following from you:\n" + _bullets([f"{g.label}: {g.reason}" for g in gaps])


def _checking(gaps: list[Gap], unread: bool) -> str:
    """The checklist paragraph. A file that is not read yet is never called missing."""
    parts = [_gap_lines(gaps)] if gaps else []
    if unread:
        parts.append("We are still checking some of the files you sent.")
    return "\n\n".join(parts) or "Our checklist shows every required document as received."


def status_reply(case_id: str, name: str | None, portal: Portal | None, gaps: list[Gap], as_of: date, unread: bool = False) -> Drafted:
    """Status from the verified portal snapshot, then the documents that are missing or unusable."""
    checklist = _checking(gaps, unread)
    body = _wrap(case_id, name, [
        "Thank you for your message.",
        _portal_line(portal, as_of),
        checklist,
        "Your attorney will follow up if anything else is needed.",
    ])  # fmt: skip
    return Drafted(None, body)


def refusal_reply(case_id: str, name: str | None, portal: Portal | None, as_of: date) -> Drafted:
    """For a question about an outcome or legal advice, or one the records cannot answer."""
    body = _wrap(case_id, name, [
        "Thank you for your message.",
        "We cannot predict outcomes or give legal advice in a message.",
        _portal_line(portal, as_of),
        "Your attorney will follow up with you directly.",
    ])  # fmt: skip
    return Drafted(None, body)


def unsupported_reply(case_id: str, name: str | None, portal: Portal | None, as_of: date) -> Drafted:
    body = _wrap(case_id, name, [
        "Thank you for your message.",
        "We do not have the information to answer that question in a message.",
        _portal_line(portal, as_of),
        "Your attorney will follow up with you directly.",
    ])  # fmt: skip
    return Drafted(None, body)


def other_client_reply(case_id: str, name: str | None) -> Drafted:
    """Generic. It never names anyone and shares nothing about any other person."""
    body = _wrap(case_id, name, [
        "Thank you for your message.",
        "We can only discuss your own case in a message. We cannot share information about anyone else.",
        "Your attorney will follow up with you directly if you have questions about your own case.",
    ])  # fmt: skip
    return Drafted(None, body)


def ask_text(label: str, state: str, documents: list[str], has_profile: bool = False) -> str:
    """What the firm needs for one field, in plain words. It never repeats what a source says."""
    docs = " or ".join(documents[:2]) or "a document"
    if state == "CONFLICT":
        where = f", exactly as it appears on your {docs}" if documents else ""
        return f"Your {label}: we have different values on file. Please confirm the correct {label}{where}."
    if state == "UNVERIFIED" and has_profile:
        return f"Your {label}: we have this on file from earlier, but a document is needed to confirm it. Please send your {docs}."
    if state == "UNVERIFIED":
        return f"Your {label}: we only have this from a call or a message. Please send your {docs} so we can confirm it."
    return f"Your {label}: we do not have this on file. Please send your {docs} that shows it."


def missing_fields_email(case_id: str, name: str | None, asks: list[str], gaps: list[Gap], unread: bool = False) -> Drafted:
    """One email that lists what the firm needs from the client and why."""
    parts = ["To keep your case moving, we need a few things from you."]
    if asks:
        parts.append("Details to confirm:\n" + _bullets(asks))
    if gaps:
        parts.append("Documents to send:\n" + _bullets([f"{g.label}: {g.reason}" for g in gaps]))
    if unread:
        parts.append("We are still checking some of the files you sent, so this list may change.")
    parts.append("Please reply with the details or upload the documents to your secure folder. Your attorney will review what you send.")
    return Drafted(f"Information we need for case {case_id}", _wrap(case_id, name, parts))
