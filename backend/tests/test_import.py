"""Import of new case data: stored once, audited, claims stay claims, other cases are out of reach."""

from sqlalchemy import text

from app.db.session import SessionLocal
from tests.test_facts import LEGAL, OPS, audit_actions, call, new_case

REQUEST = {"kind": "EVENT", "event_id": "EV-IMP-TEST-1", "event_date": "2026-10-20", "event_type": "MOCK_EVIDENCE_REQUEST_RECEIVED",
           "event_source": "MOCK_PORTAL", "source_reference": "SYN-REQ-1", "details": "Fictional evidence request.", "source_verified": True}


def send(case_id: str, body: dict, actor: str = OPS):
    return call("POST", f"/api/cases/{case_id}/import", actor, json=body)


def event(case_id: str, **changes) -> dict:
    return REQUEST | {"event_id": f"EV-{case_id}-1", "source_reference": f"SYN-{case_id}"} | changes


def test_only_the_legal_reviewer_can_import_a_verified_event():
    case_id = new_case("Import Verified")
    refused = send(case_id, event(case_id))  # OPS ticks verified
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "VERIFIED_IMPORT_LEGAL_ONLY"
    with SessionLocal() as db:
        assert db.scalar(text("SELECT count(*) FROM case_events WHERE case_id = :c"), {"c": case_id}) == 0
    unverified = send(case_id, event(case_id, source_verified=False))  # OPS may import it as a claim
    assert unverified.status_code == 200 and unverified.json()["deadline"] is None
    done = send(case_id, event(case_id, source_verified=True), LEGAL)
    assert done.status_code == 200 and done.json()["deadline"]["after"] == "2026-10-30"
    with SessionLocal() as db:
        flags = [r.details.get("source_verified") for r in db.execute(text("SELECT details FROM audit_log WHERE case_id = :c AND action = 'DATA_IMPORTED' AND outcome = 'ALLOWED' ORDER BY seq"), {"c": case_id})]
    assert flags == [False, True]  # the ledger shows who vouched


def test_a_verified_portal_request_creates_the_deadline_and_a_repeat_changes_nothing():
    case_id = new_case("Import Event")
    first = send(case_id, event(case_id), LEGAL)
    assert first.status_code == 200
    body = first.json()
    assert body["result"] == "INSERTED" and body["deadline"]["before"] is None and body["deadline"]["after"] == "2026-10-30"
    again = send(case_id, event(case_id), LEGAL).json()
    assert again["result"] == "UNCHANGED" and again["deadline"] is None and again["changes"] == []
    moved = send(case_id, event(case_id, event_date="2026-10-21"), LEGAL).json()
    assert moved["result"] == "UPDATED" and moved["deadline"]["before"] == "2026-10-30" and moved["deadline"]["after"] == "2026-10-31"
    with SessionLocal() as db:
        assert db.scalar(text("SELECT count(*) FROM case_events WHERE case_id = :c"), {"c": case_id}) == 1
    imported = [a for a in audit_actions(case_id) if a[0] == "DATA_IMPORTED"]
    assert len(imported) == 3  # every attempt is on the ledger, a repeat as UNCHANGED


def test_a_calendar_entry_can_never_be_verified_and_an_unverified_one_sets_no_deadline():
    case_id = new_case("Import Calendar")
    refused = send(case_id, event(case_id, event_source="GOOGLE_CALENDAR_MOCK", event_type="CALENDAR_DEADLINE"))
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "ONLY_PORTAL_VERIFIED"
    unverified = send(case_id, event(case_id, event_source="GOOGLE_CALENDAR_MOCK", event_type="CALENDAR_DEADLINE", source_verified=False))
    assert unverified.status_code == 200 and unverified.json()["deadline"] is None


def test_the_same_event_under_a_new_id_is_stored_once():
    case_id = new_case("Import Twin")
    send(case_id, event(case_id), LEGAL)
    twin = send(case_id, event(case_id, event_id=f"EV-{case_id}-2"), LEGAL).json()
    assert twin["result"] == "DUPLICATE_CONTENT" and twin["duplicate_of"] == f"EV-{case_id}-1"
    with SessionLocal() as db:
        assert db.scalar(text("SELECT count(*) FROM case_events WHERE case_id = :c"), {"c": case_id}) == 1


def test_an_import_cannot_reach_another_case_or_an_unassigned_user():
    mine, other = new_case("Import Mine"), new_case("Import Other")
    send(other, event(other), LEGAL)
    reach = send(mine, event(other), LEGAL)  # the other case's event id sent to my case
    assert reach.status_code == 409 and reach.json()["error"]["code"] == "RECORD_IN_OTHER_CASE"
    assert send(mine, event(mine, source_verified=False), "OPS-92").status_code == 403


def test_a_zoom_note_and_a_message_stay_claims_and_are_stored_once():
    case_id = new_case("Import Claims")
    note = {"kind": "ZOOM_NOTE", "recorded_at": "2026-10-25T10:00:00Z", "summary": "Client says the start date is 2024-01-01."}
    message = {"kind": "MESSAGE", "created_at": "2026-10-26T10:00:00Z", "channel": "WHATSAPP", "body": "My new address is 5 Invented Way."}
    assert send(case_id, note).json()["result"] == "INSERTED" and send(case_id, note).json()["result"] == "UNCHANGED"
    assert send(case_id, message).json()["result"] == "INSERTED" and send(case_id, message).json()["result"] == "UNCHANGED"
    with SessionLocal() as db:
        saved = db.execute(text("SELECT ai_generated, approved_as_fact FROM intake_notes WHERE case_id = :c"), {"c": case_id}).one()
        sent = db.execute(text("SELECT direction, sender_role FROM messages WHERE case_id = :c"), {"c": case_id}).one()
    assert (saved.ai_generated, saved.approved_as_fact) == (True, False) and (sent.direction, sent.sender_role) == ("INBOUND", "CLIENT")
    bodies = str(call("GET", f"/api/cases/{case_id}/communications").json())
    assert "5 Invented Way" in bodies
    with SessionLocal() as db:  # the ledger holds ids and results, never the text
        details = str(db.execute(text("SELECT details FROM audit_log WHERE case_id = :c AND action = 'DATA_IMPORTED'"), {"c": case_id}).all())
    assert "Invented Way" not in details and "2024-01-01" not in details
