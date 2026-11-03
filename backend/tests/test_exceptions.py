import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.cases import exceptions
from app.db.session import SessionLocal
from app.main import app
from tests.conftest import make_case

client = TestClient(app)
FOREIGN_NAME = "Zelda Foreignname"


def new_case(ops: str, status: str = "NEW", name: str = "Test Client") -> str:
    case_id = f"CASE-X{uuid.uuid4().hex[:6].upper()}"
    with SessionLocal() as db:
        make_case(db, case_id, ops=ops, status=status, name=name)
    return case_id


def add_upload(case_id: str, outcome: str, code: str | None = None, *, category: str | None = None, reason: str | None = None,
               flags: str = "{}", duplicate_of: str | None = None, injection: bool = False) -> str:  # fmt: skip
    upload_id = f"UP-X{uuid.uuid4().hex[:8].upper()}"
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO uploads (upload_id, case_id, storage_root, storage_path, original_filename, mime_type, file_size_bytes, "
                 "sha256, uploaded_at, uploader_role, ingestion_source, client_supplied_type, version_label, outcome, reason_code, "
                 "outcome_reason, category, flags, duplicate_of_upload_id) VALUES (:u, :c, 'APP_STORAGE', :u, 'a.pdf', "
                 "'application/pdf', 1, :h, now(), 'CLIENT', 'TEST', 'UNSPECIFIED', 'v1', :o, :rc, :r, :cat, CAST(:f AS jsonb), :d)"),
            {"u": upload_id, "c": case_id, "h": uuid.uuid4().hex + uuid.uuid4().hex, "o": outcome, "rc": code, "r": reason,
             "cat": category, "f": flags, "d": duplicate_of},
        )  # fmt: skip
        if injection:
            db.execute(text("INSERT INTO document_reads (upload_id, category, status, injection_flag) VALUES (:u, 'PASSPORT', 'READ', true)"),
                       {"u": upload_id})  # fmt: skip
        db.commit()
    return upload_id


def listing(actor: str, query: str = "") -> dict:
    response = client.get(f"/api/exceptions{query}", headers={"X-Actor": actor})
    assert response.status_code == 200
    return response.json()


def mine(actor: str, case_id: str) -> list[dict]:
    return [i for i in listing(actor)["items"] if i["case_id"] == case_id]


def types(items: list[dict]) -> set[str]:
    return {i["type"] for i in items}


def test_document_outcomes_become_typed_items():
    ops = "OPS-81"
    case_id = new_case(ops)
    original = add_upload(case_id, "USABLE", "OK", category="PASSPORT")
    duplicate = add_upload(case_id, "DUPLICATE", "DUPLICATE", reason=f"Same file as {original}", duplicate_of=original)
    expired = add_upload(case_id, "INVALID", "EXPIRED", category="PASSPORT", reason="The passport expired before the review date")
    add_upload(case_id, "INVALID", "STALE", category="EMPLOYER_LETTER", reason="The letter is dated before 2026-09-01")
    add_upload(case_id, "INVALID", "NEEDS_TRANSLATION", category="EMPLOYER_LETTER", reason="A certified English translation is needed")
    add_upload(case_id, "SUPERSEDED", "SUPERSEDED", reason="A later version replaces this file")
    add_upload(case_id, "NEEDS_HUMAN_REVIEW", "ROTATED", reason="Page 1 is rotated and cannot be read upright")
    add_upload(case_id, "NEEDS_HUMAN_REVIEW", "UNREADABLE", reason="has too little readable content")
    add_upload(case_id, "NEEDS_HUMAN_REVIEW", "PAY_PERIOD", reason="The pay period is not one the rules ask for")
    add_upload(case_id, "NEEDS_HUMAN_REVIEW", "NO_REFERENCE", reason="The notice has no reference number")
    add_upload(case_id, "NEEDS_HUMAN_REVIEW", "SCANNED_PAGE", reason="Read from a scanned page, a person must check it")
    add_upload(case_id, "CLAIM_SOURCE", "CLAIM_SOURCE", category="ZOOM_NOTES")
    add_upload(case_id, "PENDING")
    items = mine(ops, case_id)
    assert types(items) == {"DUPLICATE", "EXPIRED", "STALE", "NEEDS_TRANSLATION", "SUPERSEDED", "UNREADABLE", "HUMAN_REVIEW"}
    dup = next(i for i in items if i["type"] == "DUPLICATE")
    assert dup["source_ids"] == [duplicate, original] and dup["severity"] == "LOW" and dup["next_action"] == "Open documents"
    assert next(i for i in items if i["type"] == "EXPIRED")["source_ids"] == [expired]
    assert sum(i["type"] == "UNREADABLE" for i in items) == 2 and sum(i["type"] == "HUMAN_REVIEW" for i in items) == 3
    assert all(set(i) == {"case_id", "client_name", "type", "severity", "title", "reason", "source_ids", "next_action", "owner_role", "blocks_send"}
               for i in items)  # fmt: skip


def test_quarantined_files_never_show_a_foreign_name_or_case():
    ops = "OPS-82"
    other = new_case("OPS-83", name=FOREIGN_NAME)
    case_id = new_case(ops)
    flags = f'{{"foreign_pages": [2, 3], "owner": "{other}"}}'
    with SessionLocal() as db:
        db.execute(text("UPDATE cases SET client_ref = :n WHERE case_id = :c"), {"n": FOREIGN_NAME, "c": other})
        db.commit()
    wrong = add_upload(case_id, "QUARANTINED", "WRONG_CLIENT", reason=f"belongs to {FOREIGN_NAME}", flags='{"injection": false}')
    mixed = add_upload(case_id, "QUARANTINED", "MIXED_CLIENTS", reason=f"Pages 2, 3 belong to {FOREIGN_NAME}", flags=flags)
    items = [i for i in mine(ops, case_id) if i["type"] != "MISSING_DOCUMENT"]
    by_type = {i["type"]: i for i in items}
    assert set(by_type) == {"WRONG_CLIENT", "MIXED_CLIENTS"} and by_type["WRONG_CLIENT"]["source_ids"] == [wrong]
    assert by_type["MIXED_CLIENTS"]["source_ids"] == [mixed] and "Pages 2, 3" in by_type["MIXED_CLIENTS"]["reason"]
    body = str(listing(ops)) + str(client.get("/api/home", headers={"X-Actor": ops}).json())
    docs = client.get(f"/api/cases/{case_id}/documents", headers={"X-Actor": ops}).json()
    assert FOREIGN_NAME not in body and other not in body + str(docs)
    assert all(d["pages"] == [] for d in docs["items"]) and {d["upload_id"]: d["foreign_pages"] for d in docs["items"]}[mixed] == [2, 3]


def test_injection_flag_from_upload_flags_or_the_read():
    ops = "OPS-84"
    case_id = new_case(ops)
    flagged = add_upload(case_id, "USABLE", "OK", flags='{"injection": true}')
    read = add_upload(case_id, "USABLE", "OK", injection=True)
    items = [i for i in mine(ops, case_id) if i["type"] == "SUSPICIOUS_TEXT"]
    assert sorted(i["source_ids"][0] for i in items) == sorted([flagged, read]) and items[0]["severity"] == "HIGH"
    docs = {d["upload_id"]: d["injection"] for d in client.get(f"/api/cases/{case_id}/documents", headers={"X-Actor": ops}).json()["items"]}
    assert docs == {flagged: True, read: True}


def test_every_required_category_is_missing_for_a_case_with_no_file_and_nothing_is_called_missing_while_a_file_is_read():
    ops = "OPS-85"
    empty, partial, reading = new_case(ops), new_case(ops), new_case(ops)
    add_upload(partial, "USABLE", "OK", category="PASSPORT")
    add_upload(reading, "READING")
    assert len([i for i in mine(ops, empty) if i["type"] == "MISSING_DOCUMENT"]) == 6  # no document at all, so all six are owed
    assert mine(ops, reading) == []
    missing = [i for i in mine(ops, partial) if i["type"] == "MISSING_DOCUMENT"]
    assert len(missing) == 5 and all(i["source_ids"] == [] and i["severity"] == "HIGH" for i in missing)  # a required document is high
    assert not any("passport" in i["title"].lower() for i in missing)


def test_open_fact_conflict_is_listed_with_its_sources():
    ops = "OPS-86"
    case_id = new_case(ops, name="Maria Lopez")
    with SessionLocal() as db:
        db.execute(
            text("INSERT INTO claims (case_id, source_id, field_name, value, quote, page) VALUES (:c, :s, 'full_name', 'Maria Lopes', 'x', 1)"),
            {"c": case_id, "s": f"Z-{uuid.uuid4().hex[:6]}"},
        )
        db.commit()
    item = next(i for i in mine(ops, case_id) if i["type"] == "FACT_CONFLICT")
    assert item["severity"] == "HIGH" and item["owner_role"] == "LEGAL" and item["next_action"] == "Review conflict"
    assert f"PROFILE-{case_id}-full_name" in item["source_ids"] and len(item["source_ids"]) == 2


def test_deadline_conflict_overdue_and_proposals():
    ops = "OPS-87"
    case_id = new_case(ops)
    with SessionLocal() as db:
        for event_id, kind, when, source, verified in (
            (f"EV-X{uuid.uuid4().hex[:6]}", "MOCK_EVIDENCE_REQUEST_RECEIVED", "2026-10-01", "MOCK_PORTAL", True),
            (f"EV-X{uuid.uuid4().hex[:6]}", "CALENDAR_DEADLINE", "2026-11-20", "GOOGLE_CALENDAR_MOCK", False),
        ):
            db.execute(
                text("INSERT INTO case_events (event_id, case_id, event_date, event_type, event_source, source_reference, details, "
                     "source_verified, import_batch) VALUES (:e, :c, :d, :t, :s, 'test', :e, :v, 'test')"),
                {"e": event_id, "c": case_id, "d": when, "t": kind, "s": source, "v": verified},
            )  # fmt: skip
        db.commit()
    client.post(f"/api/cases/{case_id}/proposals", headers={"X-Actor": ops},
                json={"kind": "STAGE_CHANGE", "idempotency_key": uuid.uuid4().hex, "value": {"to_stage": "ON_HOLD", "reason": "x"}})  # fmt: skip
    items = mine(ops, case_id)
    assert {"DEADLINE_CONFLICT", "OVERDUE", "PROPOSAL_PENDING"} <= types(items)
    conflict = next(i for i in items if i["type"] == "DEADLINE_CONFLICT")
    assert len(conflict["source_ids"]) == 2 and "Nov 20, 2026" in conflict["reason"] and "not evidence" in conflict["reason"]
    assert next(i for i in items if i["type"] == "OVERDUE")["severity"] == "HIGH"
    assert next(i for i in items if i["type"] == "PROPOSAL_PENDING")["owner_role"] == "LEGAL"


def test_scoping_drafts_and_the_case_route():
    ops = "OPS-88"
    case_id = new_case(ops)
    draft = new_case(ops, status="DRAFT")
    add_upload(case_id, "INVALID", "EXPIRED", reason="x")
    add_upload(draft, "INVALID", "EXPIRED", reason="x")
    assert mine(ops, case_id) and mine(ops, draft) == []
    assert listing("OPS-89")["items"] == [] or all(i["case_id"] != case_id for i in listing("OPS-89")["items"])
    assert client.get(f"/api/cases/{case_id}/documents", headers={"X-Actor": "OPS-89"}).status_code == 403
    assert client.get("/api/exceptions").status_code == 401


def test_sorting_filters_and_counts():
    ops = "OPS-90"
    first, second = new_case(ops, name="Alpha Person"), new_case(ops, name="Beta Person")
    add_upload(second, "DUPLICATE", "DUPLICATE", reason="Same file as UP-1", duplicate_of="UP-1")
    add_upload(first, "INVALID", "EXPIRED", reason="x")
    add_upload(first, "QUARANTINED", "WRONG_CLIENT", reason="x")
    body = listing(ops)
    severities = [i["severity"] for i in body["items"]]
    assert severities == sorted(severities, key=exceptions.SEVERITY_ORDER.get)
    assert body["counts"]["WRONG_CLIENT"] == 1 and body["counts"]["DUPLICATE"] == 1 and sum(body["counts"].values()) >= 3
    assert body["total"] == len(body["items"])
    only = listing(ops, "?type=DUPLICATE")
    assert types(only["items"]) == {"DUPLICATE"} and only["counts"] == body["counts"] and only["total"] == 1
    by_name = listing(ops, "?q=beta person")
    assert {i["case_id"] for i in by_name["items"]} == {second} and by_name["counts"] == {"DUPLICATE": 1, "MISSING_DOCUMENT": 6}
    assert {i["case_id"] for i in listing(ops, f"?q={first.lower()}")["items"]} == {first}


def home_row(actor: str, case_id: str) -> dict:
    return client.get("/api/home", params={"case_id": case_id}, headers={"X-Actor": actor}).json()["rows"][0]


def test_home_reason_follows_the_document_precedence():
    ops = "OPS-91"
    case_id = new_case(ops)
    steps = [
        ("NEEDS_HUMAN_REVIEW", "PAY_PERIOD", "missing_document"), ("DUPLICATE", "DUPLICATE", "duplicate"),
        ("INVALID", "NEEDS_TRANSLATION", "needs_translation"), ("INVALID", "STALE", "stale"), ("INVALID", "EXPIRED", "expired"),
        ("NEEDS_HUMAN_REVIEW", "UNREADABLE", "unreadable"), ("QUARANTINED", "MIXED_CLIENTS", "mixed_clients"),
        ("QUARANTINED", "WRONG_CLIENT", "wrong_client"),
    ]  # fmt: skip
    add_upload(case_id, "USABLE", "OK", category="PASSPORT")
    row = home_row(ops, case_id)
    assert row["reason"]["key"] == "missing_document" and row["next_action"] == "Open documents" and row["attention"]
    for outcome, code, key in steps:
        add_upload(case_id, outcome, code, reason="x")
        row = home_row(ops, case_id)
        assert row["reason"]["key"] == key and row["next_action"] == "Open documents" and row["attention"]
    flagged = add_upload(case_id, "USABLE", "OK", flags='{"injection": true}')
    row = home_row(ops, case_id)
    assert row["reason"]["key"] == "suspicious_text" and flagged in row["refs"]


def test_a_superseded_file_alone_does_not_change_the_home_reason():
    ops = "OPS-92"
    case_id = new_case(ops)
    add_upload(case_id, "SUPERSEDED", "SUPERSEDED", reason="x")
    for category in ("PASSPORT", "ARRIVAL_RECORD", "EMPLOYER_LETTER", "PRIOR_NOTICE"):
        add_upload(case_id, "USABLE", "OK", category=category)
    assert home_row(ops, case_id)["reason"]["key"] == "missing_document"


def test_human_review_is_the_home_reason_once_every_category_is_present():
    ops = "OPS-93"
    case_id = new_case(ops)
    for category in ("PASSPORT", "ARRIVAL_RECORD", "EMPLOYER_LETTER", "PRIOR_NOTICE"):
        add_upload(case_id, "USABLE", "OK", category=category)
    for period in ("2026-08", "2026-09"):
        add_upload(case_id, "USABLE", "OK", category="PAY_STATEMENT", flags=f'{{"pay_period": "{period}"}}')
    assert home_row(ops, case_id)["reason"]["key"] == "working"
    add_upload(case_id, "NEEDS_HUMAN_REVIEW", "SCANNED_PAGE", reason="Read from a scanned page, a person must check it")
    assert home_row(ops, case_id)["reason"]["key"] == "human_review"


def test_one_cases_exceptions_are_listed_for_its_owner_only():
    ops = "OPS-95"
    case_id = new_case(ops)
    add_upload(case_id, "USABLE", "OK", category="PASSPORT")
    body = client.get(f"/api/cases/{case_id}/exceptions", headers={"X-Actor": ops}).json()
    assert body["total"] == len(body["items"]) > 0 and {i["case_id"] for i in body["items"]} == {case_id}
    assert any(i["type"] == "MISSING_DOCUMENT" for i in body["items"]) and "MISSING_DOCUMENT" in body["counts"]
    assert client.get(f"/api/cases/{case_id}/exceptions", headers={"X-Actor": "OPS-96"}).status_code == 403
