"""The value gate: differently written values are one value only when the gate says they are the same thing."""

import random

from sqlalchemy import text

from app.ai.client import STATUS_NEEDS_REVIEW, STATUS_OK, CallResult
from app.db.session import SessionLocal
from app.facts import match_gate, sources
from tests.test_facts import add_claim, add_doc, add_profile, changed, facts, new_case


def unique() -> int:
    return random.randint(100000, 999999)  # stored answers persist, so every run asks about new values


def answer(same: bool, injection: bool = False):
    def fake(version, variables):
        return CallResult(STATUS_OK, {"injection_flag": injection, "matches": [{"id": "p1", "same": same, "reason": "test"}]}, None)

    return fake


def never(version, variables):
    raise AssertionError("code decides this pair, the model must not be asked")


def settle(case_id: str, call) -> bool:
    with SessionLocal() as db:
        done = match_gate.settle(db, sources.collect(db, case_id), case_id, call=call)
        db.commit()
    changed(case_id)
    return done


REQUIRED_DOCUMENT_KEY = {"full_name": "PASSPORT.Applicant", "employer_name": "EMPLOYER_LETTER.Employer"}


def two_spellings(field: str, first: str, second: str) -> str:
    case_id = new_case("Test Client")
    add_profile(case_id, field, first)
    if field in REQUIRED_DOCUMENT_KEY:  # the profile alone is not enough where a required document gives the field
        add_doc(case_id, REQUIRED_DOCUMENT_KEY[field], first)
    add_claim(case_id, "Z-9300", field, second)
    return case_id


def test_two_address_spellings_are_a_conflict_until_the_gate_decides():
    n = unique()
    case_id = two_spellings("mailing_address", f"{n} Invented Way, Unit 6, Example City, EX 00030", f"{n} Invented Way, Unit 6")
    assert facts(case_id)["mailing_address"]["state"] == "CONFLICT"


def test_the_gate_merges_the_same_address_written_differently():
    n = unique()
    full, short = f"{n} Invented Way, Unit 6, Example City, EX 00030", f"{n} Invented Way, Unit 6"
    case_id = two_spellings("mailing_address", full, short)
    assert settle(case_id, answer(True)) is True
    state = facts(case_id)["mailing_address"]
    assert state["state"] == "AGREE" and len(state["sources"]) == 2
    assert {s["value"] for s in state["sources"]} == {full, short}  # each source keeps its own spelling


def test_addresses_with_different_numbers_are_decided_in_code():
    n = unique()
    case_id = two_spellings("mailing_address", f"{n} Invented Way, Unit 6", f"{n + 1} Invented Way, Unit 6")
    assert facts(case_id)["mailing_address"]["state"] == "CONFLICT"
    assert settle(case_id, never) is False  # the rebuild already decided it in code, the model is never asked
    with SessionLocal() as db:
        row = db.execute(text("SELECT same, reason, prompt_run_id FROM value_matches WHERE field = 'mailing_address' ORDER BY id DESC LIMIT 1")).one()
    assert row.same is False and row.prompt_run_id is None and row.reason.startswith("Decided in code")


def test_a_failed_or_flagged_gate_leaves_the_conflict_open():
    n = unique()
    case_id = two_spellings("mailing_address", f"{n} Invented Way, Unit 6, Example City", f"{n} Invented Way, Unit 6")
    assert settle(case_id, lambda v, vars_: CallResult(STATUS_NEEDS_REVIEW, None, None)) is False
    assert facts(case_id)["mailing_address"]["state"] == "CONFLICT"
    n = unique()
    case_id = two_spellings("mailing_address", f"{n} Invented Way, Unit 6, Example City", f"{n} Invented Way, Unit 6")
    assert settle(case_id, answer(True, injection=True)) is False
    assert facts(case_id)["mailing_address"]["state"] == "CONFLICT"


def test_a_name_in_another_order_is_the_same_person():
    n = unique()
    first, last = f"Mira{n}", f"Dhawan{n}"
    case_id = two_spellings("full_name", f"{first} {last}", f"{last}, {first}")
    assert facts(case_id)["full_name"]["state"] == "CONFLICT"
    assert settle(case_id, answer(True)) is True
    assert facts(case_id)["full_name"]["state"] == "AGREE"


def test_a_different_spelling_of_a_name_is_always_a_conflict_and_never_asked():
    n = unique()
    case_id = two_spellings("full_name", f"Mira Dhawan{n}", f"Mira Dawan{n}")
    assert settle(case_id, never) is False  # decided in code already
    assert facts(case_id)["full_name"]["state"] == "CONFLICT"


def test_an_employer_without_its_legal_ending_is_the_same_employer():
    n = unique()
    case_id = two_spellings("employer_name", f"Fictional Employer {n} LLC", f"Fictional Employer {n}")
    assert settle(case_id, answer(True)) is True
    assert facts(case_id)["employer_name"]["state"] == "AGREE"


def test_a_different_employer_number_is_a_conflict_decided_in_code():
    n = unique()
    case_id = two_spellings("employer_name", f"Fictional Employer {n} LLC", f"Fictional Employer {n + 1} LLC")
    assert settle(case_id, never) is False  # decided in code already
    assert facts(case_id)["employer_name"]["state"] == "CONFLICT"


def test_a_date_of_birth_on_a_supporting_document_that_differs_from_the_passport_is_a_conflict():
    case_id = new_case("Test Client")
    add_doc(case_id, "PASSPORT.Date of Birth", "1982-04-08")
    add_doc(case_id, "ADDRESS_PROOF.Date of Birth", "1982-04-09")
    state = facts(case_id)["date_of_birth"]
    assert state["state"] == "CONFLICT" and len(state["sources"]) == 2


# ---------------------------------------------------------------- a supporting document against the case client


def document_name_finding(document_name: str, client: str, call):
    from app.core.contracts import DocumentRead, ReadField
    from app.validation import values

    read = DocumentRead(category="PAY_STATEMENT", fields={"PAY_STATEMENT.Applicant": ReadField(value=document_name, page=1, verified=True)})
    with SessionLocal() as db:
        match_gate.settle_names(db, values.applicant_names([read]) + [client], call=call)
        db.commit()
        same = match_gate.name_matcher(db, values.applicant_names([read]) + [client])
    return values.check_names([read], client, same)


def test_a_document_of_the_same_client_written_in_another_order_passes_the_client_check():
    n = unique()
    assert document_name_finding(f"Dhawan{n}, Mira{n}", f"Mira{n} Dhawan{n}", answer(True)) is None


def test_a_document_of_another_person_is_flagged_against_the_case_client():
    n = unique()
    found = document_name_finding(f"Priya Nair{n}", f"Mira Dhawan{n}", never)
    assert found is not None and found.code == "CLIENT_NAME_MISMATCH"


def test_a_misspelled_client_name_on_a_document_is_flagged_not_merged():
    n = unique()
    found = document_name_finding(f"Mira Dawan{n}", f"Mira Dhawan{n}", never)
    assert found is not None and found.code == "CLIENT_NAME_MISMATCH"
