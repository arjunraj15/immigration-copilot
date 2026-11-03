"""The validation layer. Pure functions with fakes only, so no model, database or clock is involved."""

import re
import time
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

from app.core.contracts import DocumentRead, ReadField, ReadItem, UploadOutcome
from app.validation import crosscheck, deadlines, documents, values
from app.validation.context import build_context, parse_document_rules
from app.validation.reasons import MESSAGES, Reason

AS_OF = date(2026, 10, 23)
DOC_BODY = {
    "required_document_categories": [
        {"category": "EMPLOYER_LETTER", "tests": ["dated_not_before_2026-09-01"]},
        {"category": "PAY_AUG", "tests": ["pay_period=2026-08"]},
    ]
}
DEADLINE_BODY = {
    "triggers": [{"event_type": "REQ", "source_required": "PORTAL", "source_verified_required": True, "offset_calendar_days": 10}]
}
CTX = build_context(DOC_BODY, DEADLINE_BODY, AS_OF)
RULE = CTX.deadline


def make_read(category: str, **fields: str) -> DocumentRead:
    return DocumentRead(category=category, language="en",
                        fields={f"{category}.{k}": ReadField(value=v, page=1) for k, v in fields.items()})  # fmt: skip


def decide(*reads: DocumentRead, ctx=CTX, **facts) -> documents.Verdict:
    return documents.decide(documents.Facts(ctx, "Test Client", list(reads), **facts))


# ---------------------------------------------------------------- document rules and their boundaries


@pytest.mark.parametrize(
    ("read", "code"),
    [
        (make_read("PASSPORT", Expires="2026-10-23"), "OK"),
        (make_read("PASSPORT", Expires="2026-10-22"), "EXPIRED"),
        (make_read("EMPLOYER_LETTER", **{"Signed On": "2026-09-01"}), "OK"),
        (make_read("EMPLOYER_LETTER", **{"Signed On": "2026-08-31"}), "STALE"),
        (make_read("PAY_STATEMENT", **{"Pay Period": "2026-08"}), "OK"),
        (make_read("PAY_STATEMENT", **{"Pay Period": "2026-07"}), "PAY_PERIOD"),
        (make_read("PRIOR_NOTICE", **{"Applicant": "Test Client"}), "NO_REFERENCE"),
        (make_read("PASSPORT", Expires="10/22/2026"), "EXPIRED"),
    ],
)
def test_document_rules(read: DocumentRead, code: str) -> None:
    assert decide(read).code == code


def test_file_gates_win_over_value_checks() -> None:
    bad = make_read("PASSPORT", **{"Date of Birth": "2999-01-01"})
    assert decide(bad, duplicate_of="UP-1").code == "DUPLICATE"
    assert decide(bad).code == "BIRTH_NOT_PAST"


def test_failed_value_check_is_human_review_with_its_code() -> None:
    verdict = decide(make_read("PASSPORT", **{"Date of Birth": "02/30/1990"}))
    assert verdict.outcome == UploadOutcome.NEEDS_HUMAN_REVIEW and verdict.code == "INVALID_DATE"
    assert "02/30/1990" in verdict.reason


# ---------------------------------------------------------------- dates


@pytest.mark.parametrize(
    ("text", "parsed", "reason"),
    [
        ("2026-10-23", date(2026, 10, 23), None),
        ("10/23/2026", date(2026, 10, 23), None),
        (" 3/4/2026 ", date(2026, 3, 4), None),
        ("03/04/05", None, Reason.AMBIGUOUS_DATE),
        ("2026-02-30", None, Reason.INVALID_DATE),
        ("13/01/2026", None, Reason.INVALID_DATE),
        ("Oct 23 2026", date(2026, 10, 23), None),  # written in words, it reads one way only
        ("", None, Reason.INVALID_DATE),
    ],
)
def test_parse_date(text: str, parsed: date | None, reason: Reason | None) -> None:
    assert values.parse_date(text) == (parsed, reason)


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"Date of Birth": "2026-10-22"}, None),
        ({"Date of Birth": "2026-10-23"}, "BIRTH_NOT_PAST"),
        ({"Date of Birth": "1990-05-05", "Expires": "1990-05-05"}, "EXPIRY_BEFORE_BIRTH"),
        ({"Date of Birth": "1990-05-05", "Expires": "1990-05-06"}, None),
        ({"Date of Birth": "03/04/05"}, "AMBIGUOUS_DATE"),
    ],
)
def test_passport_plausibility(fields: dict, code: str | None) -> None:
    found = values.check_values([make_read("PASSPORT", **fields)], CTX)
    assert (found.code if found else None) == code


@pytest.mark.parametrize(
    ("key", "value", "code"),
    [
        ("EMPLOYER_LETTER.Employment start", "2026-10-23", None),
        ("EMPLOYER_LETTER.Employment start", "2026-10-24", "START_IN_FUTURE"),
        ("ARRIVAL_RECORD.Last Recorded Entry", "2026-10-23", None),
        ("ARRIVAL_RECORD.Last Recorded Entry", "2026-10-24", "ENTRY_IN_FUTURE"),
    ],
)
def test_future_dates(key: str, value: str, code: str | None) -> None:
    read = DocumentRead(category=key.split(".")[0], fields={key: ReadField(value=value, page=1)})
    found = values.check_values([read], CTX)
    assert (found.code if found else None) == code


def test_unverified_and_image_values_are_not_value_checked() -> None:
    read = DocumentRead(category="PASSPORT", fields={
        "PASSPORT.Date of Birth": ReadField(value="2999-01-01", verified=False),
        "PASSPORT.Expires": ReadField(value="2999-01-01", from_image=True)})  # fmt: skip
    assert values.check_values([read], CTX) is None


# ---------------------------------------------------------------- reference pattern


def test_reference_pattern_comes_from_the_rule_data_and_is_skipped_without_one() -> None:
    read = make_read("PRIOR_NOTICE", **{"Reference Number": "BAD 1"})
    assert values.check_values([read], CTX) is None
    ctx = parse_document_rules({"reference_patterns": {"PRIOR_NOTICE.Reference Number": r"[A-Z]+-RCPT-\d{5}"}}, AS_OF)
    assert values.check_values([read], ctx).code == "BAD_REFERENCE"
    assert values.check_values([make_read("PRIOR_NOTICE", **{"Reference Number": "SYN-RCPT-00007"})], ctx) is None


# ---------------------------------------------------------------- names


def test_name_must_match_across_pages_ignoring_case_and_spaces() -> None:
    same = make_read("PASSPORT", Applicant="Mira  Dhawan")
    same.fields["PASSPORT.Page Applicants"] = ReadField(items=[
        ReadItem(values={"Applicant": "mira dhawan"}, quote="q", page=1),
        ReadItem(values={"Applicant": "MIRA DHAWAN"}, quote="q", page=2)])  # fmt: skip
    assert values.check_names([same], "") is None
    same.fields["PASSPORT.Page Applicants"].items.append(ReadItem(values={"Applicant": "Mira Dhavan"}, quote="q", page=3))
    found = values.check_names([same], "")
    assert found.code == "NAME_INCONSISTENT" and "Mira Dhavan" in found.message and "Mira  Dhawan" in found.message


def test_applicant_is_compared_with_the_known_client_name() -> None:
    read = make_read("PASSPORT", Applicant="Other Person")
    found = values.check_names([read], "Test Client")
    assert found.code == "CLIENT_NAME_MISMATCH" and "Other Person" in found.message and "Test Client" in found.message
    assert values.check_names([read], "") is None
    assert values.check_names([make_read("PASSPORT", Applicant="test  CLIENT")], "Test Client") is None
    assert decide(read, known_name="Test Client").code == "CLIENT_NAME_MISMATCH"


# ---------------------------------------------------------------- cross check


def test_cross_check_agree_disagree_and_skipped() -> None:
    read = make_read("PASSPORT", Expires="2030-01-01", Applicant="Test Client")
    labels = {1: {"expires": "2030-01-01", "applicant": "test client"}}
    assert crosscheck.check_cross([read], labels) is None
    found = crosscheck.check_cross([read], {1: {"expires": "2031-01-01"}})
    assert found.code == "VALUE_MISMATCH" and "2031-01-01" in found.message and "2030-01-01" in found.message
    assert "Page 1" in found.message
    assert crosscheck.check_cross([read], {1: {"issued": "2031-01-01"}}) is None  # label not present
    assert crosscheck.check_cross([read], {}) is None  # the page is an image, so it has no labels
    assert crosscheck.check_cross([read], {1: {"expires": "01/01/30"}}) is None  # ambiguous page date


def test_cross_check_compares_us_dates_and_runs_in_decide() -> None:
    read = make_read("PASSPORT", Expires="2030-01-01")
    assert crosscheck.check_cross([read], {1: {"expires": "01/01/2030"}}) is None
    assert decide(read, page_labels={1: {"expires": "2031-01-01"}}).code == "VALUE_MISMATCH"
    image = DocumentRead(category="PASSPORT", fields={"PASSPORT.Expires": ReadField(value="2030-01-01", page=1, from_image=True)})
    assert crosscheck.check_cross([image], {1: {"expires": "2031-01-01"}}) is None


# ---------------------------------------------------------------- deadlines


def event(event_id: str, day: date, kind: str = "REQ", source: str = "PORTAL", verified: bool = True, details: str = "") -> dict:
    return {"event_id": event_id, "event_date": day, "event_type": kind, "event_source": source,
            "source_verified": verified, "details": details}  # fmt: skip


def test_candidate_is_newest_verified_portal_request_plus_rule_offset() -> None:
    events = [
        event("EV-1", date(2026, 10, 1)),
        event("EV-2", date(2026, 10, 14)),
        event("EV-3", date(2026, 10, 20), verified=False),
        event("CAL-1", date(2026, 10, 21), source="CALENDAR"),
        event("EV-4", date(2026, 10, 22), kind="OTHER"),
    ]
    due = deadlines.build_due(events, RULE, False, AS_OF)
    assert due.request_event_id == "EV-2" and due.date == date(2026, 10, 24) and due.offset_days == 10
    longer = build_context(None, {"triggers": [{**DEADLINE_BODY["triggers"][0], "offset_calendar_days": 30}]}, AS_OF)
    assert deadlines.build_due(events, longer.deadline, False, AS_OF).date == date(2026, 11, 13)
    assert deadlines.build_due([events[2]], RULE, False, AS_OF) is None
    assert deadlines.build_due(events, None, False, AS_OF) is None


def test_no_weekend_shift() -> None:
    saturday = deadlines.build_due([event("EV-1", date(2026, 10, 17))], RULE, False, AS_OF)
    assert saturday.date == date(2026, 10, 27) and saturday.date.weekday() == 1
    friday = deadlines.build_due([event("EV-1", date(2026, 10, 16))], RULE, False, AS_OF)
    assert friday.date == date(2026, 10, 26) and friday.date.weekday() == 0
    sunday = deadlines.build_due([event("EV-1", date(2026, 10, 18))], RULE, False, AS_OF)
    assert sunday.date == date(2026, 10, 28) and sunday.date.weekday() == 2
    assert deadlines.candidate_date(event("EV-1", date(2026, 10, 24)), RULE) == date(2026, 11, 3)


def test_calendar_contradiction_and_states() -> None:
    request = event("EV-RFE", date(2026, 10, 14))
    other = event("EV-CAL", date(2026, 10, 27), "CALENDAR_DEADLINE", "CALENDAR", False)
    same = event("EV-CAL", date(2026, 10, 24), "CALENDAR_DEADLINE", "CALENDAR", False)
    due = deadlines.build_due([request, other], RULE, False, AS_OF)
    assert (due.state, due.calendar_event_id, due.calendar_date) == ("CONFLICT", "EV-CAL", date(2026, 10, 27))
    assert deadlines.build_due([request, same], RULE, False, AS_OF).state == "PROPOSED"
    assert deadlines.build_due([request], RULE, True, AS_OF).state == "APPROVED"


@pytest.mark.parametrize(("as_of", "left", "state"), [
    (date(2026, 10, 24), 0, "PROPOSED"), (date(2026, 10, 25), -1, "OVERDUE"), (date(2026, 10, 23), 1, "PROPOSED"),
])  # fmt: skip
def test_overdue_and_days_left(as_of: date, left: int, state: str) -> None:
    due = deadlines.build_due([event("EV-RFE", date(2026, 10, 14))], RULE, False, as_of)
    assert (due.days_left, due.state) == (left, state)
    overdue_conflict = deadlines.due_state(True, -3, True)
    assert overdue_conflict == "OVERDUE"


def test_unverified_approved_note_never_changes_the_status() -> None:
    note = event("CAL-NOTE", date(2026, 10, 21), "CALENDAR_NOTE", "CALENDAR", False, "Calendar title: APPROVED, placeholder")
    portal = event("EV-1", date(2026, 10, 1), "STATUS_SNAPSHOT", details="Mock portal status: approved by clerk")
    assert deadlines.unverified_status_events([note, portal]) == [note]
    assert deadlines.build_due([note], RULE, False, AS_OF) is None


def test_proposed_deadline_value_is_recomputed_and_compared() -> None:
    due = deadlines.build_due([event("EV-RFE", date(2026, 10, 14))], RULE, False, AS_OF)
    good = {"due_date": "2026-10-24", "trigger_event_id": "EV-RFE"}
    assert deadlines.check_proposed_value(good, due) is None
    assert deadlines.check_proposed_value({**good, "due_date": "2026-10-27"}, due).code == "DEADLINE_MISMATCH"
    assert deadlines.check_proposed_value(good, None).code == "NO_DEADLINE"


# ---------------------------------------------------------------- the clock and the layer boundaries


def test_results_do_not_change_with_the_system_clock() -> None:
    def run() -> tuple:
        due = deadlines.build_due([event("EV-RFE", date(2026, 10, 14))], RULE, False, AS_OF)
        read = make_read("PASSPORT", Expires="2026-10-22", **{"Date of Birth": "1990-01-01"})
        return due, decide(read), values.check_values([make_read("EMPLOYER_LETTER", **{"Employment start": "2026-10-23"})], CTX)

    first = run()
    for fake_now in (0, 4_102_444_800):
        with mock.patch("time.time", return_value=fake_now):
            assert date.today().year in (1970, 2100) and time.time() == fake_now
            assert run() == first


def test_validation_package_has_no_model_network_database_or_clock() -> None:
    banned = re.compile(r"import (anthropic|httpx|requests|sqlalchemy)|from (anthropic|httpx|requests|sqlalchemy)|datetime\.now|date\.today|utcnow|time\.time")
    for path in Path(documents.__file__).parent.glob("*.py"):
        assert not banned.search(path.read_text()), path.name


def test_every_reason_code_has_a_plain_message() -> None:
    assert set(MESSAGES) == set(Reason)
    assert not any("—" in m or ";" in m for m in MESSAGES.values())


def test_a_date_written_in_words_or_year_first_is_read_as_that_date():
    from datetime import date

    for text in ("April 8, 1982", "8 April 1982", "8th April 1982", "08-Apr-1982", "1982/04/08", "1982.04.08", "Sept 5, 2026"):
        parsed, reason = values.parse_date(text)
        assert reason is None and parsed is not None, text
    assert values.parse_date("April 8, 1982")[0] == date(1982, 4, 8)
    assert values.parse_date("5th Sept 2026")[0] == date(2026, 9, 5)


def test_a_date_that_does_not_exist_or_reads_two_ways_is_still_not_guessed():
    assert values.parse_date("February 30, 2026")[1] is not None
    assert values.parse_date("3/4/25")[1] is not None
    assert values.parse_date("not a date")[1] is not None


def test_a_document_matching_any_name_on_file_is_for_the_right_case():
    read = make_read("PAY_STATEMENT", Applicant="Mira Dhawan")
    read.fields["PAY_STATEMENT.Applicant"].verified = True
    assert values.check_names([read], ["Mira Dawan", "Mira Dhawan"]) is None  # the spelling of the client is still undecided
    assert values.check_names([read], ["Mira Dawan"]).code == "CLIENT_NAME_MISMATCH"
    other = make_read("PAY_STATEMENT", Applicant="Zed Quux")
    other.fields["PAY_STATEMENT.Applicant"].verified = True
    found = values.check_names([other], ["Mira Dawan", "Mira Dhawan"])
    assert found.code == "CLIENT_NAME_MISMATCH" and "Mira Dawan, Mira Dhawan" in found.message
